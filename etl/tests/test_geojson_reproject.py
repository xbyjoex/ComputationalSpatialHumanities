"""GeoJsonExtractor CRS normalisation — verified against real WFS samples.

Fixtures captured from the live endpoints on 2026-06-10:
- park_ride_lastrecord.json → declares EPSG:4326 (lon/lat, must pass through)
- radverkehr_standorte.json → declares EPSG:25833 (UTM33, must be reprojected)
"""

from __future__ import annotations

import json
from pathlib import Path

from shapely.geometry import shape

from src.extractors.geojson_extractor import GeoJsonExtractor

FIXTURES = Path(__file__).parent / "fixtures"

# Leipzig bounding box in WGS84 — every counter/site must land inside it.
LON_RANGE = (12.0, 12.7)
LAT_RANGE = (51.2, 51.5)


def _load(extractor: GeoJsonExtractor, fixture: str) -> list[dict]:
    data = json.loads((FIXTURES / fixture).read_text())
    extractor.get_json = lambda _url: data  # type: ignore[method-assign]
    return extractor.extract_all("http://test")


def test_park_ride_4326_passthrough():
    feats = _load(GeoJsonExtractor(), "park_ride_lastrecord.json")
    assert feats, "no features parsed"
    lon, lat = feats[0]["geometry"]["coordinates"]
    assert LON_RANGE[0] < lon < LON_RANGE[1]
    assert LAT_RANGE[0] < lat < LAT_RANGE[1]
    # occupancy properties survive for the map / popups
    assert "totalnumvacantparkingspaces" in feats[0]["properties"]


def test_radverkehr_utm_reprojected_to_wgs84():
    feats = _load(GeoJsonExtractor(), "radverkehr_standorte.json")
    assert feats, "no features parsed"
    lon, lat = feats[0]["geometry"]["coordinates"]
    # Raw UTM eastings (~316000) would be far outside any lon/lat range.
    assert LON_RANGE[0] < lon < LON_RANGE[1], f"lon not reprojected: {lon}"
    assert LAT_RANGE[0] < lat < LAT_RANGE[1], f"lat not reprojected: {lat}"


def test_reprojected_geometry_is_loadable():
    """Mirror the loader's geometry parse — shapely.shape must accept output."""
    for fixture in ("park_ride_lastrecord.json", "radverkehr_standorte.json"):
        for feat in _load(GeoJsonExtractor(), fixture):
            geom = shape(feat["geometry"])
            assert geom.is_valid and not geom.is_empty
