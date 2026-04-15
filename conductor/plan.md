# Plan: Case-Insensitive Collection Matching

## Objective
Update the `select` method in `components/aer/plugin/selector.py` to perform case-insensitive matching against the collections in `self._collection_index`, without modifying the keys in `self._collection_index` so they retain their original case.

## Implementation Details
1. In `components/aer/plugin/selector.py`, locate the `select` method.
2. Modify the collection matching loop (lines ~184-188).
3. Instead of a direct key lookup (`if collection in self._collection_index:`), iterate over the index keys.
4. Compare each requested collection in lowercase against each indexed collection in lowercase.
5. If a match is found, add the corresponding plugins to `matching_plugins`.

```python
        # Find plugins supporting ANY of the requested collections
        matching_plugins: set[str] = set()
        for requested_collection in collections:
            req_lower = requested_collection.lower()
            for indexed_collection, plugins in self._collection_index.items():
                if indexed_collection.lower() == req_lower:
                    matching_plugins.update(plugins)
```

## Verification
Run tests to ensure the selector logic is still working correctly and the new case-insensitive matching works as expected.
