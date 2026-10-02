#!/usr/bin/env python3
"""Validate UME schemas, examples and type definitions.

Usage:  python tools/validate.py [repo_root]
Needs:  pip install "jsonschema>=4.18" pyyaml   (optional: shapely, for polygon validity)
Exits 1 on any error. Suitable for CI.

Checks, in order:
  1. Every *.schema.json is a valid JSON Schema; all are loaded into a local registry by $id.
  2. Each example passes the envelope schema and its payload schema.
  3. Each example meets the normative cross-field rules (R1-R6, R10-R11) and its kind's type definition (R7-R9).
  4. No two examples share a deduplication key (source.id, kind, source.event_id).
"""
import json, re, sys
from datetime import datetime
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
try:
    from shapely.geometry import shape
except ImportError:
    shape = None

root = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent)
sroot = root / "schemas"
errors, warnings, checked = [], [], 0

schemas = {}
for path in sroot.rglob("*.schema.json"):
    doc = json.loads(path.read_text())
    Draft202012Validator.check_schema(doc)
    schemas[doc["$id"]] = doc
registry = Registry().with_resources((i, Resource.from_contents(d)) for i, d in schemas.items())
def validator(sid):
    return Draft202012Validator(schemas[sid], registry=registry, format_checker=FormatChecker())
envelope = validator("urn:schema:fabric:ume:v1")

def ts(v): return datetime.fromisoformat(v.replace("Z", "+00:00"))
def lookup(rec, dotted):
    obj = {"id": rec["id"], "source": rec["properties"]["source"], "payload": rec["properties"]["payload"]}
    for part in dotted.split("."):
        obj = obj[part]
    return obj
def rings(geom):
    t = geom["type"]
    if t == "Polygon": return geom["coordinates"]
    if t == "MultiPolygon": return [r for poly in geom["coordinates"] for r in poly]
    if t == "GeometryCollection": return [r for g in geom["geometries"] for r in rings(g)]
    return []

def positions(geom):
    """Every position in a geometry."""
    if geom is None:
        return []
    if geom["type"] == "GeometryCollection":
        return [p for g in geom["geometries"] for p in positions(g)]
    def walk(c):
        return [c] if isinstance(c[0], (int, float)) else [p for x in c for p in walk(x)]
    return walk(geom["coordinates"])

def has_z(geom):
    return any(len(p) == 3 for p in positions(geom))

def flat(geom):
    """The same geometry with heights removed, for comparing footprints."""
    if geom is None:
        return None
    if geom["type"] == "GeometryCollection":
        return {"type": geom["type"], "geometries": [flat(g) for g in geom["geometries"]]}
    def walk(c):
        return [c[0], c[1]] if isinstance(c[0], (int, float)) else [walk(x) for x in c]
    return {"type": geom["type"], "coordinates": walk(geom["coordinates"])}

def normative_rules(rec, where):
    """R1-R6, R10-R11: rules JSON Schema cannot express."""
    p, g, place = rec["properties"], rec["geometry"], rec.get("place")
    # R1 span times ordered; R2 span datetime equals start
    if p.get("start_datetime") and p.get("end_datetime") and ts(p["end_datetime"]) < ts(p["start_datetime"]):
        errors.append(f"{where}: R1 end_datetime before start_datetime")
    if p.get("start_datetime") and p["datetime"] != p["start_datetime"]:
        errors.append(f"{where}: R2 datetime must equal start_datetime for spans")
    # R3 prism limits ordered
    if place and "lower" in place and "upper" in place and place["lower"] > place["upper"]:
        errors.append(f"{where}: R3 Prism lower > upper")
    # R4 geometry and geometry_source go together; place needs a geometry
    if (g is None) != (p["geometry_source"] is None):
        errors.append(f"{where}: R4 geometry and geometry_source must both be null or both set")
    if place and g is None:
        errors.append(f"{where}: R4 place requires a geometry (the 2D footprint)")
    for label, geom in (("geometry", g), ("Prism base", place["base"] if place else None)):
        if geom is None:
            continue
        # R5 rings closed
        for r in rings(geom):
            if r[0] != r[-1]:
                errors.append(f"{where}: R5 {label} polygon ring not closed")
        # R6 geometry valid (no self-intersection)
        if shape is not None and not shape(flat(geom)).is_valid:
            errors.append(f"{where}: R6 invalid {label}")
        elif shape is None and "R6" not in " ".join(warnings):
            warnings.append("R6 polygon validity not checked (install shapely); PostGIS ST_IsValid also enforces it")
    # R10 all positions in a geometry have the same dimension
    if g is not None and len({len(pt) for pt in positions(g)}) > 1:
        errors.append(f"{where}: R10 geometry mixes 2D and 3D positions")
    # R11 a Prism's base is 2D and is the geometry's footprint
    if place:
        if has_z(place["base"]):
            errors.append(f"{where}: R11 Prism base must be 2D")
        if g is not None and flat(g) != place["base"]:
            errors.append(f"{where}: R11 Prism base must equal the geometry footprint")

