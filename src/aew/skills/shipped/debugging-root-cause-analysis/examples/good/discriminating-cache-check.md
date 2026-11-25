# Good: order-dependent output with a negative control

Synthetic source at snapshot `cache-demo-2`:

```python
cache = {}

def label(item, language):
    if item not in cache:
        cache[item] = {"en": "Book", "fr": "Livre"}[language]
    return cache[item]
```

Reported symptom: calling `label("book", "en")` then `label("book", "fr")` returns `Book` twice. Expected second result: `Livre`.

Competing predictions:

| Explanation | Discriminating prediction |
| --- | --- |
| French lookup is wrong | French fails even after clearing the cache |
| Cache identity omits language | Fresh French succeeds; switching language on a cached item preserves the first language |

Within an authorized isolated interpreter, clear `cache`, run French alone, clear again, then run English followed by French. Repeat in reverse order if needed. Record the returned values and resets. The fresh French call is a negative control for the mixed-language trigger.

Source predicts fresh French is `Livre`, while mixed calls reuse the first value. The proximate failure is a stale-language cache hit; the mechanism is that language affects the value but not the cache key. If executed results match, that mechanism explains both the symptom and control. If execution is unavailable, report these as source-derived predictions and propose the checks.

A regression probe should assert both languages for the same item in one cache lifetime and include fresh-state behavior. Recommending a key that includes language does not authorize changing source.
