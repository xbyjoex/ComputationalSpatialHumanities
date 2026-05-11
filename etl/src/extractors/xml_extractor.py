"""Extract tabular records from XML sources."""

from __future__ import annotations

import logging
from typing import Any
from xml.etree import ElementTree as ET

from .base import HttpExtractor

logger = logging.getLogger(__name__)


def _strip_ns(tag: str) -> str:
    """Remove XML namespace prefix from a tag."""
    return tag.split("}")[-1] if "}" in tag else tag


def _elem_to_dict(elem: ET.Element) -> dict[str, str]:
    """Flatten direct children of an element into a key→text dict."""
    rec: dict[str, str] = {}
    # Include element attributes
    for k, v in elem.attrib.items():
        rec[_strip_ns(k)] = v
    for child in elem:
        key = _strip_ns(child.tag)
        text = (child.text or "").strip()
        # If child itself has children, recurse one level as JSON-style prefix
        if len(child):
            sub = _elem_to_dict(child)
            for sk, sv in sub.items():
                rec[f"{key}_{sk}"] = sv
        else:
            rec[key] = text
    return rec


class XmlExtractor(HttpExtractor):
    def extract(self, url: str) -> list[dict[str, Any]]:
        text = self.get_text(url)
        try:
            root = ET.fromstring(text)
        except ET.ParseError as exc:
            logger.error("XML parse error from %s: %s", url, exc)
            return []

        children = list(root)
        if not children:
            return [{"value": (root.text or "").strip()}]

        # Detect repeating row element: all children share the same tag
        child_tags = [_strip_ns(c.tag) for c in children]
        if len(set(child_tags)) == 1:
            # Each child is a row
            records = [_elem_to_dict(c) for c in children]
        else:
            # Single-record flat XML
            records = [_elem_to_dict(root)]

        records = [r for r in records if r]
        logger.info("XML: %d records from %s", len(records), url)
        return records
