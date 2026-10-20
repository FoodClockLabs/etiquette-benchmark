"""Post-processing of nutrition-extractor token labels, ported from Open Food Facts' Robotoff
(robotoff/prediction/nutrition_extraction.py, AGPL-3.0, (c) Open Food Facts contributors) so the model can be run and
scored outside Triton. Behaviour kept exactly: B-/I- prefixes ignored, consecutive same-label words merged into one entity,
word text stripped of whitespace and "()/", the value/unit regex, energy-unit sanity, a trailing 8/9 on the matched value of a
macronutrient read as a misread "g", and any label that occurs more than once voids all its entities.
This file is AGPL-3.0 like its source. Everything else in this repository is Apache-2.0."""
import re

NUM = re.compile(r"(< ?)?((?:[0-9]+[,.]?[0-9]*)|O) ?(g|mg|µg|mcg|kj|kcal)?", re.I)
MACRO = ("proteins", "sugars", "fat", "saturated_fat", "carbohydrates", "fiber", "salt", "added_sugars", "trans_fat")


def parse_value(entity, text):
    """-> (value, unit, invalid_reason) as robotoff's match_nutrient_value + the energy checks."""
    t = text.strip().lower()
    if "trace" in t:
        return "traces", None, None
    m = NUM.match(t)
    if not m:
        return None, None, "no_value"
    val = m.group(2).replace(",", ".")
    val = "0" if val == "o" else val
    unit = (m.group(3) or "").lower().replace("mcg", "µg") or None
    base = entity.rsplit("_", 1)[0] if entity != "serving_size" else entity
    if unit is None:
        if base == "energy_kcal":
            unit = "kcal"
        elif base == "energy_kj":
            unit = "kj"
        elif val.endswith(("8", "9")) and len(val) > 1 and base in MACRO:
            unit = "g"
            val = val[:-1]
    if base == "energy_kcal" and unit not in (None, "kcal"):
        return val, unit, "energy_unit_mismatch"
    if base == "energy_kj" and unit not in (None, "kj"):
        return val, unit, "energy_unit_mismatch"
    if base not in ("energy_kcal", "energy_kj") and unit in ("kcal", "kj"):
        return val, unit, "energy_unit_on_non_energy"
    try:
        float(val)
    except ValueError:
        if val != "traces":
            return None, unit, "no_value"
    return val, unit, None


def aggregate(words, labels):
    """words: list of str; labels: list of label names ('O' or 'B-X'/'I-X'/'X') -> list of {entity, words}."""
    ents, cur = [], None
    for w, lab in zip(words, labels):
        ent = None if lab == "O" else (lab[2:] if lab[:2] in ("B-", "I-") else lab)
        if ent and cur and cur["entity"] == ent:
            cur["words"].append(w)
            continue
        if cur:
            ents.append(cur)
        cur = {"entity": ent, "words": [w]} if ent else None
    if cur:
        ents.append(cur)
    return ents


def postprocess(ents):
    """-> (all entities with value/unit/invalid_reason, dict of valid ones by entity name)"""
    post = []
    for e in ents:
        name = e["entity"].lower()
        text = " ".join(w.strip().strip("()/") for w in e["words"])
        val, unit, inv = parse_value(name, text)
        post.append({"entity": name, "text": text, "value": val, "unit": unit, "invalid_reason": inv})
    seen = {}
    for p in post:
        seen.setdefault(p["entity"], []).append(p)
    for v in seen.values():
        if len(v) > 1:
            for p in v:
                p["invalid_reason"] = p["invalid_reason"] or "multiple_entities"
    valid = {p["entity"]: {"value": p["value"], "unit": p["unit"], "text": p["text"]}
             for p in post if not p["invalid_reason"] and p["value"] not in (None, "traces")}
    return post, valid
