# Integrating Etiquette

What a Robotoff contributor needs to call Etiquette-1-8B and turn its reading into Robotoff's nutrient fields, without anyone from
FoodClock in the loop. Questions in the discussion thread.

## 1. Serving

**One GPU, BF16 (what the numbers in the README were produced with).** 17.5 GB of weights, any OpenAI-compatible server that
handles Qwen3-VL works. We serve it with llama.cpp in BF16; a vLLM command of this shape should also work (not tested by us):

    vllm serve FoodClockLabs/Etiquette-1-8B --max-model-len 40960 --limit-mm-per-prompt image=6 --port 8080

About 4 to 5 s per product with several photos on one workstation GPU. Memory ~20 GB.

**CPU or laptop, GGUF.** Download the Q4_K_M quant and the mmproj from `mradermacher/Etiquette-1-8B-GGUF`, then

    llama-server -m Etiquette-1-8B.Q4_K_M.gguf --mmproj Etiquette-1-8B.mmproj-f16.gguf -c 40960 -ngl 999 --jinja --port 8080

`-c 40960` matters: a photo can take ~2,400 visual tokens. Expect well over a minute per photo without a GPU. The Q4_K_M quant
scores below BF16 on the whole card (79.9 vs 83.0 on the hundred); the nutrition rows hold up better.

## 2. The request

The model repo holds `system.txt` and `prompt.txt`; send them unchanged with the photos first, then the prompt, one chat completion
per product, `max_tokens` 3000, temperature 0.1 (what the FoodClock worker uses). `run_gguf.py` in the model repo does exactly this with the standard library and is
the reference client:

    python3 run_gguf.py nutrition.jpg front.jpg --url http://127.0.0.1:8080

Send the photos at up to 1568 px on the long side. Up to six photos per product; the nutrition table photo first if you know which
it is, otherwise any order (the model finds the panel).

## 3. The reply

A JSON object. The fields Robotoff cares about:

    {
      "kind": "food",                       # or "not-food"
      "basis": {"per": "100g", "header": "Valeurs nutritionnelles moyennes pour 100 g"},   # per: "100g" | "100ml" | "serving" | "1l" | "prepared"
      "nutriments": {"energy_kj_100g": 979, "energy_kcal_100g": 235, "fat_100g": 18, "saturated_fat_100g": 10,
                     "carbohydrates_100g": 1.3, "sugars_100g": 1.2, "fiber_100g": null, "proteins_100g": 17, "salt_100g": 1.0},
      "sodium_mg": null,                    # only when sodium is printed; never derived from salt
      "rows": {"energy_kj": {"value": 979, "unit": "kJ"}, ...},                  # value + unit as printed, per row; "qualifier": "<" when printed
      "panel_seen": true,
      "product_name": "...", "brand": "...", "quantity": "90 g", "ingredients": {"fr": "..."}, ...
    }

Rules the model was trained to follow, which the integration should rely on:
- A value is only ever what is printed. No kJ from kcal, no salt from sodium, no per-100 g from a serving column.
- `nutriments` keys always end in `_100g` but mean "on the printed basis": read `basis.per` to know whether that is 100 g, 100 ml,
  a serving, a litre or the prepared product. For "serving" the printed header is in `basis.header` and the pack's serving size,
  when printed, in `quantity` or the header text.
- A row the pack does not print is `null`. The schema has a `qualifier` field in `rows` for "<", "≤" and ">", but this version
  usually leaves a row printed as "< 0,5 g" out altogether (22 of its 23 misses on the 199 panels). The next version will emit it.
- `kind` "not-food" means do not use the nutrients.

## 4. Mapping to Robotoff

For each key in `nutriments` with a non-null value, with `suffix = "100g"` if `basis.per` starts with "100" else `"serving"`:

    energy_kj_100g      -> energy-kj_{suffix}      value, unit kJ
    energy_kcal_100g    -> energy-kcal_{suffix}    value, unit kcal
    fat_100g            -> fat_{suffix}            g
    saturated_fat_100g  -> saturated-fat_{suffix}  g
    carbohydrates_100g  -> carbohydrates_{suffix}  g
    sugars_100g         -> sugars_{suffix}         g
    fiber_100g          -> fiber_{suffix}          g
    proteins_100g       -> proteins_{suffix}       g
    salt_100g           -> salt_{suffix}           g
    sodium_mg           -> sodium_{suffix}         value/1000, unit g   (only when printed)
    basis.per "serving"       -> serving_size from `quantity` / `basis.header` when printed

`rows[name].unit` gives the printed unit when it differs (mg for sodium, kcal/kJ for energy). Give each prediction the same
`NutrientPrediction` shape Robotoff builds today; there is no per-token score, so use a constant or `panel_seen`.

## 5. What to expect

- Rotated or sideways tables: the most common Etiquette error class, one row read into its neighbour. If a product has a
  nutrition_xx selected image, send that one first.
- Arabic and other non-Latin tables: read directly from the photo; this is where the OCR route misses most.
- Not food (cosmetics, pet food): `kind` says so; nothing to extract.
- Throughput planning: budget ~5 s per product on one consumer GPU, ~0.06 cent of electricity, no OCR call.
