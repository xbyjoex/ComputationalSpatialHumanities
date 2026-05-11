"""Extract geo features from SHP files served as ZIP archives."""

from __future__ import annotations

import io
import logging
import os
import tempfile
import zipfile
from typing import Any

import shapefile  # pyshp
from shapely.geometry import shape, mapping
from shapely.ops import transform as shapely_transform

from .base import HttpExtractor

logger = logging.getLogger(__name__)


def _reproject_feature(geom_dict: dict, transformer: Any) -> dict:
    """Reproject a GeoJSON geometry dict using a pyproj Transformer."""
    try:
        geom = shape(geom_dict)
        reprojected = shapely_transform(transformer.transform, geom)
        return mapping(reprojected)
    except Exception:
        return geom_dict


def _read_prj(shp_path: str) -> Any | None:
    """Return a pyproj CRS from the .prj sidecar, or None."""
    prj_path = os.path.splitext(shp_path)[0] + ".prj"
    if not os.path.exists(prj_path):
        return None
    try:
        from pyproj import CRS
        with open(prj_path, encoding="utf-8", errors="replace") as f:
            return CRS.from_wkt(f.read())
    except Exception:
        return None


class ShapefileExtractor(HttpExtractor):
    def extract(self, url: str) -> list[dict[str, Any]]:
        raw = self.get_bytes(url)
        features: list[dict[str, Any]] = []

        with tempfile.TemporaryDirectory() as tmpdir:
            # SHP is always distributed as ZIP
            if zipfile.is_zipfile(io.BytesIO(raw)):
                with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                    zf.extractall(tmpdir)
            else:
                # Bare .shp — write it and hope sidecar files are missing (rare)
                with open(os.path.join(tmpdir, "data.shp"), "wb") as f:
                    f.write(raw)

            shp_paths = []
            for root, _, files in os.walk(tmpdir):
                for fname in files:
                    if fname.lower().endswith(".shp"):
                        shp_paths.append(os.path.join(root, fname))

            if not shp_paths:
                logger.warning("No .shp file found in archive from %s", url)
                return []

            for shp_path in shp_paths:
                features.extend(self._read_shapefile(shp_path, url))

        logger.info("SHP: %d features from %s", len(features), url)
        return features

    def _read_shapefile(self, shp_path: str, url: str) -> list[dict[str, Any]]:
        transformer = None
        crs = _read_prj(shp_path)
        if crs is not None and crs.to_epsg() != 4326:
            try:
                from pyproj import CRS, Transformer
                transformer = Transformer.from_crs(crs, CRS.from_epsg(4326), always_xy=True)
            except Exception as exc:
                logger.warning("CRS reproject setup failed for %s: %s", url, exc)

        features = []
        try:
            with shapefile.Reader(shp_path) as sf:
                fields = [f[0] for f in sf.fields[1:]]  # skip DeletionFlag
                for sr in sf.iterShapeRecords():
                    try:
                        geom = sr.shape.__geo_interface__
                    except Exception:
                        continue
                    if geom is None or geom.get("type") is None:
                        continue
                    if transformer:
                        geom = _reproject_feature(geom, transformer)
                    props = {}
                    for k, v in zip(fields, sr.record):
                        # Convert bytes to str (DBF encoding)
                        if isinstance(v, bytes):
                            v = v.decode("utf-8", errors="replace")
                        props[str(k)] = v
                    features.append({"type": "Feature", "geometry": geom, "properties": props})
        except Exception as exc:
            logger.error("Failed to read shapefile %s: %s", shp_path, exc)

        return features
