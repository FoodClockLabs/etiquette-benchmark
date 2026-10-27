"""Open Food Facts category taxonomy: fetch, parse, walk.

The taxonomy is a text file in the openfoodfacts-server repository. This module downloads it when first asked and
keeps a local copy next to this file (taxonomy_cache/), so that nothing is redistributed here: every user holds their
own copy from upstream, and `source()` reports which commit it came from so a result can be reproduced.

    from off_taxonomy import Taxonomy
    tax = Taxonomy.load()                 # fetches once, then reads the cache
    tax.resolve("en:vegetable-soup")      # -> "en:vegetable-soups"
    tax.children("en:cheeses")            # direct children
    tax.descendants("en:cheeses", 6)      # (id, depth) pairs, breadth first
    tax.name(id, "nl")                    # a display name in a language, falling back to English
"""
import json
import os
import re
import time
import unicodedata
import urllib.request

RAW = "https://raw.githubusercontent.com/openfoodfacts/openfoodfacts-server/main/taxonomies/food/categories.txt"
COMMITS = "https://api.github.com/repos/openfoodfacts/openfoodfacts-server/commits?path=taxonomies/food/categories.txt&per_page=1"
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "taxonomy_cache")
UA = {"User-Agent": "etiquette-category/1.0 (+https://github.com/FoodClockLabs/etiquette-benchmark)"}
PROPS = {"synonyms", "stopwords", "wikidata", "ciqual_food_code", "agribalyse_food_code", "pnns_group_2", "country",
         "instanceof", "region", "origins", "agribalyse_proxy_food_code", "nutriscore", "nova", "description",
         "comment", "expected_nutriscore_grade", "intake24_category_code", "ciqual_proxy_food_code",
         "incompatible_with", "season_in_country", "protected_name_type", "grapevariety", "packaging_materials",
         "packaging_shapes", "image_sizes", "agribalyse_food_name", "expected_ingredients", "wikipedia", "taxonomy",
         "alcohol_by_volume", "language", "carbon_footprint_fr_foodges_ingredient", "carbon_footprint_fr_foodges_proxy",
         "ciqual_food_name", "gpc_category_code", "gpc_category_name", "nutri_score_category", "vegan", "vegetarian",
         "wikidata_category", "hs_code", "agribalyse_proxy_food_name", "pnns_group_1", "pnns_group_2_en"}


def slug(s):
    """OFF's id rule: fold accents, lowercase, runs of non-word characters become '-'; non-Latin scripts keep their letters."""
    s = "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch)).lower()
    return re.sub(r"[^\w]+", "-", s, flags=re.UNICODE).replace("_", "-").strip("-")


def ref_id(ref):
    m = re.match(r"^\s*([a-z]{2,3})\s*:\s*(.+?)\s*$", ref or "")
    return (m.group(1) + ":" + slug(m.group(2))) if m else None


def parse(text):
    entries, cur = [], None
    def flush():
        nonlocal cur
        if cur and cur.get("id"):
            entries.append(cur)
        cur = None
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            flush(); continue
        if line.startswith("#"):
            continue
        if cur is None:
            cur = {"parents": [], "names": {}, "id": None}
        if line.startswith("<"):
            r = ref_id(line[1:])
            if r: cur["parents"].append(r)
            continue
        m = re.match(r"^([a-z]{2,3}):\s*(.*)$", line)
        if not m or m.group(1) in PROPS or "_" in m.group(1):
            continue
        names = [n.strip() for n in m.group(2).split(",") if n.strip()]
        if not names:
            continue
        cur["names"][m.group(1)] = names
        if cur["id"] is None:
            cur["id"] = m.group(1) + ":" + slug(names[0])
    flush()
    seen, out = set(), []
    for e in entries:
        if e["id"] in seen or e["id"].endswith(":"):
            continue
        seen.add(e["id"]); out.append(e)
    ids = {e["id"] for e in out}
    for e in out:
        e["parents"] = [p for p in e["parents"] if p in ids]
    return out


class Taxonomy:
    def __init__(self, entries, source):
        self.by_id = {e["id"]: e for e in entries}
        self.kids = {}
        for e in entries:
            for p in e["parents"]:
                self.kids.setdefault(p, []).append(e["id"])
        self.source_info = source

    @classmethod
    def load(cls, max_age_days=7):
        os.makedirs(CACHE, exist_ok=True)
        f = os.path.join(CACHE, "categories.txt"); meta = os.path.join(CACHE, "source.json")
        fresh = os.path.exists(f) and (time.time() - os.path.getmtime(f)) < max_age_days * 86400
        if not fresh:
            text = urllib.request.urlopen(urllib.request.Request(RAW, headers=UA), timeout=120).read().decode("utf-8")
            if text.count("\nen:") < 5000:
                raise RuntimeError("taxonomy fetch looks truncated; keeping the cached copy" if os.path.exists(f) else "taxonomy fetch failed")
            open(f, "w", encoding="utf-8").write(text)
            src = {"url": RAW, "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
            try:
                c = json.load(urllib.request.urlopen(urllib.request.Request(COMMITS, headers=UA), timeout=30))
                src["upstream_commit"] = c[0]["sha"]; src["upstream_date"] = c[0]["commit"]["committer"]["date"]
            except Exception:
                pass
            json.dump(src, open(meta, "w"))
        source = json.load(open(meta)) if os.path.exists(meta) else {"url": RAW}
        return cls(parse(open(f, encoding="utf-8").read()), source)

    def source(self):
        return self.source_info

    def name(self, cid, lang="en"):
        e = self.by_id.get(cid)
        if not e: return cid
        for l in (lang, "en"):
            if e["names"].get(l): return e["names"][l][0]
        return next(iter(e["names"].values()))[0]

    def resolve(self, guess):
        """A model's informal id ('en:vegetable-soup', 'cheese') onto a real node, or None."""
        c = (guess or "").strip().lower()
        if not c: return None
        if ":" not in c: c = "en:" + c
        for cand in (c, c + "s", c[:-1] if c.endswith("s") else c, c + "es"):
            if cand in self.by_id: return cand
        word = c.split(":", 1)[1].replace("-", " ")
        for e in self.by_id.values():
            for l in ("en", "nl", "fr", "de"):
                for n in e["names"].get(l, []):
                    if n.lower() in (word, word + "s"): return e["id"]
        return None

    def children(self, cid):
        return list(self.kids.get(cid, []))

    def descendants(self, cid, max_depth=6):
        out, seen, frontier = [], set(), [(cid, 0)]
        while frontier:
            node, d = frontier.pop(0)
            if d >= max_depth: continue
            for k in self.kids.get(node, []):
                if k in seen: continue
                seen.add(k); out.append((k, d + 1)); frontier.append((k, d + 1))
        return out

    def is_descendant(self, cid, root):
        return any(k == cid for k, _ in self.descendants(root, 12))
