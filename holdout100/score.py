#!/usr/bin/env python3
"""score.py - score a model's replies against the Etiquette printed-truth cards.

    python3 score.py cards.jsonl replies/run13.jsonl            # the headline number and the per-field table
    python3 score.py cards.jsonl replies/run13.jsonl --examples  # plus up to 12 disagreements per field

This script needs NO GPU, NO model and NO network. It reads the two files and compares them, nothing else:
  cards.jsonl        one line per product: what a person recorded as printed on the pack (or "not printed")
  replies/<run>.jsonl one line per product: what a model returned for that product's ticked photos, raw and parsed
Python 3.8+, standard library only. It is a faithful copy of the scorer that gated the Etiquette release (FoodClock
worker 0.93.0, fcworker/truth.py + bench.same_text), so the number it prints for replies/run13.jsonl is the number on
the model card. To score your own model: run it on each card's photos (the `photos` urls, in that order, with the
prompt.txt and system.txt from the model repo or your own), parse the JSON object it returns, and write one line per
card as {"code": ..., "reading": <that object>}; the raw text can go in "reply".

How a field is judged (per card, per field):
  printed + read equal      agree        printed + read other   differ       printed + nothing read   missing
  not printed + nothing     agree        not printed + a value  invented
Numbers agree within 2% (or 0.05). Text agrees after normalisation when equal, one inside the other, or sharing 60% of
the shorter side's words. Net quantity agrees after unit and e-mark normalisation ("220 g" = "220g e"). The per-language
name fields are judged per language entry; a right text filed under another slot (brand / front / generic) or another
language key is a "slot" filing disagreement, counted separately: the headline percentage counts it as not agreeing
(agree / every judgement, slot included), the per-field percentages leave it out (agree / (judgements - slot)).
"""
import json, re, sys, unicodedata
from collections import Counter, defaultdict

FIELDS = ("product_name", "brand", "quantity", "basis", "energy_kcal_100g", "salt_100g", "sodium_mg")
NAME_FIELDS = (("front_names", "product_names"), ("generic_names", "generic_names"))   # (truth field, reading field)

HDR = re.compile(r"^\s*\(?\s*[a-z]{0,3}\s*\)?\s*[-:]?\s*(ingredients?|ingr[ée]dients?|ingredientes?|ingredienti|zutaten|ingredi[eë]nten|"
                 r"slo[žz]en[íi]|zlo[žz]enie|sk[łl]adniki|съставки|състав|συστατικά|المكونات|المكوّنات|ส่วนประกอบ|состав|"
                 r"sast[āa]vda[ļl]as|koostisosad|sudedamosios dalys|összetevők|sestavine|sastojci|innihald|ainesosat|"
                 r"ingredienser|ingrediens|bestanddelen|i[çc]indekiler|成分|原材料名|원재료명)\s*[:：]\s*", re.I)


def _norm(s):
    if not s: return ""
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"^\s*\(?\s*\w{1,3}\s*\)?\s*(ingr[ée]dients?|ingredients|المكونات)\s*[:：]\s*", "", s, flags=re.I)
    s = HDR.sub("", s, count=1).replace("œ", "oe").replace("æ", "ae").replace("ß", "ss")
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _qnorm(s):
    """quantity: '220 g' == '220g e' == '220 gr'; '0.5 L' == '0,5L'."""
    s = _norm(str(s).replace(",", "."))
    s = re.sub(r"\b(e|net|nett|netto|neto|peso neto|poids net|approx|ca|env)\b", " ", s)
    s = re.sub(r"\b(grs?|gramm?e?s?|grammes?|gramos?)\b", "g", s)
    s = re.sub(r"\b(ltr|litres?|liters?|litros?)\b", "l", s)
    s = re.sub(r"\b(millilitres?|milliliters?|mililitros?)\b", "ml", s)
    return re.sub(r"\s+", "", s)


def same_text(g, r, kind="name"):
    if kind == "quantity":
        ng, nr = _qnorm(g), _qnorm(r)
        return bool(ng) and bool(nr) and (ng == nr or ng in nr or nr in ng)
    ng, nr = _norm(g), _norm(r)
    if not ng or not nr: return ng == nr
    if ng == nr or ng in nr or nr in ng: return True
    tg, tr = set(ng.split()), set(nr.split())
    return len(tg & tr) / min(len(tg), len(tr)) >= 0.6


def _num(v):
    if v is None: return None
    if isinstance(v, (int, float)) and not isinstance(v, bool): return float(v)
    m = re.search(r"-?\d+(?:[.,]\d+)?", str(v).replace(",", "."))
    return float(m.group(0)) if m else None


def _basis(v):
    s = str(v or "").lower().replace(" ", "")
    if not s: return None
    if s.startswith("100g"): return "100g"
    if s.startswith("100ml"): return "100ml"
    if s.startswith("1l") or "1l(" in s: return "1l"
    if "serving" in s or "portion" in s or "package" in s or "bag" in s: return "serving"
    return s[:12]


def reading_value(r, f):
    n = r.get("nutriments") or {}
    if f == "energy_kcal_100g": return n.get("energy_kcal_100g")
    if f == "salt_100g": return None if r.get("salt_from_sodium") else n.get("salt_100g")
    if f == "sodium_mg": return r.get("sodium_mg")
    if f == "basis":
        per = (r.get("basis") or {}).get("per")
        return None if str(per or "").strip().lower() in ("", "unknown", "?", "none", "null") else per
    return r.get(f)


