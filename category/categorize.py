#!/usr/bin/env python3
"""Apply an Open Food Facts category to an Etiquette reading.

Etiquette reads the pack and returns no category on purpose; this script files the reading. Two short text calls to
any chat model behind an OpenAI-compatible endpoint (Ollama, llama.cpp, vLLM, a hosted API):

  1. family   - the model names the family the product belongs to; the guess is resolved onto a real taxonomy node
  2. depth    - the model picks the deepest candidate under that node it is certain of, or keeps the parent

Candidates come from the taxonomy itself (off_taxonomy.py), never from the model's memory, and a choice outside the
candidate list is treated as "keep". The output is one category id, a confidence and a one-line reason.

  python categorize.py reading.json                      # an Etiquette reading (JSON) -> category
  python categorize.py reading.json --model gemma4:31b --endpoint http://localhost:11434/v1
  python categorize.py --name "Volle yoghurt" --brand "Albert Heijn" --ingredients "volle yoghurt" --quantity "1 l"

Environment: CATEGORY_ENDPOINT (default http://localhost:11434/v1), CATEGORY_MODEL (default gemma4:31b),
CATEGORY_API_KEY (only for hosted endpoints).
"""
import argparse
import json
import os
import re
import sys
import urllib.request

from off_taxonomy import Taxonomy

FAMILY_PROMPT = (
 "You classify ONE packaged food product into the Open Food Facts category taxonomy.\n"
 "Product: name={name} | brand={brand} | quantity={quantity}\nIngredients: {ingredients}\n"
 "Name the FAMILY this product belongs to, as an Open Food Facts category id such as en:cheeses, en:breads, "
 "en:yogurts, en:fruit-soft-drinks, en:canned-vegetables, en:biscuits. One id, nothing else."
)
DEPTH_PROMPT = (
 "You classify ONE packaged food product into the Open Food Facts category taxonomy.\n"
 "Product: name={name} | brand={brand} | quantity={quantity}\nIngredients: {ingredients}\n"
 "It is already classified as: {coarse_id} ({coarse_name}).\n"
 "Below are the more specific categories under it. Pick the ONE deepest candidate that certainly fits this product. "
 "If none fits with certainty, answer keep. Never guess a flavour, a process (frozen, canned, cooked) or a fat level "
 "that the facts do not state.\n"
 "Candidates (id | English name | local name | depth below the current category):\n{cands}\n"
 'Answer ONLY a JSON object: {{"choice": "<candidate id or keep>", "confidence": "high|medium|low", '
 '"reason": "one short sentence naming the fact that decides it"}}'
)


def chat(prompt, model, endpoint, api_key=None, max_tokens=220):
    body = {"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0, "max_tokens": max_tokens}
    req = urllib.request.Request(endpoint.rstrip("/") + "/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", **({"Authorization": "Bearer " + api_key} if api_key else {})})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)["choices"][0]["message"]["content"]


def facts_from_reading(reading):
    """Pull name, brand, quantity and the ingredients from an Etiquette reading (any language, first one found)."""
    pn = reading.get("product_name") or {}
    name = pn.get("nl") or pn.get("en") or (next(iter(pn.values())) if isinstance(pn, dict) and pn else str(pn or ""))
    ingr = reading.get("ingredients") or {}
    ingredients = ingr.get("nl") or ingr.get("en") or (next(iter(ingr.values())) if isinstance(ingr, dict) and ingr else str(ingr or ""))
    return {"name": name or "", "brand": reading.get("brand") or "", "quantity": reading.get("quantity") or "",
            "ingredients": (ingredients or "")[:1200]}


def candidates(tax, root, text, lang="nl", cap=60):
    words = set(re.findall(r"[^\W\d_]{3,}", (text or "").lower()))
    def score(cid):
        nm = (tax.name(cid, "en") + " " + tax.name(cid, lang)).lower()
        return len(words & set(re.findall(r"[^\W\d_]{3,}", nm)))
    rows = tax.descendants(root, 6)
    direct = sorted([c for c, d in rows if d == 1], key=lambda c: (-score(c), c))
    deeper = sorted([(c, d) for c, d in rows if d > 1], key=lambda x: (-score(x[0]), x[1], x[0]))
    out = [(c, d) for c, d in deeper if score(c) > 0][:cap // 2]
    for c in direct:
        if len(out) >= cap: break
        if c not in [x[0] for x in out]: out.append((c, 1))
    return out


def categorize(facts, tax, model, endpoint, api_key=None, lang="nl", coarse=None):
    if not coarse:
        guess = chat(FAMILY_PROMPT.format(**facts), model, endpoint, api_key, 40).strip().split()[0].strip("`\"'.,")
        coarse = tax.resolve(guess)
        if not coarse:
            return {"category": None, "coarse": None, "confidence": "low", "reason": "family %r not in the taxonomy" % guess}
    cands = candidates(tax, coarse, " ".join(facts.values()), lang)
    if not cands:
        return {"category": coarse, "coarse": coarse, "confidence": "high", "reason": "%s is already a leaf" % coarse}
    lines = "\n".join("%s | %s | %s | %d" % (c, tax.name(c, "en"), tax.name(c, lang), d) for c, d in cands)
    reply = chat(DEPTH_PROMPT.format(coarse_id=coarse, coarse_name=tax.name(coarse, "en"), cands=lines, **facts), model, endpoint, api_key)
    m = re.search(r"\{.*\}", reply, re.S)
    try:
        j = json.loads(m.group(0)) if m else {}
    except Exception:
        j = {}
    choice = str(j.get("choice") or "keep").strip()
    if choice != "keep" and choice not in {c for c, _ in cands}:
        return {"category": coarse, "coarse": coarse, "confidence": "low", "reason": "model answered %r, not a candidate; kept" % choice[:60]}
    return {"category": coarse if choice == "keep" else choice, "coarse": coarse,
            "confidence": str(j.get("confidence") or "low").lower(), "reason": str(j.get("reason") or "")[:300],
            "candidates": len(cands)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("reading", nargs="?", help="an Etiquette reading, JSON file")
    ap.add_argument("--name"); ap.add_argument("--brand", default=""); ap.add_argument("--quantity", default=""); ap.add_argument("--ingredients", default="")
    ap.add_argument("--coarse", help="skip the family call: start from this category id")
    ap.add_argument("--lang", default="nl", help="local names shown beside the English ones")
    ap.add_argument("--model", default=os.environ.get("CATEGORY_MODEL", "gemma4:31b"))
    ap.add_argument("--endpoint", default=os.environ.get("CATEGORY_ENDPOINT", "http://localhost:11434/v1"))
    a = ap.parse_args()
    if a.reading:
        facts = facts_from_reading(json.load(open(a.reading, encoding="utf-8")))
    elif a.name:
        facts = {"name": a.name, "brand": a.brand, "quantity": a.quantity, "ingredients": a.ingredients[:1200]}
    else:
        ap.error("give a reading file or --name")
    tax = Taxonomy.load()
    out = categorize(facts, tax, a.model, a.endpoint, os.environ.get("CATEGORY_API_KEY"), a.lang, a.coarse)
    out["taxonomy"] = tax.source()
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