def type_rules(rec, td, where):
    """R7-R9: kind-specific rules from type.yaml (time, presence of geometry, z, place, entity, assets)."""
    p, env, g = rec["properties"], td["envelope"], rec["geometry"]
    if p["kind"] != td["kind"] or p["schema"] != td["schema"]:
        errors.append(f"{where}: kind/schema do not match type definition")
    # R7 time type
    if env["time"] == "instant" and (p.get("start_datetime") or p.get("end_datetime")):
        errors.append(f"{where}: R7 instant kind has start/end_datetime")
    if env["time"] == "span" and not p.get("start_datetime"):
        errors.append(f"{where}: R7 span kind needs start_datetime")
    # R8 presence rules
    zval = True if (g is not None and has_z(g)) else None
    for field, value in (("geometry", g), ("z", zval), ("place", rec.get("place")), ("entity_id", p.get("entity_id"))):
        rule = env[field]
        if rule == "required" and value is None:
            errors.append(f"{where}: R8 {field} required for this kind")
        if rule == "forbidden" and value is not None:
            errors.append(f"{where}: R8 {field} not allowed for this kind")
    if g is not None and p["geometry_source"] not in env["geometry_source"]:
        errors.append(f"{where}: R8 geometry_source {p['geometry_source']} not allowed")
    roles = {r for a in rec.get("assets", {}).values() for r in a.get("roles", [])}
    for r in env.get("required_assets", []):
        if r not in roles:
            errors.append(f"{where}: R8 missing required asset role '{r}'")
    # R9 entity_id derived consistently
    tmpl = env.get("entity_id_template")
    if tmpl and p.get("entity_id") is not None:
        expected = re.sub(r"\{([^}]+)\}", lambda m: str(lookup(rec, m.group(1))), tmpl)
        if p["entity_id"] != expected:
            errors.append(f"{where}: R9 entity_id {p['entity_id']} should be {expected}")

types, dedup = {}, {}
for tf in sorted(sroot.glob("kinds/*/type.yaml")):
    td = yaml.safe_load(tf.read_text()); types[td["kind"]] = td
    if td["schema"] not in schemas:
        errors.append(f"{td['kind']}: schema {td['schema']} not found"); continue
    exs = sorted((tf.parent / "examples").glob("*.json"))
    if not exs: errors.append(f"{td['kind']}: no examples")
    payload = validator(td["schema"])
    for ex in exs:
        where = f"{td['kind']}/{ex.name}"; rec = json.loads(ex.read_text()); checked += 1
        env_errs = [f"{where}: envelope: {e.message}" for e in envelope.iter_errors(rec)]
        errors.extend(env_errs)
        errors.extend(f"{where}: payload: {e.message}" for e in payload.iter_errors(rec["properties"]["payload"]))
        if env_errs: continue
        normative_rules(rec, where); type_rules(rec, td, where)
        key = (rec["properties"]["source"]["id"], rec["properties"]["kind"], rec["properties"]["source"]["event_id"])
        if key in dedup: errors.append(f"{where}: duplicate source event {key} (also {dedup[key]})")
        dedup[key] = where

for w in warnings: print("WARN", w)
for e in errors: print("FAIL", e)
print(f"{len(schemas)} schemas, {len(types)} kinds, {checked} examples, {len(errors)} errors")
sys.exit(1 if errors else 0)