def judge(f, truth_v, read_v):
    if f in ("energy_kcal_100g", "salt_100g", "sodium_mg"):
        a, b = _num(truth_v), _num(read_v)
        if a is None or b is None: return False
        return abs(a - b) < max(0.05, abs(a) * 0.02)
    if f == "basis": return _basis(truth_v) == _basis(read_v)
    return same_text(truth_v, read_v, "quantity" if f == "quantity" else "name")


def _truth_dict(row):
    """A per-language truth field: {lang: text} when printed, else {}. The value may be an object or its JSON text."""
    if not row or not row.get("printed"): return {}
    v = row.get("value")
    if isinstance(v, str):
        try: v = json.loads(v or "{}")
        except Exception: v = {}
    return v if isinstance(v, dict) else {}


def _texts(src, keys):
    out = []
    for kk in keys:
        v = src.get(kk)
        if isinstance(v, dict): out.extend(x for x in v.values() if isinstance(x, str))
        elif isinstance(v, str): out.append(v)
    return out


def score(cards, replies, show_examples=False):
    per = defaultdict(Counter); tot = Counter(); n = 0; examples = defaultdict(list)
    for code, t in cards.items():
        r = replies.get(code)
        if r is None: continue
        n += 1
        for tf, rf in NAME_FIELDS:
            row = t.get(tf)
            if row is None or not isinstance(r.get(rf), (dict, type(None))): continue
            truth_d = _truth_dict(row); read_d = r.get(rf) or {}
            if not truth_d:
                k = "invented" if read_d else "agree"; per[tf][k] += 1; tot[k] += 1
                if k == "invented" and len(examples[tf]) < 12: examples[tf].append((code, "not printed", read_d))
                continue
            read_all = _texts(r, ("product_names", "generic_names", "product_name", "brand"))
            truth_all = []
            for tk in ("front_names", "generic_names"): truth_all.extend(x for x in _truth_dict(t.get(tk)).values() if isinstance(x, str))
            bt = t.get("brand") or {}
            if bt.get("printed") and bt.get("value"): truth_all.append(bt["value"])
            for lang, tv in truth_d.items():
                rv = read_d.get(lang)
                k = "missing" if not rv else ("agree" if same_text(tv, rv, "name") else "differ")
                if k != "agree" and any(same_text(tv, x, "name") for x in read_all): k = "slot"
                per[tf][k] += 1; tot[k] += 1
                if k not in ("agree", "slot") and len(examples[tf]) < 12: examples[tf].append((code, "%s: %s" % (lang, tv), rv))
            for lang in read_d:
                if lang not in truth_d:
                    k = "slot" if any(same_text(x, read_d[lang], "name") for x in truth_all) else "invented"
                    per[tf][k] += 1; tot[k] += 1
                    if k == "invented" and len(examples[tf]) < 12: examples[tf].append((code, "%s: not printed" % lang, read_d[lang]))
        for f in FIELDS:
            row = t.get(f)
            if row is None: continue
            rv = reading_value(r, f)
            if f == "product_name" and isinstance(rv, dict): rv = [x for x in rv.values() if isinstance(x, str)] or None
            empty = rv is None or (isinstance(rv, str) and not rv.strip()) or (isinstance(rv, list) and not rv)
            if row.get("printed"):
                if isinstance(rv, list): k = "agree" if any(judge(f, row.get("value"), x) for x in rv) else "differ"
                else: k = "missing" if empty else ("agree" if judge(f, row.get("value"), rv) else "differ")
            else:
                k = "agree" if empty else "invented"
            per[f][k] += 1; tot[k] += 1
            if k in ("differ", "invented") and len(examples[f]) < 12: examples[f].append((code, row.get("value") if row.get("printed") else "not printed", rv))
    judged = sum(tot.values())   # the headline counts a slot filing as not agreeing; the per-field lines excuse it
    print("printed-truth score: %d cards, %d fields | agree %d differ %d missing %d invented %d | %.1f%%"
          % (n, judged, tot["agree"], tot["differ"], tot["missing"], tot["invented"], 100.0 * tot["agree"] / max(1, judged)))
    print("slot = right text, wrong slot or language key (filing disagreement, excused from acc%%): %d" % tot.get("slot", 0))
    print("%-18s %6s %6s %7s %8s %5s  %s" % ("field", "agree", "differ", "missing", "invented", "slot", "acc%"))
    for f in FIELDS + tuple(tf for tf, _ in NAME_FIELDS):
        c = per[f]; m = sum(c.values())
        if not m: continue
        print("%-18s %6d %6d %7d %8d %5d  %5.1f" % (f, c["agree"], c["differ"], c["missing"], c["invented"], c["slot"], 100.0 * c["agree"] / max(1, m - c["slot"])))
    if show_examples:
        for f in FIELDS + tuple(tf for tf, _ in NAME_FIELDS):
            if examples[f]:
                print("\n%s (code, truth, reading)" % f)
                for e in examples[f]: print("  ", e)
    return 100.0 * tot["agree"] / max(1, judged)


def load_jsonl(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(ln) for ln in fh if ln.strip()]


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    if len(a) != 2: sys.exit(__doc__)
    cards = {c["code"]: c["truth"] for c in load_jsonl(a[0])}
    replies = {r["code"]: (r.get("reading") or {}) for r in load_jsonl(a[1])}
    score(cards, replies, show_examples="--examples" in sys.argv)
