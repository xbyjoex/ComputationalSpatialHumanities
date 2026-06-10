"""Extract GeoJSON / WFS features from a URL.

Leipzig's WFS endpoints are inconsistent about coordinate reference systems:
`l5/Amt66/...` (Park+Ride) serves EPSG:4326 (lon/lat), while `l3/OpenData/wfs`
(Radverkehr) serves EPSG:25833 (UTM33N, easting/northing). Both declare their
CRS in the FeatureCollection `crs` member. We normalise every geometry to
WGS84 (EPSG:4326) here so loaders can write `geo_features` without caring about
the source projection.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Generator

from .base import HttpExtractor

logger = logging.getLogger(__name__)

# WGS84 — the target CRS for everything stored in core.geo_features.
_WGS84 = 4326
_CRS_RE = re.compile(r"EPSG:{1,2}(\d+)", re.IGNORECASE)


def _parse_epsg(data: dict[str, Any]) -> int | None:
    """Read the EPSG code from a GeoJSON FeatureCollection `crs` member.

    Handles both `"EPSG:4326"` and the URN form
    `"urn:ogc:def:crs:EPSG::25833"`. Returns None when no CRS is declared
    (GeoJSON spec default is then WGS84).
    """
    crs = data.get("crs")
    if not isinstance(crs, dict):
        return None
    name = (crs.get("properties") or {}).get("name", "")
    m = _CRS_RE.search(str(name))
    return int(m.group(1)) if m else None


def _build_reprojector(epsg: int):
    """Return a shapely-compatible (x, y) -> (lon, lat) transform fn, or None."""
    from pyproj import Transformer

    transformer = Transformer.from_crs(epsg, _WGS84, always_xy=True)
    return transformer.transform


class GeoJsonExtractor(HttpExtractor):
    def extract(
        self, url: str, reproject: bool = True
    ) -> Generator[dict[str, Any], None, None]:
        """Yield GeoJSON feature dicts, normalised to EPSG:4326.

        When the source declares a non-WGS84 CRS (and `reproject` is True) every
        feature geometry is transformed to lon/lat so downstream loaders can
        store it directly. Features whose geometry fails to transform are
        yielded unchanged (the loader then skips them on its own).
        """
        data = self.get_json(url)

        if isinstance(data, dict) and data.get("type") == "FeatureCollection":
            features = data.get("features", [])
            epsg = _parse_epsg(data) if reproject else None
            logger.info(
                "GeoJSON: %d features from %s (crs=%s)", len(features), url, epsg or "wgs84"
            )
            if epsg and epsg != _WGS84:
                yield from self._reproject(features, epsg)
            else:
                yield from features
        elif isinstance(data, list):
            # Some endpoints return a bare array of feature objects (assumed WGS84)
            yield from data
        else:
            logger.warning("Unexpected GeoJSON structure from %s: %s", url, type(data))

    def _reproject(
        self, features: list[dict[str, Any]], epsg: int
    ) -> Generator[dict[str, Any], None, None]:
        from shapely.geometry import mapping, shape
        from shapely.ops import transform as shp_transform

        fn = _build_reprojector(epsg)
        for feat in features:
            geom = feat.get("geometry")
            if geom:
                try:
                    feat = {**feat, "geometry": mapping(shp_transform(fn, shape(geom)))}
                except Exception as exc:
                    logger.debug("reproject failed (epsg=%s): %s", epsg, exc)
            yield feat

    def extract_all(self, url: str, reproject: bool = True) -> list[dict[str, Any]]:
        return list(self.extract(url, reproject=reproject))
