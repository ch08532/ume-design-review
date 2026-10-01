# UME design review package

- `ume-design-review.md`: the review and design.
- `schemas/`: envelope (`ume.schema.json`), shared definitions (`common.v1.schema.json`), base schemas (`base/`), and one folder per kind (`kinds/<kind>/`) with payload schema, type definition (`type.yaml`) and examples.
- `tools/validate.py`: validates everything; use in CI.

```
pip install "jsonschema>=4.18" pyyaml shapely
python tools/validate.py
```

Schemas reference each other by URN (`urn:schema:...`), resolved locally, never from the network.
