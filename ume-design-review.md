# UME Design Review

Review of the **Universal Metadata Envelope (UME) Design** against the Data Fabric architecture and its design principles.

## Contents

1. [Summary](#1-summary)
2. [Design principles reference](#2-design-principles-reference)
3. [The envelope concept](#3-the-envelope-concept)
4. [What works well](#4-what-works-well)
5. [Priority findings](#5-priority-findings)
6. [Detailed findings](#6-detailed-findings)
7. [Classification and labelling](#7-classification-and-labelling)
8. [Proposed revised UME](#8-proposed-revised-ume)
9. [Controlled lists and standards](#9-controlled-lists-and-standards)
10. [Schema catalogue](#10-schema-catalogue)
11. [Worked examples](#11-worked-examples)
12. [Vertical model](#12-vertical-model)

---

## 1. Summary

The UME design is a strong foundation and closely matches the envelope concept for the Data Fabric (section 3): a fixed set of fields on every record, a schema reference for type-specific content, Atom/OGC-style links for references and lineage, a security label on every record, and URN identifiers for offline operation.

The main issues are:

- **Track-specific fields are built into the envelope**, which turns a universal envelope into a track record with extras.
- **The time model records pipeline stages but not when things actually happened**, and has no start/end interval.
- **Several fields don't work in a distributed deployment** (global counter, integer source IDs, node-local track IDs).
- **Some fields change after writing** (`lifecycle`, `storage_tier`, `next`/`previous` links), which conflicts with append-only history.
- **Client-facing URLs are stored in the data**, tying storage to one API.
- **The classification block needs a more general structure**, fail-closed defaults, and rules for derived data.

Most of these are easy to fix now and much harder once data is stored in the current shape. Sections 8 to 12 give the revised envelope, a schema catalogue for fourteen kinds, worked examples and the vertical model. The structure is already close to a **GeoJSON Feature / STAC Item**; adopting that shape would bring direct OGC API compatibility.

---

## 2. Design principles reference

Findings are mapped to the Data Fabric design principles using these codes:

| Code | Principle | Summary |
|---|---|---|
| **DP1** | Separate data storage from data access | Store data in the medium best for the data; serve it in the medium best for the client |
| **DP2** | Everything is spatiotemporal | Location and time are first-class; everything can be queried on time and space. Proposed rewording, to be confirmed by the principle owners: everything has time; anything with a location can be queried in space. |
| **DP3** | Distributed by design | Nodes from edge to cloud; configurable synchronization |
| **DP4** | Open architecture with standards support | Open standards for APIs, formats, protocols; integrate without forcing changes |
| **DP5** | Designed for redundancy and recovery | Replicate critical data; restore quickly after failure |
| **DP6** | Bring your own data model and ontology | Types defined by configuration; no forced canonical model |
| **DP7** | Provenance, lineage and versioning built-in | Where data came from, how it changed, what it was derived from |
| **DP8** | Zero-trust security | Authenticate and authorize everything; least privilege; encryption by default |

---

## 3. The envelope concept

The review is based on one core idea: every piece of data is split into two parts.

- **The envelope:** a small, fixed outer layer that is the same for every type of data.
- **The payload:** the inner content, whose shape depends on what the data is and is defined by a registered schema.

### 3.1 The analogy

A postal envelope always carries the same things on the outside: address, return address, postmark, and perhaps a "Confidential" stamp. The postal system can sort, route, track and store any letter using only the outside, without opening it or caring whether it holds a bill or a birthday card. Only the recipient reads what's inside.

The Data Fabric works the same way. Storage, routing, synchronization, security and lineage all operate on the envelope. Only services that care about a specific type read its payload.

### 3.2 What goes in the envelope

| Field | Why the platform needs it | Principles |
|---|---|---|
| ID | Unique identity, deduplication, references | DP3, DP7 |
| Kind and schema | Which type this is; how to validate and read the payload | DP6 |
| Entity ID | Groups records about the same thing (a track, an alert); latest-state views | DP7 |
| Time (when it happened, start/end) | Time queries, ordering, retention | DP2 |
| Geometry (2D, where the kind has a location) | Space queries, map display | DP2 |
| Height range | Vertical and airspace queries across types | DP2 |
| Source (stable device ID), node and source event ID | Routing, sync rules, trust, deduplication | DP3, DP5, DP8 |
| Provenance | What it came from, what produced it | DP7 |
| Security label | Access decisions, replication limits | DP8 |
| Links / assets | Pointers to files and related records | DP1, DP7 |

### 3.3 What goes in the payload

Everything specific to the type: a track's callsign and speed, an image's resolution and bands, an alert's rule and severity. Adding a new type means registering a schema and a type definition (section 10), not changing the platform.

### 3.4 The rule for deciding

> If a platform service needs a field to store, index, route, sync, secure or trace a record **without knowing its type**, it belongs in the envelope. Everything else belongs in the payload.

A callsign fails this test, because only track-aware services care about it. A security label passes, because every service that touches the record must respect it. This rule is the basis of finding PF1 (move track fields out of the envelope).

Keep the envelope small. Every envelope field is one that every type must provide, and the envelope is the hardest part of the design to change later.

### 3.5 Benefits by principle

| Principle | How the envelope supports it | Example |
|---|---|---|
| **DP1** Separate storage from access | Storage and APIs handle generic envelopes and change independently | A video segment moves to cold storage; GSS serves it from the same endpoint with a fresh link. |
| **DP2** Everything is spatiotemporal | Time and geometry on every record | "Everything within 5 km of the substation, 14:00–14:30" returns tracks, video, imagery and alerts in one query. |
| **DP3** Distributed by design | Sync and routing use envelope fields only | Edge sync: `alert.*` immediately, `track.fused` at 1 Hz, `video.segment` on request, nothing not releasable to the destination. |
| **DP4** Open architecture | Maps onto CloudEvents, GeoJSON/STAC and OGC API Features | Partners open tracks in QGIS and search imagery with a STAC browser, with no custom integration. |
| **DP5** Redundancy and recovery | Replication and retention apply to all types alike | One job purges `track.raw` after 5 minutes and keeps `track.fused` for 90 days, using only `kind`. |
| **DP6** Bring your own data model | New types are configuration | Adding `maritime.vessel` takes a schema, an index on `mmsi` and an OGC collection; no code. |
| **DP7** Provenance and lineage | Lineage recorded the same way for every type | Track 9421 traces back to its radar and Remote ID inputs; an ML detection traces back to its video segment. |
| **DP8** Zero trust | One label format, one policy engine (OPA, 7.1) | A newly registered type is protected from its first record, with no new security code. |

### 3.6 Logical model and representations

The envelope is a **logical model**: a set of fields and rules, independent of any format. Each part of the platform uses a representation suited to it, mapped from the same model:

```
                     UME logical model
                            │
          ┌─────────────────┼──────────────────┐
          │                 │                  │
   JSON profile        Messaging            SQL model
   (GeoJSON Feature)   (CloudEvents +       (envelope columns
          │             NATS subject)        + jsonb payload)
   OGC API / STAC           │                  │
                          NATS              Postgres / Iceberg
```

The JSON profile (`ume.schema.json`) is normative for JSON, but GeoJSON is a representation of the model, not the model itself. This keeps DP1 intact: storage, messaging and APIs each use their own form.

| Logical field | JSON profile | Messaging | SQL |
|---|---|---|---|
| Record ID | `id` | `ce-umeid` (extension) | `id uuid` |
| Kind | `properties.kind` | `ce-type`; NATS subject token | `kind text` |
| Event time / span | `datetime`, `start_datetime`, `end_datetime` | `ce-time` (`datetime`) | `timestamptz` columns |
| Footprint (2D) | `geometry` | Payload | `geom geometry(Geometry, 4326)` |
| Vertical extent | `height_range` | Payload | `height numrange` |
| Entity | `entity_id` | `ce-subject` | `entity_id text` |
| Source and node | `source.id`, `source.node` | `ce-source`; NATS subject token (node) | `source_id`, `node_id` |
| Source event (dedup key) | `source.event_id` | `ce-id`; `Nats-Msg-Id` (hash of source + event ID) | Unique index on `(source_id, event_id)` |
| Kind schema | `properties.schema` | `ce-dataschema` | `schema_ref text` |
| Security label | `security` | `ce-label` (extension) | Label columns |
| Provenance | `provenance` | Payload | `provenance jsonb` + `ume_link` projection |
| Payload | `payload` | Message body | `payload jsonb` |

The GeoJSON profile can still write a third coordinate for clients that expect it (for example Cesium), generated from `height_range` when it's a single height.

**CloudEvents** is the messaging representation's metadata format. It's a graduated CNCF specification that defines a standard set of event attributes (`id`, `source`, `type`, `time`, `subject`, `dataschema`, plus custom extensions), with bindings for NATS, Kafka, MQTT, AMQP and HTTP. In **binary mode** the attributes travel as message headers prefixed `ce-` and the record is the body, so services and gateways can read an event's type, source, time and label without parsing it, and tools that already understand CloudEvents can consume the data directly.

```
Subject:  fabric.track.fused.site-a
Headers:  ce-specversion: 1.0
          ce-id: site-a:9421:118734
          ce-source: urn:source:omnitrack-01
          ce-type: track.fused
          ce-time: 2026-09-23T17:46:01.200Z
          ce-subject: urn:track:site-a:9421
          ce-dataschema: urn:schema:tracks:fused-kinematics:v1
          ce-umeid: urn:uuid:01926f3a-8e10-7c32-b7e1-8890cf2b6941
Body:     the record
```

CloudEvents treats two events with the same `source` and `id` as duplicates, so `ce-id` carries `source.event_id`, not the record ID. That makes CloudEvents' deduplication rule and the platform's (A9) the same thing. The record ID travels as the extension `ce-umeid`. Brokers don't route on these headers; routing uses subjects and topics (6.8, M2).

---

## 4. What works well

| Strength | Principles |
|---|---|
| Fixed envelope with schema-defined `properties` | DP6 |
| Multiple timestamps (source, broadcast, receive, store) enabling latency analysis | DP2, DP5 |
| Atom/OGC link relations (`enclosure`, `preview`, `alternate`, `service`) | DP1, DP4 |
| `derivedfrom` links for record-level lineage, including multiple inputs for fused tracks | DP7 |
| URNs as identifiers rather than network locations; embedded schema cache | DP3, DP4 |
| Local CRS resolution through PROJ/GDAL, no remote lookups | DP3 |
| Security label on every record, including releasability | DP8 |
| `sha256` for integrity | DP7, DP8 |
| GeoJSON geometry types | DP2, DP4 |

---

## 5. Priority findings

| ID | Finding | Recommendation | Principles |
|---|---|---|---|
| **PF1** | Track fields (`spatial.track`) are part of the universal envelope; every non-track UME carries empty track columns. | Move them into a payload schema (`urn:schema:tracks:fused-kinematics:v1`). Ship tracks as a default type, not part of the envelope. | DP6, DP2 |
| **PF2** | Raw binary track data is stored base64 in the envelope: about a third larger, and bloats history at sensor rates. | Send raw data on the backbone. If kept, batch it to object storage as an asset, or use a short-retention raw table. | DP1, DP5, DP3 |
| **PF3** | No time for when the event happened (`sourced_at` is when the source *received* data), and no start/end for spans. | Add `datetime`, `start_datetime`, `end_datetime`; group pipeline times separately (6.1). | DP2, DP7 |
| **PF4** | 3D coordinates labelled `EPSG:4326` (2D, lat/lon order); `altitude_type` changes what height means per record. | 2D lon/lat geometry plus a separate `height_range`, both WGS84 (S1, section 12). Convert at ingest; pressure altitude in the payload. | DP2, DP4 |
| **PF5** | `index` is a global counter: needs a central sequence, breaks when nodes disconnect, and appears in two places. | Remove it. Use UUIDv7 record IDs (PostgreSQL 18 has `uuidv7()`), and deduplicate on a separate source event ID (A9). | DP3, DP5 |
| **PF6** | Close to a GeoJSON Feature / STAC Item but not one, so GSS must translate. | Make the UME a GeoJSON Feature (`type`, `id`, `geometry`, `properties`, `links`, `assets`). | DP4, DP1 |

---

## 6. Detailed findings

Each subsection has a summary table, then short notes on why each change matters and how to do it.

### 6.1 Temporal

| ID | Finding | Recommendation | Principles |
|---|---|---|---|
| T1 | No field for when the event happened. | Add `datetime`. | DP2 |
| T2 | No interval for things that span time. | Add `start_datetime` / `end_datetime`. | DP2 |
| T3 | `observed_at` means receive time here, but phenomenon time in most standards. | Rename to `received_at`. | DP2, DP4 |
| T4 | `broadcasted` naming. | Rename to `sent_at`. | — |
| T5 | `valid_until` mixes validity with retention. | Retention per kind; `expires_at` for overrides. | DP5 |
| T6 | Partition column not specified. | Partition on `datetime`. | DP2 |
| T7 | Latency compares clocks on different machines. | Synchronized time on all sources and nodes. | DP3 |

**T1. Add `datetime`.**
*Why:* "Where was this drone at 14:00?" is about when it happened. All current fields include pipeline delay.
*How:* Take it from the source message (ASTERIX Time of Applicability, KLV timestamp, capture time). If the source has none, fall back to `times.source_at` and flag it (`time_source: "source_at"`).

**T2. Add `start_datetime` / `end_datetime`.**
*Why:* Video segments, imagery passes and outages span time; one instant can't answer "what covers 14:00–14:05?".
*How:* Null for instants. For spans, set the start and set `datetime` to it so the partition column is never empty. Leave the end null while it's unknown (a recording in progress, a permanent zone).

```sql
SELECT * FROM ume
WHERE kind = 'video.segment'
  AND start_datetime < '2026-09-23T14:05Z'
  AND (end_datetime IS NULL OR end_datetime > '2026-09-23T14:00Z');
```

**T3 / T4. Rename pipeline times.**
*Why:* "Observed" means phenomenon time to integrators; mixed tenses read badly.
*How:* Group under `times`: `source_at`, `sent_at`, `received_at`, `stored_at`. Latency checks carry over:

| Delay | Calculation |
|---|---|
| Source | `sent_at - source_at` |
| Network | `received_at - sent_at` |
| Ingestion | `stored_at - received_at` |
| End to end | `stored_at - datetime` |

**T5. Separate validity from retention.**
*Why:* Expiring raw tracks is retention. Validity (a zone active until 18:00) belongs in `end_datetime`.
*How:* Set retention per kind in platform configuration; use `expires_at` only for per-record overrides. TimescaleDB drops whole chunks, so put short-lived kinds like `track.raw` in their own hypertable with small chunks.

**T6. Partition on `datetime`.**
*Why:* Most queries filter on event time, so TimescaleDB can skip chunks.
*How:* `create_hypertable('ume', 'datetime')`. If compressing, wait longer than the longest expected outage (for example 7 days) so late data doesn't land in compressed chunks.

**T7. Synchronize clocks.**
*Why:* A 2-second clock error makes delays negative and lets old data overwrite new.
*How:* chrony on every node, GPS or PTP where available. Monitor clock offset and alert on drift. Never rewrite timestamps silently.

### 6.2 Spatial

| ID | Finding | Recommendation | Principles |
|---|---|---|---|
| S1 | 3D coordinates labelled `EPSG:4326`; axis order and height datum vary. | 2D lon/lat geometry plus a separate vertical extent (`height_range`), both WGS84. | DP2, DP4 |
| S2 | `spatial` may be null, with no rule for when. | Geometry required, optional or forbidden per kind; real locations only. | DP2 |
| S3 | Unparsed raw message has a position. | Use the sensor's location. | DP2, DP7 |
| S4 | `confidence` undefined. | `position_error_m`. | DP2 |
| S5 | `domain` mixes physical and non-physical categories. | Physical domains only. | DP2, DP4 |
| S6 | No units; "bearing" ambiguous. | SI units in field names. | DP4 |
| S7 | `track_id` unique only per Trackgen. | Namespace by node. | DP3 |
| S8 | No vertical extent for volumes (UTM volumes, NOTAMs, zones). | `height_range` on every record with a height (section 12). | DP2, DP6 |

**S1. Horizontal and vertical kept separate.**
*Why:* Mixed axis order or height datums put positions in the wrong place without any error. Mixing 3D points with 2D footprints plus ranges gives two vertical models.
*How:* Geometry is always 2D lon/lat (OGC:CRS84); height is always `height_range` in WGS84 ellipsoidal metres (together, EPSG:4979). Adapters convert with PROJ at ingest (MSL heights need a geoid model such as EGM2008). Store as `geometry(Geometry, 4326)` plus `height numrange`. Keep the original CRS and altitudes in the payload if needed.

**S2. Geometry per kind, real locations only.**
*Why:* Not every record has a location (configuration changes, audit events, alert acknowledgements). Giving them a stand-in location (such as the processing node) would make them appear in spatial queries they have nothing to do with.
*How:* Each kind's type definition says `geometry: required | optional | forbidden`. When geometry is present, `geometry_source` says where it came from; when it's null, so is `geometry_source`:

| Location | `geometry_source` |
|---|---|
| The data's own position or footprint | `observed` |
| Declared or planned area (volume, zone, NOTAM) | `defined` |
| Sensor coverage area | `sensor_coverage` |
| Sensor location | `sensor` |
| Mission area of interest | `aoi` |

There is no node-location fallback. Adapters get sensor locations and coverage from the source registry (A5).

**S3. Raw messages use the sensor's location.**
*Why:* An unparsed message has no known target position; a placeholder corrupts spatial queries.
*How:* `geometry_source: "sensor_coverage"` or `"sensor"`. The parsed or fused record carries the real position.

**S4. Position error in metres.**
*Why:* A 0.95 score can't be compared across sources or used by fusion.
*How:* `position_error_m` with one meaning (horizontal 95% radius). ADS-B and Remote ID accuracy categories convert directly. Covariance and other confidences go in the payload.

**S5. Physical domains only.**
*Why:* LOGISTICS or ENVIRONMENTAL describe what data is about, which `kind` already covers.
*How:* AIR, LAND, SEA_SURFACE, SUBSURFACE, SPACE, optionally aligned with APP-6 / MIL-STD-2525. Null otherwise.

**S6. Units in field names.**
*Why:* 210.5 could be m/s, knots or km/h; "bearing" could be course, heading or direction from a sensor.
*How:* `ground_speed_mps`, `course_deg` (true north, clockwise), `heading_deg`, `vertical_rate_mps` (positive up). Aviation conventions are fine if the unit is named (`pressure_altitude_ft`).

**S7. Namespaced track IDs.**
*Why:* Two sites will both produce track 9421; at the core they merge wrongly.
*How:* `site-a:9421`. Core cross-site fusion uses its own namespace (`core:118`) and lists site tracks in `derived_from`. The UI can still show a short number.

**S8. Vertical extent.**
*Why:* Airspace queries need heights across NOTAMs, UTM volumes, zones and tracks; GeoJSON footprints are 2D.
*How:* `height_range` in WGS84 ellipsoidal metres: a single height for points, a conservative range for volumes, originals kept in the payload. Full design in section 12.

### 6.3 Reference links

| ID | Finding | Recommendation | Principles |
|---|---|---|---|
| L1 | `self` and client URLs stored in data. | Store internal identifiers; generate URLs when serving. | DP1 |
| L2 | `next` / `previous` need post-write updates. | Derive by query. | DP7, DP1 |
| L3 | Reverse lineage needs a JSON scan. | `ume_link` table. | DP7 |
| L4 | `derivedfrom` not a registered relation; files, lineage and links overlap. | One home for each: files in `assets`, lineage in `provenance`, stored links for services only. | DP4, DP7 |
| L5 | `length` meaningless for record links. | Optional; size goes on assets. | — |

**L1. Generate client URLs at the access layer.**
*Why:* Stored URLs go stale, differ per client (OGC, STAC, TAK, video player), and can't expire.
*How:* Store `s3://` and `urn:` references only. GSS adds `self` and turns `s3://` into short-lived presigned URLs after the access check.

**L2. Derive `next` / `previous`.**
*Why:* The next segment doesn't exist when a segment is written; updating later breaks append-only history.
*How:* Compute when serving:

```sql
SELECT id,
       lag(id)  OVER w AS previous_id,
       lead(id) OVER w AS next_id
FROM ume
WHERE kind = 'video.segment' AND source_id = :source
WINDOW w AS (ORDER BY start_datetime);
```

**L3. Link table for lineage.**
*Why:* "What came from this radar message?" shouldn't scan every row.
*How:* The DB writer fills `ume_link` from `derived_from` and `revision_of`, indexed both ways:

```sql
SELECT from_id FROM ume_link WHERE to_ref = :id AND rel = 'derived_from';
```

**L4. Registered relation names.**
*Why:* Standard clients understand standard links.
*How:* Each relationship has exactly one stored form, so two copies can't disagree. Files are `assets`; lineage is `provenance.derived_from` and `revision_of`. Stored links are limited to `service`, `related`, `alternate` and `describedby` (IANA). GSS generates `self`, `next`, `prev`, `derived_from` (STAC) and `predecessor-version` (IANA) links when serving, from the canonical fields.

**L5. Optional `length`.**
Size belongs on file assets (`file:size`, A1).

### 6.4 Asset descriptor

| ID | Finding | Recommendation | Principles |
|---|---|---|---|
| A1 | Record and file metadata mixed. | STAC-style `assets`; `schema` and source at top level. | DP6, DP4 |
| A2 | Type described three times. | One `kind` plus media type on assets. | DP6 |
| A3 | `lifecycle` mixes form and state. | Form in `kind`, state in a state table. | DP6 |
| A4 | `lifecycle`, `storage_tier` change after writing. | Keep mutable state out of history. | DP7, DP1 |
| A5 | Integer `source_id` collides across nodes. | Stable URN per device, node recorded separately, plus a source registry. | DP3 |
| A6 | Hash input undefined. | Hash asset bytes, as a multihash. | DP7, DP8 |
| A7 | Invalid example hashes. | Fix; use as test fixtures. | — |
| A8 | Asset UUID duplicates UME UUID. | Only shared files need an ID. | — |
| A9 | No way to recognise the same source event arriving twice. | `source.event_id`, derived from source-native data. | DP3, DP5 |

**A1. Separate record and file metadata.**
*Why:* A record may have no files (track), one (image) or several (video plus thumbnail plus HLS).
*How:* Assets keyed by role:

```json
"assets": {
  "data":      { "href": "s3://mission-lake/fmv/cam-03/2026/09/23/174510.ts",
                 "type": "video/mp2t", "file:size": 18874368, "file:checksum": "sha256:..." },
  "thumbnail": { "href": "s3://mission-lake/previews/cam-03/174510.jpg", "type": "image/jpeg" }
}
```

**A2. One `kind`.**
*Why:* "image/geotiff" is a format, not a meaning; three type fields will drift.
*How:* Registered dot-separated kinds (`track.raw`, `track.fused`, `imagery.ortho`, `video.segment`), each mapped to its schemas and configuration.

**A3. Separate form from state.**
*Why:* "Raw" is permanent; "processing" is temporary.
*How:* Form in `kind`, state in the state table (A4).

**A4. Keep mutable state out of history.**
*Why:* Updates break append-only storage and cause replication conflicts.
*How:* Write the UME once its asset is ready; track in-progress work in a job or `ume_state` table. Archived records move to Iceberg whole, so the tier is known from where they live.

**A5. URN source IDs and a source registry.**
*Why:* Site-assigned integers clash at the core. Putting the site in the ID would make a receiver moved from site A to site B look like a new source, and mobile sensors move constantly.
*How:* `urn:source:flightline-0037` names the device or producing service and never changes; `source.node` records where this record was ingested. The registry holds each source's type, location, coverage and label; adapters use it for labels (7.4) and locations (S2).

**A6. Hash the bytes.**
*Why:* JSON serializes many ways, so its hash isn't reproducible.
*How:* `file:checksum` over the file bytes, as a SHA2-256 multihash (`1220` + hex), as the STAC File extension expects; verify on transfer and serving. `config_hash` uses the same format. Use signatures (V5) for record integrity, or RFC 8785 canonical JSON if a record hash is required.

**A9. Source event identity.**
*Why:* The record ID is generated by whoever creates the record. If a site adapter and a core adapter both receive the same sensor message, or a node replays data after reconnecting, the same event gets two different record IDs, so the record ID can't detect duplicates.
*How:* `source.event_id` identifies the event itself, unique per `source.id`, and is derived from source-native data so every adapter computes the same value: a native message ID or sequence (ASTERIX SAC/SIC plus sequence), a natural key (operational intent, version and state), or a content hash when nothing else exists. Each kind's type definition documents its rule. `(source.id, event_id)` is the deduplication key: a unique index in Postgres, and the basis of `Nats-Msg-Id` on the backbone.

**A7. Fix examples.**
Correct them and validate them against the schemas in CI.

**A8. Asset IDs only where shared.**
Identify assets by reference and checksum; add an ID on the asset only if several records share it.

### 6.5 Provenance and versioning

| ID | Finding | Recommendation | Principles |
|---|---|---|---|
| V1 | Producer version and config not recorded. | `producer_version`, `config_hash`. | DP7 |
| V2 | No link to previous versions, and no distinction between corrections and state changes. | `revision_of` for corrections only; state changes as their own records, linked by `entity_id`. | DP7 |
| V3 | Operator edits undefined. | Edits as records. | DP7 |
| V4 | Custom lineage terms. | Map to W3C PROV. | DP7, DP4 |
| V5 | Provenance not tamper-evident. | Sign at the producer. | DP7, DP8 |

```json
"provenance": {
  "origin": "urn:source:flightline-0037",
  "derived_from": ["urn:uuid:...", "urn:uuid:..."],
  "revision_of": null,
  "produced_by": "omnitrack-engine",
  "producer_version": "3.4.1",
  "producer_org": "urn:org:dnd",
  "config_hash": "1220..."
}
```

**V1. Producer version and config.**
*Why:* Explains why the same inputs gave different outputs; essential for incident review.
*How:* Each producer stamps version and a hash of its effective configuration; configurations live in Git so the hash can be looked up.

**V2. Observations, revisions and state transitions.**
*Why:* These are three different things. Treating a state change as a revision would claim the earlier record was wrong, when it was right at the time.

| Concept | Meaning | Recorded as | Example |
|---|---|---|---|
| Observation or event | Something new happened | New record, same `entity_id` | A track position update |
| Revision | An earlier record was wrong, or is superseded | New record with `revision_of` | Re-fusion with a corrected algorithm; a new operational intent version; a NOTAM replacement |
| State transition | The entity legitimately changed state | New record of a state kind, same `entity_id` | `alert.state_change` (acknowledged, resolved); `utm.intent_state` (Accepted → Activated) |

*How:* `entity_id` names the thing a record is about (`urn:track:site-a:9421`, an alert, an operational intent, a sensor). Each kind's type definition says whether it's required and how it's derived, so it can't drift from the payload. A small latest-state table keyed on `entity_id` gives current state for operational queries, while the full history stays immutable.

**V3. Operator edits as records.**
*Why:* Updating rows loses who did what and what the picture looked like before.
*How:* Each action is a record (`kind: track.command`). Trackgen applies it and lists it in the updated track's `derived_from`, so operator decisions become part of lineage.

**V4. Map to W3C PROV.**
`derived_from` = `wasDerivedFrom`, `origin` = `hadPrimarySource`, `revision_of` = `wasRevisionOf`, `produced_by` = generating agent. Export PROV-JSON on request.

**V5. Sign where integrity matters.**
*Why:* Evidence and after-action review need proof of no tampering.
*How:* Per-producer keys (for example Ed25519) in OpenBao or TPM. Sign batches, not every record. STANAG 4778 covers label binding (C3).

### 6.6 Extension fields

| ID | Finding | Recommendation | Principles |
|---|---|---|---|
| X1 | Two extension areas, unclear schema scope. | One `payload`, one schema. | DP6 |
| X2 | Payload indexes not addressed. | Declare index hints in the type definition. | DP6 |

**X1. One payload.**
Validate `payload` against `schema` at the adapter. Pick one rule for unknown fields and apply it everywhere.

**X2. Indexes from configuration.**
*Why:* Hand-made indexes per installation don't scale and break "configuration, not architecture".
*How:* Each kind's type definition lists index hints (10.3); tooling creates partial indexes from them:

```yaml
# kinds/track.fused/type.yaml
index_hints: ["payload->>'callsign'", "payload->>'squawk'", "payload->>'target_address'"]
```

```sql
CREATE INDEX ON ume ((payload->>'squawk')) WHERE kind = 'track.fused';
```

### 6.7 Storage mapping

| ID | Finding | Recommendation | Principles |
|---|---|---|---|
| D1 | ~40 mostly empty columns. | Envelope columns plus `jsonb`. | DP6, DP1 |
| D2 | No index strategy. | Indexes per query type. | DP2, DP8 |

**D1. Envelope columns plus `jsonb`.**
*Why:* A column per field means a migration per new type, which is the fixed model DP6 avoids.
*How:* Columns for filtered envelope fields (time, geometry, kind, source, label); `jsonb` for payload, provenance, links, assets. Heavily queried types can get generated tables from configuration.

**D2. Indexes.**

| Index | Serves |
|---|---|
| Hypertable on `datetime` | Time windows |
| GiST on `geom` | Area queries |
| B-tree on (`kind`, `datetime`) | Latest of a kind |
| GIN on `releasable_to`, `caveats` | Security filters from OPA (7.1) |
| Partial payload indexes | Type-specific search (X2) |

### 6.8 Miscellaneous

| ID | Finding | Recommendation | Principles |
|---|---|---|---|
| M1 | `$schema` misused. | `ume_version`. | DP4 |
| M2 | Wire format and routing unspecified. | JSON now; CloudEvents for metadata; routing by subject. | DP4, DP3 |

**M1. `ume_version`.**
In JSON Schema, `$schema` names a meta-schema. `ume_version` versions the envelope; `schema` versions the payload, independently.

**M2. Wire format.**
*Why:* Base64 adds a third; services must parse the body to read kind or label.
*How:* Start with JSON. With Protobuf, use CloudEvents binary mode (mapping in 3.6): event ID, kind, source, time, entity, schema and label as headers, payload as body, so consumers and gateways can read metadata without decoding. Brokers don't route on headers, though: routing uses the transport's own addressing, so encode it there.

| Transport | Routing | Example |
|---|---|---|
| NATS | Subject | `fabric.track.fused.site-a`, `fabric.alert.zone_breach.site-a` |
| Kafka | Topic and partition key | Topic `fabric.track.fused`, key `entity_id` |
| MQTT | Topic hierarchy | `fabric/track/fused/site-a` |

Dotted kinds map directly onto subject tokens. A classification segment can be added for coarse separation if the deployment needs it. Set `Nats-Msg-Id` from the deduplication key (A9) so JetStream drops duplicates.

---

## 7. Classification and labelling

### 7.1 Access decisions and OPA

The label on a record is only useful if something checks it every time data leaves the platform. This review recommends **Open Policy Agent (OPA)** for that job.

**What it is.** OPA is an open-source policy engine: a small service or library that answers access questions. A service sends it a question as JSON, OPA evaluates it against rules written in its policy language (Rego), and returns a decision. It's a graduated CNCF project under the Apache 2.0 license, widely used for API and microservice authorization.

```
Service (GSS, live streams, export)            OPA
  "Can this user see this record?"   ───►   evaluates policy
  { user: {...}, record: {label} }   ◄───   { "allow": true }
```

**Why use it instead of writing checks in code:**

| Benefit | What it means here |
|---|---|
| One set of rules | GSS, the live streams service, the BFF and export gateways all ask the same question and get the same answer. Rules can't drift between services. |
| Rules change without code changes | Updating a label rule is a policy update, not a release of every service. |
| Testable | Policies have their own unit tests, so the team can show accreditors exactly what the rules are and prove they behave as written. |
| Audit | OPA can log every decision: who asked, for what, and the answer. |
| Works offline | Policies are distributed as bundles and evaluated locally, so edge nodes keep making decisions while disconnected. |
| Database filtering | For bulk queries, OPA's partial evaluation can produce a filter condition that's translated into a SQL `WHERE` clause, so Postgres returns only permitted rows instead of the service checking each one. |

**How it fits with identity.** Keycloak (or the customer's identity provider) answers *who the user is* and puts their attributes (clearance, nationality or organization, caveats) in the login token. OPA answers *what they can see*, by comparing those attributes with the record's label. That comparison is attribute-based access control (ABAC).

**Where it runs.** Next to each service that releases data, as a sidecar or embedded library, with the same policy bundle everywhere. The enforcement points are:

- Query APIs (GSS): filter query results.
- Live streams: check each message before it's pushed to a user.
- Export and partner gateways: check before data leaves the platform.
- Node sync: decide what may replicate to which node, using `releasable_to`.

**What developers need to do:**

- Call OPA at the enforcement points above; never write label checks in service code.
- Pass the user's token attributes and the record's `security` block as input.
- Treat "no decision" or an OPA error as deny.
- Write policy tests alongside any policy change.

Alternatives exist (for example AWS's Cedar, also open source), but OPA has the larger ecosystem and the most integrations, so it's the safer default.

### 7.2 Findings

| ID | Finding | Recommendation | Principles |
|---|---|---|---|
| C1 | Called role-based, but rules compare user attributes to record labels. | Attribute-based access control (ABAC) in OPA (7.1). | DP8 |
| C2 | Single `nato_classification` enum; Canadian data uses national markings, and NATO names are formally "NATO RESTRICTED" etc. | Five-field label with `policy` selecting the scheme (7.3). | DP8, DP6 |
| C3 | No label integrity. | Align with **STANAG 4774** (confidentiality metadata labels) and **STANAG 4778** (binding labels to data). | DP8, DP4 |
| C4 | `need_to_know` defined as countries but used as a group; matching rule undefined. | Rename to `caveats`; the user must hold all of them. | DP8 |
| C5 | Country and coalition codes unspecified. | ISO 3166-1 alpha-3 for countries, plus named coalitions (e.g. FVEY). | DP8, DP4 |
| C6 | No defined behaviour for missing labels. | Fail closed (section 7.4). | DP8 |
| C7 | No rule for labels on derived data. | Derivation rules defined by the policy package (7.3). | DP8, DP7 |


### 7.3 Label structure

**The UME carries labels; it does not define what they mean.** For each `policy`, a policy package (maintained with the security authority, enforced through OPA) defines:

- label validation (allowed values and combinations),
- clearance comparison (how levels relate; not necessarily a single ranking),
- release rules (who `releasable_to` admits),
- caveat handling,
- derivation rules for data built from several inputs, including across policies,
- downgrade and sanitization rules.

The envelope schema only checks that a label is present and well formed. Every record carries the same five fields, whatever the scheme:

| Field | Purpose | Why it's essential |
|---|---|---|
| `policy` | Which scheme the label uses: NATO, CAN or CORP | Selects the allowed values and the OPA policy |
| `classification` | Sensitivity level | Core check: the user's level must meet or exceed it |
| `releasable_to` | Countries (NATO/CAN) or organizations (CORP) the data may go to | Sharing between nations or tenants, and what syncs to which node |
| `caveats` | Groups or compartments; the user must hold **all** of them | Need-to-know within an organization |
| `originator` | Controlling authority | Who approves release or downgrade; tenant boundary in CORP. Not necessarily the producer, which is recorded in `provenance.producer_org`. |

```json
"security": {
  "policy": "CAN",
  "classification": "PROTECTED B",
  "releasable_to": ["CAN"],
  "caveats": ["OPS-INTEL"],
  "originator": "urn:org:dnd"
}
```

Allowed values per scheme:

| Policy | `classification` | `releasable_to` |
|---|---|---|
| NATO | NATO UNCLASSIFIED, NATO RESTRICTED, NATO CONFIDENTIAL, NATO SECRET, COSMIC TOP SECRET | ISO 3166-1 alpha-3 countries, coalitions (e.g. FVEY) |
| CAN | UNCLASSIFIED, PROTECTED A, PROTECTED B, PROTECTED C, CONFIDENTIAL, SECRET, TOP SECRET | Same as NATO |
| CORP | PUBLIC, INTERNAL, CONFIDENTIAL, RESTRICTED | Organization URNs (`urn:org:...`) |

An example of what a policy package's core rule might look like in OPA. It is illustrative only: the real rules, including any ranking, come from the security authority.

```rego
package fabric.authz

default allow := false

level_rank := {
  "NATO": {"NATO UNCLASSIFIED": 0, "NATO RESTRICTED": 1, "NATO CONFIDENTIAL": 2, "NATO SECRET": 3, "COSMIC TOP SECRET": 4},
  "CAN":  {"UNCLASSIFIED": 0, "PROTECTED A": 1, "PROTECTED B": 2, "PROTECTED C": 3, "CONFIDENTIAL": 3, "SECRET": 4, "TOP SECRET": 5},
  "CORP": {"PUBLIC": 0, "INTERNAL": 1, "CONFIDENTIAL": 2, "RESTRICTED": 3}
}

user_ref(p) := input.user.org if p == "CORP"
user_ref(p) := input.user.nationality if p != "CORP"

allow if {
  l := input.record.label
  level_rank[l.policy][input.user.clearance[l.policy]] >= level_rank[l.policy][l.classification]
  user_ref(l.policy) in l.releasable_to
  every c in l.caveats { c in input.user.caveats }
}
```

A single numeric ranking is a simplification. For example, PROTECTED and classified levels are separate categories in Government of Canada policy, and how they compare is for the security authority to decide.

### 7.4 Default classification: fail closed

There should be no default that assumes UNCLASSIFIED. Instead:

1. **Labels come from source configuration.** Each source is registered with the label its data carries, decided when the source is approved. The adapter stamps it on every UME.

```yaml
sources:
  - id: urn:source:flightline-0037
    label: { policy: CAN, classification: UNCLASSIFIED, releasable_to: [CAN, USA, GBR, AUS, NZL], caveats: [], originator: "urn:org:dnd" }
  - id: urn:source:radar-0012
    label: { policy: CAN, classification: PROTECTED B, releasable_to: [CAN], caveats: [], originator: "urn:org:dnd" }
```

2. **Missing or unknown labels fail closed.** Either quarantine to a dead-letter subject for review, or label at "system high" (the node's accredited maximum) with the narrowest releasability until reviewed.

3. **Enforce at every layer:**
   - Schema: all five label fields required.
   - Postgres: label columns `NOT NULL` with no `DEFAULT`.
   - OPA: `default allow := false`.
   - Adapters: reject messages from sources without a registered label.

Actual levels, system-high values and releasability come from the program's security assessment and accreditation, not from engineering.

## 8. Proposed revised UME

The fused track, with the recommendations applied, in the JSON profile (section 3.6):

```json
{
  "type": "Feature",
  "id": "urn:uuid:01926f3a-8e10-7c32-b7e1-8890cf2b6941",
  "geometry": {
    "type": "Point",
    "coordinates": [
      -75.6972,
      45.4215
    ]
  },
  "properties": {
    "ume_version": "1",
    "kind": "track.fused",
    "schema": "urn:schema:tracks:fused-kinematics:v1",
    "entity_id": "urn:track:site-a:9421",
    "datetime": "2026-09-23T17:46:01.200Z",
    "start_datetime": null,
    "end_datetime": null,
    "time_source": "event",
    "times": {
      "source_at": "2026-09-23T17:46:01.205Z",
      "sent_at": "2026-09-23T17:46:01.210Z",
      "received_at": "2026-09-23T17:46:01.215Z",
      "stored_at": "2026-09-23T17:46:01.230Z"
    },
    "expires_at": null,
    "geometry_source": "observed",
    "position_error_m": 12.0,
    "domain": "AIR",
    "height_range": {
      "lower_m": 3200.5,
      "upper_m": 3200.5,
      "approximate": false
    },
    "source": {
      "id": "urn:source:omnitrack-01",
      "node": "site-a",
      "event_id": "site-a:9421:118734"
    },
    "provenance": {
      "origin": "urn:source:flightline-0037",
      "derived_from": [
        "urn:uuid:01926f3a-7d01-7bb2-b841-39659b8120e5",
        "urn:uuid:01926f3a-7d02-78b2-b1d6-857c0e66c91a"
      ],
      "revision_of": null,
      "produced_by": "omnitrack-engine",
      "producer_version": "3.4.1",
      "producer_org": "urn:org:dnd",
      "config_hash": "12209c9c9c9c9c9c9c9c9c9c9c9c9c9c9c9c9c9c9c9c9c9c9c9c9c9c9c9c9c9c9c9c"
    },
    "security": {
      "policy": "CAN",
      "classification": "UNCLASSIFIED",
      "releasable_to": [
        "CAN",
        "USA",
        "GBR",
        "AUS",
        "NZL"
      ],
      "caveats": [],
      "originator": "urn:org:dnd"
    },
    "payload": {
      "track_id": "site-a:9421",
      "callsign": "C-GKSI",
      "object_class": "FIXED_WING",
      "ground_speed_mps": 210.5,
      "course_deg": 184.2,
      "vertical_rate_mps": -5.2,
      "vertical_rate_type": "GEOMETRIC",
      "pressure_altitude_ft": 3150,
      "squawk": "7700",
      "target_address": "C0FFEE",
      "emitter_category": "LIGHT",
      "air_ground_state": "AIRBORNE",
      "fusion": {
        "algorithm": "KalmanFilterMultiSensor",
        "contributing_sensor_count": 2,
        "covariance_diag_m2": [
          1.2,
          1.2,
          4.5
        ]
      }
    }
  },
  "links": [],
  "assets": {}
}
```

Records with files (imagery, video) add `assets`; see the video example in 11.2.

Field mapping from the current design:

| Current | Proposed |
|---|---|
| `$schema` | `properties.ume_version` |
| `uuid` | `id` (UUIDv7): identity of this record |
| (missing) | `source.event_id`: identity of the source event, for deduplication (A9) |
| (missing) | `entity_id`: the thing the record is about (V2) |
| `temporal.sourced_at` / `broadcasted` / `observed_at` / `ingested_at` | `times.source_at` / `sent_at` / `received_at` / `stored_at` |
| (missing) | `datetime`, `start_datetime`, `end_datetime` |
| `temporal.valid_until` | `expires_at` |
| `temporal.index` / `spatial.track.index` | removed |
| `spatial.geometry` (3D) | `geometry` (2D, top level; null where the kind allows) |
| Geometry height / `altitude_type` | `height_range` (WGS84 ellipsoidal); originals in payload (section 12) |
| `spatial.crs` | fixed: OGC:CRS84 horizontal, WGS84 ellipsoidal vertical |
| `spatial.confidence` | `position_error_m` (+ `geometry_source`) |
| `spatial.domain` | `domain` (physical domains only) |
| `spatial.track.*` | `payload` (per schema) |
| `spatial.track.payload` (raw binary) | backbone, or a batch file asset (`track.raw`) |
| `reference.links` | `assets` for files; `links` for services only |
| `reference.links[rel=derivedfrom]` | `provenance.derived_from` (+ `ume_link` projection) |
| `asset_descriptor.schema` | `schema` |
| `asset_descriptor.source_id` / `source_name` | `source.id` (stable URN) + `source.node` |
| `asset_descriptor.data_type` | `kind` |
| `asset_descriptor.mime_type` / `sha256` | `assets.*.type` / `file:checksum` (multihash) |
| `asset_descriptor.lifecycle` / `storage_tier` | `ume_state` table |
| `classification.nato_classification` / `releasable_to` / `need_to_know` / `owner_id` | `security.classification` / `releasable_to` / `caveats` / `originator` (7.3); producer in `provenance.producer_org` |
| `properties` / `spatial.track.properties` | `payload` |

---

## 9. Controlled lists and standards

The controlled lists and formats in the schemas, and whether each comes from a standard.

**Legend:** ✅ standard, ◐ standards-aligned or partly standard, ✖ custom to this design

### 9.1 Envelope

| Field | Values / format | Standard? | Source |
|---|---|---|---|
| `type` | `Feature` | ✅ | GeoJSON (RFC 7946) |
| Geometry types | Point, MultiPoint, LineString, MultiLineString, Polygon, MultiPolygon, GeometryCollection, or null | ✅ | GeoJSON (RFC 7946), from OGC Simple Features |
| Coordinates | lon, lat | ✅ | OGC CRS84 |
| `height_range` | Metres, WGS84 ellipsoidal | ◐ | Datum is standard (with CRS84, EPSG:4979); field is custom. JSON-FG Prism on export. |
| `id` | `urn:uuid:` UUIDv7 | ✅ | RFC 9562 |
| Date-times | `2026-09-23T17:46:01.200Z` | ✅ | RFC 3339 (ISO 8601 profile) |
| `ume_version` | `1` | ✖ | Custom |
| `kind` | `track.fused`, `video.segment`, ... | ✖ | Custom naming convention |
| `schema`, `entity_id` | `urn:schema:...`, `urn:track:...` | ◐ | URN syntax (RFC 8141); namespaces not registered |
| `source.id` | `urn:source:<device>` | ◐ | Same as above |
| `source.event_id` | Per-kind derivation rule | ◐ | Often a standard native ID (ASTERIX SAC/SIC + sequence, NOTAM ID) |
| `time_source` | `event`, `source_at` | ✖ | Custom |
| `geometry_source` | `observed`, `defined`, `sensor_coverage`, `sensor`, `aoi` | ✖ | Custom |
| `domain` | AIR, LAND, SEA_SURFACE, SUBSURFACE, SPACE | ◐ | Aligned with APP-6 / MIL-STD-2525 domains, not their exact codes |
| `position_error_m` | Metres, 95% radius | ◐ | SI unit; the 95% definition is a design choice |

### 9.2 Security label

| Field | Values / format | Standard? | Source |
|---|---|---|---|
| `policy` | NATO, CAN, CORP | ✖ | Custom selector |
| `classification` (NATO) | NATO levels (7.3) | ✅ | NATO security policy markings |
| `classification` (CAN) | Government of Canada levels (7.3) | ✅ | Policy on Government Security |
| `classification` (CORP) | PUBLIC to RESTRICTED (7.3) | ✖ | Common practice, not a formal standard |
| `releasable_to` (NATO/CAN) | ISO 3166-1 alpha-3 codes, plus FVEY, NATO, ACGU | ✅ / ◐ | ISO 3166-1 (enumerated in the schema); coalition list maintained by the program |
| `releasable_to` (CORP) | `urn:org:...` | ◐ | URN syntax only |
| `caveats` | Free text | ✖ | Custom (could align with STANAG 4774 categories) |
| `originator` | `urn:org:...` | ◐ | URN syntax only |

### 9.3 Links and assets

| Field | Values / format | Standard? | Source |
|---|---|---|---|
| Stored link `rel` | service, related, alternate, describedby | ✅ | IANA Link Relations registry |
| Generated link `rel` | self, next, prev, predecessor-version; derived_from | ✅ | IANA; STAC |
| `type` (links, assets) | `image/tiff; application=geotiff`, `video/mp2t` | ✅ | IANA media types |
| `href` scheme `urn:` | | ✅ | RFC 8141 |
| `href` scheme `s3:` | | ◐ | Widely used de facto, not registered |
| `href` scheme `lake:` | | ✖ | Custom |
| Asset structure, `roles` | data, thumbnail, alternate, metadata | ✅ | STAC assets |
| `file:size` | Integer bytes | ✅ | STAC File extension |
| `file:checksum`, `config_hash` | `1220` + 64 hex | ✅ | SHA2-256 (FIPS 180-4) as multihash, per the STAC File extension |

### 9.4 Track payloads

| Field | Values / format | Standard? | Source |
|---|---|---|---|
| `track_id` | `site-a:9421` | ✖ | Custom |
| `squawk` | 4 octal digits | ✅ | ICAO Mode A code (Annex 10) |
| `target_address` | 6 hex characters | ✅ | ICAO 24-bit aircraft address (Annex 10) |
| `callsign` | Text | ◐ | ICAO aircraft identification, format not enforced |
| `identity` | PENDING, UNKNOWN, ASSUMED_FRIEND, FRIEND, NEUTRAL, SUSPECT, HOSTILE | ✅ | APP-6 / MIL-STD-2525 standard identity |
| `object_class` | UAS, FIXED_WING, ROTORCRAFT, ... | ✖ | Custom |
| `emitter_category` | `LIGHT`, `ROTORCRAFT`, `UAV`, ... | ✅ | ADS-B emitter categories (DO-260B; ASTERIX CAT021 I021/020) |
| `vertical_rate_type` | GEOMETRIC, PRESSURE | ◐ | Concept from ADS-B / ASTERIX; labels are custom |
| `air_ground_state` | AIRBORNE, ON_GROUND, UNKNOWN | ◐ | Concept from ADS-B; labels are custom |
| Speeds, rates | m/s | ✅ | SI units |
| `pressure_altitude_ft` | Feet | ◐ | Aviation convention |
| `course_deg`, `heading_deg` | 0–360, true north | ◐ | Navigation convention |

### 9.5 Other payload kinds

| Kind | Field | Standard? | Source |
|---|---|---|---|
| `alert.*` | `severity`, `urgency`, `certainty` | ✅ | OASIS Common Alerting Protocol (CAP) 1.2 |
| `alert.state_change` | `status` | ✖ | Custom |
| `imagery.ortho` | `gsd`, `bands` / `eo:common_name`, `eo:cloud_cover`, `proj:code`, `view:*` | ✅ | STAC core and eo, projection, view extensions |
| `sensor.detection` | `rid.uas_id_type` | ✅ | ASTM F3411 Remote ID |
| `sensor.detection` | `sensor_type` | ✖ | Custom |
| `video.segment` | `klv.standard` | ✅ | MISB ST 0601 (STANAG 4609) |
| `utm.intent_state` | `state` | ✅ | ASTM F3548 operational intent states (plus `Ended`) |
| `aim.notam` | ID, type, Q-code, traffic, purpose, scope | ✅ | ICAO NOTAM format |
| `zone.geofence` | `schedule` | ✅ | iCalendar RRULE (RFC 5545) |
| `zone.geofence` | `zone_type` | ✖ | Custom |
| `sensor.status` | `state` | ✖ | Custom |
| All | Altitude `reference` / `units` | ◐ | Aviation datums (W84, AMSL, AGL, SFC, STD); labels are custom |

### 9.6 Gaps

| Gap | Recommendation | Principles |
|---|---|---|
| Unregistered URN namespaces (`schema`, `source`, `org`, `track`, `zone`) | Fine internally; for external exchange, register a namespace or use an organization-owned identifier scheme | DP4 |
| Coalition codes | The schema enumerates ISO 3166-1 plus a short coalition list; the program should own and maintain that list | DP4, DP8 |
| `caveats` free text | Align with STANAG 4774 label categories for NATO exchange | DP4, DP8 |
| `domain` codes | Use exact APP-6 / MIL-STD-2525 codes if symbology mapping matters | DP2, DP4 |

The custom lists (`kind`, `geometry_source`, `time_source`, CORP classification levels, state values) are expected: they're platform-specific. Document them as part of the published schema rather than looking for a standard.

---

## 10. Schema catalogue

Every `kind` has a payload schema, a type definition and at least one example. The schema is the contract that makes "bring your own data model" (DP6) work: without it the platform can't validate, index, document or safely evolve a type.

### 10.1 Rules

| Rule | Why |
|---|---|
| No kind without a schema | Unvalidated payloads are where bad data gets in. Experimental kinds get a permissive schema marked `draft`, but still have one. |
| One schema per kind version | The record's `schema` field names exactly which version it follows (`...:v1`, `...:v2`). |
| Additive changes keep the version | New optional fields don't break readers. Removing, renaming or changing the meaning of a field means a new version. |
| Old versions are never deleted | Archived records still point to them. |
| Shared definitions live in `common.v1` | Altitude, angles, speeds, IDs and standard lists are defined once and referenced with `$ref`. |
| Shared structure lives in `base/` | Kinds in one family (alert kinds) extend a base schema. |
| Each kind has a type definition | Envelope rules, identity derivation and index hints sit beside the schema. |
| Each kind has examples | Examples are test fixtures, validated in CI on every change. |
| Reuse standard field names where they exist | Imagery uses STAC field names; alerts use CAP values; identities use APP-6 (DP4). |

### 10.2 Layout

```
schemas/
  ume.schema.json                 envelope (JSON profile)
  common.v1.schema.json           shared definitions
  base/alert.v1.schema.json       base for alerts
  kinds/<kind>/
    v1.schema.json                payload schema
    type.yaml                     type definition
    examples/*.json               valid records (test fixtures)
tools/
  validate.py                     validates everything; used in CI
```

Schemas reference each other by URN (for example `urn:schema:fabric:common:v1#/$defs/altitude`), resolved from this folder, never from the network.

### 10.3 Type definition

Each kind's `type.yaml` describes what the kind is, beyond its payload schema:

```yaml
kind: track.fused
schema: urn:schema:tracks:fused-kinematics:v1
status: draft
envelope:
  time: instant                    # instant | span
  geometry: required               # required | optional | forbidden
  geometry_source: [observed]      # allowed values
  height_range: optional           # required | optional | forbidden
  entity_id: required              # required | optional | forbidden
  entity_id_template: urn:track:{payload.track_id}
  required_assets: []
source_event_id: track_id + Trackgen update sequence
index_hints: ["payload->>'callsign'", "payload->>'squawk'", "payload->>'target_address'"]
```

| Section | Used by | For |
|---|---|---|
| `envelope` | Adapters, `validate.py` | Rules the envelope must meet for this kind |
| `entity_id_template`, `source_event_id` | Adapters, producers | How identity is derived, so every producer computes the same values |
| `index_hints` | Index tooling | Partial indexes for common payload queries |

Retention, synchronization between nodes and API exposure (which OGC collection serves a kind) are platform configuration and outside the scope of this schema package.

### 10.4 Kinds

| Kind | Purpose | Time | Geometry | Height | Entity | Files | Standards used |
|---|---|---|---|---|---|---|---|
| `track.raw` | One raw sensor message | Instant | Sensor coverage | — | — | Batch file | ASTERIX |
| `sensor.detection` | Single-sensor detection before fusion | Instant | Estimated position | Optional | Optional | — | ASTM F3411 ID types |
| `track.fused` | Fused track state | Instant | Position | Optional | Track | — | ICAO Mode A, 24-bit address; ADS-B categories; APP-6 identity |
| `track.command` | Operator action on tracks | Instant | Optional | — | Optional (target track) | — | APP-6 identity |
| `alert.zone_breach` | Track entered, left or loitered in a zone | Instant | Breach position | Optional | The alert | — | OASIS CAP 1.2 |
| `alert.nonconformance` | Track left its UTM nominal volume | Instant | Track position | Optional | The alert | — | OASIS CAP 1.2 |
| `alert.state_change` | Alert acknowledged, escalated, resolved or dismissed | Instant | None | — | The alert | — | — |
| `video.segment` | FMV segment | Span | Ground footprint | Optional | — | Video, HLS, thumbnail, KLV | STANAG 4609, MISB ST 0601 |
| `imagery.ortho` | Orthorectified image | Span | Footprint | Optional | — | COG, thumbnail | STAC eo, proj, view |
| `utm.volume` | One 4D volume of an operational intent | Span | Footprint (`defined`) | Required | The intent | — | ASTM F3548 |
| `utm.intent_state` | Operational intent state transition | Instant | Optional | — | The intent | — | ASTM F3548 |
| `aim.notam` | NOTAM area restriction | Span | Area (`defined`) | Required | The NOTAM | AIXM, text | ICAO NOTAM, AIXM 5.1 |
| `zone.geofence` | Protected, restricted or monitored area | Span, open end allowed | Area (`defined`) | Required | The zone | — | iCalendar RRULE (RFC 5545) |
| `sensor.status` | Sensor health and coverage | Instant | Coverage area | Optional | The sensor | — | — |

### 10.5 Storage and distribution

Schemas live in Git, are released as a signed bundle, and are used from a local copy on every node. Nothing fetches a schema over the network while validating data.

| Layer | Where | Purpose |
|---|---|---|
| Authoring | Git repository (this `schemas/` tree) | History, review, CI (`validate.py`). Merging and tagging publishes a version. |
| Release | Versioned schema bundle, signed (Cosign), stored as an OCI artifact in Harbor | One immutable, verifiable unit to deploy |
| Runtime | On disk on every node, delivered by GitOps like OPA bundles | Offline validation and URN lookup; no registry needed at the edge |
| Discovery (optional) | Apicurio Registry at the core, loaded from the bundle | Browsing and API for developers and partners; a copy, never the source of truth |

- Records store only the schema URN, and every bundle keeps all old versions, so archived records stay readable.
- A record naming a schema the node doesn't have is quarantined until the bundle catches up; it's never fetched remotely.
- New bundles reach every node before producers start using a new schema version.
- Nodes refuse unsigned or altered bundles: schemas decide what data is accepted, so they're part of the security boundary.

---

## 11. Worked examples

Each kind has an example in `kinds/<kind>/examples/`. The examples are linked, so they also show lineage, entities and state across kinds:

```
track.raw ────────┐
                  ├─► track.fused                                    ISR chain (CAN labels)
sensor.detection ─┘

zone.geofence ─► alert.zone_breach ─► alert.state_change (acknowledged)
                        └────────────► track.command (reclassify)     site protection (CORP labels)

utm.volume ─┬─► alert.nonconformance
            └── utm.intent_state (Accepted → Activated)               UTM (CORP labels)
```

### 11.1 Fused track and its inputs

`track.fused/examples/fused-air-track.json` is the track in section 8.

- **Geometry and height:** a 2D point plus `height_range` 3,200.5 m (a single height, so lower equals upper).
- **Entity:** `urn:track:site-a:9421`, derived from the payload `track_id`, so every update of this track shares it.
- **Source:** `urn:source:omnitrack-01` (the Trackgen instance), ingested at `site-a`, with event ID `site-a:9421:118734` (track and update sequence).
- **Provenance:** `derived_from` the raw ASTERIX message and the radar plot; `producer_org` DND; `revision_of` null, since an update is a new observation, not a correction (V2).
- **Security:** CAN, UNCLASSIFIED, five nations, consistent with its inputs.

The **raw message** has no target position, so its geometry is the receiver's 50 km coverage (`sensor_coverage`, S3) and it has no height. Its event ID is the ASTERIX SAC/SIC plus sequence (`012/037:491208`), so any adapter receiving it produces the same deduplication key. The bytes sit in a one-minute batch file (`data` asset).

The **radar plot** has an estimated position with a 40 m error, a height of 3,195 m, and its radar measurements in the `radar` sub-object.

### 11.2 FMV video segment

`video.segment/examples/uav-eo-segment.json` is 10 seconds from a UAV EO camera: one record describing several files.

- **Time** is a span (17:45:10–17:45:20), with `datetime` set to the start (T2).
- **Geometry** is the 2D ground area the camera saw, from KLV; `height_range` 71.5–74 m is the terrain height across the footprint. The aircraft's own position is in the payload (`sensor_position`).
- **Provenance:** primary data, so `derived_from` is empty. An EO detection found in this video would be a `sensor.detection` listing this segment in its `derived_from`.
- **Links:** a `service` link to the sensor's live stream, by URN, resolved by the access layer. `next` / `previous` aren't stored (L2).

| Asset | File | Media type | Role |
|---|---|---|---|
| `data` | Original segment with KLV (STANAG 4609), with size and checksum | `video/mp2t` | data |
| `hls` | Playback rendition | `application/vnd.apple.mpegurl` | alternate |
| `thumbnail` | Preview image | `image/jpeg` | thumbnail |
| `klv` | Decoded KLV as JSON | `application/json` | metadata |

All `href` values are `s3://` references; GSS turns them into presigned or proxied URLs after the access check (L1).

The **orthomosaic** (`imagery.ortho/examples/sector-b-orthomosaic.json`) follows the same pattern, with STAC field names in its payload so it exports as a STAC Item without translation.

### 11.3 UTM: volume, state and non-conformance

`utm.volume/examples/bvlos-nominal-volume.json` is one 4D volume of an operational intent (ASTM F3548 concepts): a BVLOS flight, 18:00–18:25, 45–165 m, west of Ottawa.

| UTM concept | Representation |
|---|---|
| Volume footprint | 2D geometry, `geometry_source: defined` |
| Reservation period | `start_datetime` / `end_datetime` |
| Altitude bounds | `height_range` 45–165 m (already WGS84; no conversion), originals in payload (12) |
| Operational intent | `entity_id` `urn:uuid:<operational_intent_id>`, shared by all its volumes and state records |
| Conformance volume / off-nominal volume | `volume_type`: `nominal` / `off_nominal` |
| New intent version from the USS | New volume records with `revision_of` the previous ones: a supersession (V2) |
| State (Accepted, Activated, Nonconforming, Contingent, Ended) | `utm.intent_state` records: state transitions, not revisions |
| Conformance monitoring | Compares fused tracks to active nominal volumes; a violation is an `alert.nonconformance` |

**State transition:** `utm.intent_state/examples/intent-activated.json` records Accepted → Activated at 18:00. It has no geometry: it's about the intent, whose volumes already carry the location. Its event ID (`<intent>:v1:Activated`) is a natural key, so the same transition reported twice is recognised as one event.

**Non-conformance:** `alert.nonconformance/examples/bvlos-volume-exit.json` shows track `site-a:9512` 85 m outside the volume, `derived_from` the track and the volume. Its `releasable_to` is the intersection of its inputs' (the utility only).

The volume's originator is the USS (it controls the operator's flight data), while the producing organization is the utility that runs the adapter. The payload schema marks `uas_serial` and `operator_id` with `"x-personal-info": true`, which OPA uses to redact them for users without personal-information access.

### 11.4 NOTAM

`aim.notam/examples/ottawa-restricted-area.json` is a temporary restricted area: 2 NM around downtown Ottawa, surface to 1,500 ft AMSL, 17:00–21:00, RPAS prohibited.

| NOTAM concept | Representation |
|---|---|
| Items B / C (validity) | `start_datetime` / `end_datetime` |
| Item D (schedule) | Payload `schedule` |
| Circle area | 24-sided 2D polygon (`defined`); centre and radius kept in payload `area` |
| Items F / G (limits) | `height_range` null–423 m (converted, 12); originals in payload |
| ID, Q-code, FIR, location, text | Payload (`A1234/26`, `QRTCA`, `CZUL`, `CYOW`); `entity_id` `urn:notam:A1234/26` |
| NOTAMR / NOTAMC | New record with `revision_of` the original (and `replaces` for NOTAMR) |
| Original message | Assets: AIXM 5.1 Digital NOTAM and ICAO-format text |

NOTAMs are public but still labelled (CORP, PUBLIC): fail closed applies to everything. The originator is the issuing authority.

### 11.5 Zone, alert, acknowledgement and command

Four linked records show a site-protection sequence:

| Record | Key content | Entity | Links |
|---|---|---|---|
| `zone.geofence`: Substation B protection zone | 2D polygon (`defined`), active from 2026-01-01 with no end, surface to 150 m AGL, `breach_severity: SEVERE` | `urn:zone:northgrid:substation-b` | — |
| `alert.zone_breach`: UAS entered the zone (18:05:12) | Breach point at 95 m, CAP `SEVERE` / `IMMEDIATE` / `OBSERVED`, track `site-a:9507`, `zone_id` = the zone's entity | The alert (its own ID) | `derived_from` the track and the zone record |
| `alert.state_change`: alert acknowledged (18:05:30) | `ACKNOWLEDGED` from `ACTIVE`, operator, note | The alert | — |
| `track.command`: operator reclassifies the UAS (18:05:40) | `RECLASSIFY` to `SUSPECT` (APP-6), class `UAS`, tag `intrusion`, reason | `urn:track:site-a:9507` | `derived_from` the alert |

Points this shows:

- **Open-ended span:** the zone has a start and no end.
- **References to entities, not records:** the alert's `zone_id` is the zone's entity ID, so it stays valid if the zone is later revised.
- **State transitions:** the acknowledgement is its own record about the same entity, not a revision of the alert, and has no geometry. The latest-state table shows the alert as acknowledged; the history keeps both records unchanged.
- **Operator lineage:** Trackgen applies the command and lists it in the updated track's `derived_from`, so the decision, who made it and why are part of the track's history (V3). Operator IDs are marked as personal information.
- **Height conversion:** 150 m AGL becomes up to 190 m ellipsoidal (12). The values are illustrative.

`sensor.status/examples/rid-receiver-operational.json` completes the site picture: the Remote ID receiver's 5 km coverage as geometry, its state as payload, and its `entity_id` equal to its source ID, so the latest-state table always holds each sensor's current status.

### 11.6 Side by side

| | Fused track | Video segment | UTM volume | NOTAM | Zone | Alert state change |
|---|---|---|---|---|---|---|
| Time | Instant | Span | Span | Span | Open-ended span | Instant |
| Geometry | Point | Polygon (observed area) | Polygon (footprint) | Polygon (circle) | Polygon (area) | None |
| `geometry_source` | `observed` | `observed` | `defined` | `defined` | `defined` | null |
| Height | Single height | Terrain range | Range | Range, open below | Range, open below | — |
| Entity | Track | — | Operational intent | NOTAM | Zone | Alert |
| Files | None | Four | None | Two | None | None |
| Lineage | Derived from inputs | Primary | Primary; revisions per version | Primary; revisions on replace | Primary | About its entity |
| Label | CAN | CAN | CORP | CORP | CORP | CORP |

Same envelope, same storage, sync, security and API code. Only type-aware services read the payloads.

---

## 12. Vertical model

**Recommendation:** horizontal and vertical are separate. Geometry is always 2D; height is always `height_range`, in WGS84 ellipsoidal metres, on every record that has a height:

```json
"height_range": { "lower_m": 3200.5, "upper_m": 3200.5, "approximate": false }   // a track
"height_range": { "lower_m": 45.0,   "upper_m": 165.0,  "approximate": false }   // a UTM volume
```

Each kind's type definition says whether it's required (UTM volumes, NOTAMs, zones), optional (tracks, detections, footprints) or forbidden (records with no meaningful height). Original altitudes, with their datums, stay in the payload.

**Why:**
- **One spatial query model for everything:** 2D intersection, time intersection and vertical-range intersection. "What applies at 120 m over this point at 18:10?" covers NOTAMs, UTM volumes, zones and tracks in one query.
- **No second vertical representation.** With 3D points alongside 2D footprints plus ranges, every query and the database would need two height models. Keeping them separate removes that.
- **It passes the envelope rule (3.4)** and completes DP2 for airspace data.
- **GeoJSON footprints are 2D,** so volumes need a range anyway; points simply use a range of zero width.

| Decision | Choice | Reason |
|---|---|---|
| Datum | WGS84 ellipsoidal metres | With CRS84 horizontal, matches EPSG:4979; all types compare directly |
| Points | `lower_m` = `upper_m` | Same field and query as volumes |
| Unbounded ends | `null` | NOTAMs and zones often use SFC or UNL |
| `approximate` | True when conversion used assumptions | Flags estimates |
| Converted volumes | Conservative superset of the real volume | Safe first filter; exact checks use payload values |
| Per-vertex heights | Not in the envelope | A footprint's corners or a flight path's points become one range; keep the detail in the payload where it matters |

| Original datum | Conversion |
|---|---|
| WGS84 (`W84`) | None (ASTM F3548 already uses it) |
| `AMSL` | Add geoid height (EGM2008), min/max over the footprint, rounded outward |
| `SFC` lower limit | `null` |
| `AGL` | Terrain + geoid + limit, lowest terrain for the lower bound and highest for the upper; needs an elevation model on each node (e.g. HRDEM, Copernicus GLO-30) |
| Flight level (`STD`) | Standard atmosphere plus a margin; `approximate: true` |

In the examples: the track is a single height (3,200.5 m); the UTM volume needs no conversion (45–165 m); the NOTAM becomes `null` to 423 m (SFC unbounded below; 1,500 ft AMSL is 457.2 m, plus a local geoid height of about −34 m, rounded up); the zone becomes `null` to 190 m from 150 m AGL. Values are illustrative; adapters compute them per footprint.

**Storage:** two columns, both straight from the record:

```sql
geom    geometry(Geometry, 4326),   -- 2D, nullable
height  numrange,                   -- from height_range, nullable

CREATE INDEX ON ume USING gist (geom, height);

SELECT * FROM ume
WHERE ST_Intersects(geom, :point)
  AND start_datetime <= :t
  AND (end_datetime IS NULL OR end_datetime > :t)
  AND height @> 120::numeric;
```

Conformance monitoring uses the same filter to find candidate volumes, then checks exactly. True 3D solids in PostGIS (SFCGAL) aren't recommended: heavy, and poorly supported by OGC APIs.

**Standards:** in the GeoJSON profile, `height_range` is an extra member that ordinary clients ignore; the profile can also write a z coordinate for points for clients that expect one. For export, OGC JSON-FG's **Prism** geometry (2D base plus lower and upper limits) matches this model directly; confirm JSON-FG's status and GSS support.
