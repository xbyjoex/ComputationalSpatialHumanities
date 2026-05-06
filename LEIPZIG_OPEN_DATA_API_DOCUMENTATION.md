# Leipzig Open Data Program: Datasets and API Access

This document summarizes the City of Leipzig open data catalog and explains how to access all datasets through the API.

## 1) Portal and API Basics

- Open data portal: `https://opendata.leipzig.de/`
- API root: `https://opendata.leipzig.de/api/3/action/`
- API type: CKAN Action API (`/api/3/action/<method>`)
- Response format: JSON objects in the shape:
  - `success` (boolean)
  - `result` (payload)
  - `help` (optional)
  - `error` (if request fails)

Example:

```bash
curl "https://opendata.leipzig.de/api/3/action/package_search?rows=1"
```

## 2) Current Catalog Snapshot (retrieved 2026-05-06)

- Total datasets (packages): `395`
- Total resources/files/endpoints linked from datasets: `797`
- Organizations publishing data: `25`
- Topic groups (categories): `13`
- Resources that look like API/service endpoints (WFS/WMS/WMTS/API links): `441`
- Datastore-enabled resources (`datastore_active=true`): `130` across `108` datasets

## 3) Topic Areas (Groups) in Leipzig Open Data

The catalog uses these major topic groups:

- Regierung und öffentlicher Sektor
- Bevölkerung und Gesellschaft
- Wirtschaft und Finanzen
- Bildung, Kultur und Sport
- Regionen und Städte
- Verkehr
- Umwelt
- Wissenschaft und Technologie
- Gesundheit
- Internationale Themen
- Landwirtschaft, Fischerei, Forstwirtschaft und Nahrungsmittel
- Energie
- Justiz, Rechtssystem und öffentliche Sicherheit

You can query all groups:

```bash
curl "https://opendata.leipzig.de/api/3/action/group_list?all_fields=true"
```

## 4) Main Data Sources (by Publisher/Organization)

Largest publishers in the catalog include:

- Amt für Statistik und Wahlen
- Amt für Geoinformation und Bodenordnung
- Standesamt
- Verkehrs- und Tiefbauamt
- Städtische Bibliotheken
- Bürgerservice
- Ordnungsamt
- Amt für Umweltschutz

Query all organizations:

```bash
curl "https://opendata.leipzig.de/api/3/action/organization_list?all_fields=true"
```

## 5) Data Source Domains (where resources are hosted)

Most resource URLs currently point to:

- `statistik.leipzig.de` (statistics datasets)
- `opendata.leipzig.de` (portal-hosted resources/downloads)
- `geodienste.leipzig.de` (geospatial web services)
- `geodaten.leipzig.de` (geodata endpoints/files)
- Additional smaller sources (for example election/ratsinformation domains)

## 6) Available Resource/Data Formats

Most common formats in the Leipzig catalog:

- CSV (dominant tabular format)
- JSON
- GeoJSON
- SHP
- WFS
- GPKG
- WMS
- XLSX
- WMTS
- Additional less frequent formats (for example GTFS, XML, ODS, CityGML, DXF)

## 7) How to Access All Datasets via API

## 7.1 List all dataset IDs

```bash
curl "https://opendata.leipzig.de/api/3/action/package_list"
```

Use this if you only need names/IDs.

## 7.2 Get full metadata for all datasets (recommended)

Use `package_search` with pagination:

```bash
curl "https://opendata.leipzig.de/api/3/action/package_search?rows=100&start=0"
```

Then iterate `start=100,200,300,...` until you collected all results (`result.count` tells total size).

Each dataset contains:

- title and description
- tags/topics
- organization/publisher
- license information
- `resources[]` with URL, format, size, and service links

## 7.3 Get one dataset by name/ID

```bash
curl "https://opendata.leipzig.de/api/3/action/package_show?id=<dataset-id>"
```

## 7.4 Filter by topic, publisher, or free text

Use CKAN search syntax in `fq`:

```bash
curl "https://opendata.leipzig.de/api/3/action/package_search?fq=groups:verkehr&rows=50"
curl "https://opendata.leipzig.de/api/3/action/package_search?fq=organization:amt-fuer-statistik-und-wahlen&rows=50"
curl "https://opendata.leipzig.de/api/3/action/package_search?q=bev%C3%B6lkerung&rows=50"
```

## 7.5 Access tabular records directly (when datastore is enabled)

If a resource has `datastore_active=true`, use:

```bash
curl "https://opendata.leipzig.de/api/3/action/datastore_search?resource_id=<resource-id>&limit=100"
```

Pagination for records:

```bash
curl "https://opendata.leipzig.de/api/3/action/datastore_search?resource_id=<resource-id>&limit=100&offset=100"
```

## 8) API Patterns by Data Type

- Tabular files: usually direct download (`CSV`, `XLSX`, `JSON`) via resource URL
- Geospatial datasets: often service endpoints (`WFS`, `WMS`, `WMTS`) and/or geofiles (`GeoJSON`, `SHP`, `GPKG`)
- Statistical datasets: frequently hosted under `statistik.leipzig.de`, with downloadable files and metadata via CKAN
- Mobility/transport: includes standard file feeds and map/service resources depending on dataset

## 9) Minimal Python Harvester Example

```python
import json
import urllib.parse
import urllib.request

BASE = "https://opendata.leipzig.de/api/3/action/package_search"

start = 0
rows = 100
all_datasets = []

while True:
    url = f"{BASE}?{urllib.parse.urlencode({'rows': rows, 'start': start})}"
    with urllib.request.urlopen(url, timeout=30) as r:
        data = json.load(r)["result"]
    all_datasets.extend(data["results"])
    start += rows
    if start >= data["count"]:
        break

print(f"Collected {len(all_datasets)} datasets")
```

## 10) Practical Notes

- Some resources are file downloads, others are service endpoints; always inspect each dataset's `resources[]`.
- Not every dataset has a CKAN datastore table; use `datastore_search` only when `datastore_active=true`.
- For geospatial pipelines, prefer WFS for feature queries and WMS/WMTS for map rendering.
- Keep in mind that dataset counts can change over time; rerun the API snapshot script for updates.

