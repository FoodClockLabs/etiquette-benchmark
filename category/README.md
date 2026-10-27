# Applying an Open Food Facts category to an Etiquette reading

[Etiquette](https://huggingface.co/FoodClockLabs/Etiquette-1-8B) reads what is printed on a pack and returns no
category, on purpose: a reader that also classifies starts guessing. Filing the reading is a separate, text-only step,
and this folder is that step, the same code FoodClock runs behind its own contributions to Open Food Facts.

Two files, no dependencies beyond Python 3.9:

| file | what it does |
|---|---|
| `off_taxonomy.py` | fetches the Open Food Facts category taxonomy from the openfoodfacts-server repository on first use, caches it beside the file, parses it with OFF's own id rule, and reports the upstream commit it loaded |
| `categorize.py` | two short calls to any chat model behind an OpenAI-compatible endpoint: name the family, then pick the deepest category under it that certainly fits |

```
# an Ollama on this machine, any capable instruct model
python categorize.py reading.json --model gemma4:31b --endpoint http://localhost:11434/v1

# or straight from the facts
python categorize.py --name "Verse volle yoghurt" --brand "Albert Heijn" --quantity "1 l" --ingredients "volle yoghurt (van weidemelk)"
```

The output is one category id with a confidence and a one-line reason, plus the taxonomy source (URL, fetch time,
upstream commit) so a result can be reproduced:

```json
{"category": "en:plain-cow-milk-yogurts", "coarse": "en:yogurts", "confidence": "high",
 "reason": "The ingredients are only whole milk yoghurt, with no flavour or added sugar.", "candidates": 23,
 "taxonomy": {"url": "https://raw.githubusercontent.com/openfoodfacts/openfoodfacts-server/main/taxonomies/food/categories.txt",
              "fetched_at": "2026-10-27T15:02:11Z", "upstream_commit": "..."}}
```

## Hints and tips, from a few thousand cards

**Go to the leaf.** Open Food Facts' value sits at the deepest category: the Nutri-Score computation, "compare with
similar products", Eco-Score and every study that picks representative products count there. "Cheeses" is true and
nearly useless; "firm cheese around 27% fat, Maasdam-type" is what the record wants. The edit form says it in its own
words: "Indicate only the most specific category. Parent categories will be added automatically."

**Never let the model invent an id.** Models remember ids that look right and do not exist ("en:vegetable-soup";
the node is "en:vegetable-soups"). Resolve every guess against the taxonomy, offer the model only real candidates,
and treat anything outside the list as "keep the parent". `off_taxonomy.resolve()` does the first part;
`categorize.py` does the rest.

**Only facts the pack states.** A flavour, a process (frozen, canned, cooked, dried) or a fat level that is not on
the label is a guess; the prompt forbids it and "keep" is the right answer when the leaf needs a fact you do not
have. A sugar-free fruit drink belongs in "still fruit soft drink without sugar and with sweeteners" only when the
ingredients list the sweetener.

**Add, do not replace.** When writing to Open Food Facts use `add_categories`, which merges, never the plain
`categories` parameter, which deletes other contributors' tags. Wrong existing tags (a plain yoghurt filed under
skyrs, a fruit drink filed as juice) are a human's edit on the product page, with a change summary that names the
fact on the pack.

**Read the whole subtree, rank by the pack's own words.** A parent such as "cheeses" has far more than sixty
descendants. Score candidates by word overlap between their names (English and the pack's language) and the
reading's name, brand and ingredients, show the matching deep nodes first, then the direct children, and cap the
list; the model reads sixty lines well and three hundred badly.

**A person confirms.** The model proposes; whoever signs the contribution decides. Keep the coarse category beside
the leaf in your own records so a reviewer sees both.

## Licence and attribution

This code: Copyright 2026 FoodClock (FoodClock Labs), Apache-2.0, as the rest of this repository.

The category taxonomy belongs to Open Food Facts and lives in the
[openfoodfacts-server](https://github.com/openfoodfacts/openfoodfacts-server/tree/main/taxonomies/food) repository,
which is licensed AGPL-3.0; Open Food Facts' product data is under the ODbL. Nothing from the taxonomy is
redistributed here: the loader fetches the current file from upstream for you and keeps your copy beside the code.
Credit Open Food Facts when you publish categories produced with it, as we do. Open Food Facts is a trademark of the
Open Food Facts association; FoodClock Labs is not affiliated with or endorsed by it.
