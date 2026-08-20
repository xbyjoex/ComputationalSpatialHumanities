#!/usr/bin/env python3
"""Generate the paper figures for the real-estate case study.

The architecture figure is static and kept as-is. Figures 2--4 are regenerated
from Leipzig's public Statistik API dumps:

* Wohnungsmieten, kleinraeumig (Kategorie 6, Rubrik 6)
* Nettoeinkommen, kleinraeumig (Kategorie 9, Rubrik 1)
* Wohnungsbestand, kleinraeumig (Kategorie 6, Rubrik 5)
* Grundsicherung SGB II, kleinraeumig (Kategorie 4, Rubrik 4)

Matplotlib is deliberately not required here; the repo's paper environment is
small, so the figures are drawn directly as vector PDFs with ReportLab.
"""

from __future__ import annotations

import csv
import json
import math
import urllib.request
from pathlib import Path

import numpy as np
from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = ROOT / "analysis"
DATA = ANALYSIS / "data"
FIGURES = ROOT / "figures"
FIGURES.mkdir(exist_ok=True)

CM = 72 / 2.54

INK = HexColor("#0b0b0b")
INK_SECONDARY = HexColor("#52514e")
INK_MUTED = HexColor("#898781")
GRID = HexColor("#e1e0d9")
BASELINE = HexColor("#c3c2b7")
SURFACE = HexColor("#fcfcfb")
BLUE = HexColor("#2a78d6")
BLUE_DARK = HexColor("#184f95")
MISSING = HexColor("#eeeeee")

RAMP = [
    "#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7",
    "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281",
    "#0d366b",
]

API_SOURCES = {
    "rent": (
        "real_estate_rent.json",
        "https://statistik.leipzig.de/opendata/api/kdvalues?"
        "kategorie_nr=6&rubrik_nr=6&periode=y&format=json",
    ),
    "income": (
        "real_estate_income.json",
        "https://statistik.leipzig.de/opendata/api/kdvalues?"
        "kategorie_nr=9&rubrik_nr=1&periode=y&format=json",
    ),
    "stock": (
        "real_estate_housing_stock.json",
        "https://statistik.leipzig.de/opendata/api/kdvalues?"
        "kategorie_nr=6&rubrik_nr=5&periode=y&format=json",
    ),
    "sgb2": (
        "real_estate_sgb2.json",
        "https://statistik.leipzig.de/opendata/api/kdvalues?"
        "kategorie_nr=4&rubrik_nr=4&periode=y&format=json",
    ),
}

TMP_FALLBACKS = {
    "rent": Path("/tmp/leipzig_rent.json"),
    "income": Path("/tmp/leipzig_income.json"),
    "stock": Path("/tmp/leipzig_housing_stock.json"),
    "sgb2": Path("/tmp/leipzig_sgb2.json"),
}


def api_rows(source: str) -> list[dict]:
    """Read cached API rows, or fetch them if the cache is absent."""
    name, url = API_SOURCES[source]
    cache_path = DATA / name
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))
    tmp_path = TMP_FALLBACKS[source]
    if tmp_path.exists():
        return json.loads(tmp_path.read_text(encoding="utf-8"))

    print(f"fetching {url}")
    with urllib.request.urlopen(url, timeout=30) as response:
        data = response.read().decode("utf-8")
    cache_path.write_text(data, encoding="utf-8")
    return json.loads(data)


def parse_value(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in {".", "-"}:
        return None
    return float(text.replace(",", "."))


def series(source: str, metric: str, year: int = 2023, level: str = "ortsteil") -> dict[str, float]:
    out: dict[str, float] = {}
    for row in api_rows(source):
        if row.get("name") != metric or str(row.get("jahr")) != str(year):
            continue
        place = row.get(level)
        if not place:
            continue
        value = parse_value(row.get("wert"))
        if value is not None:
            out[place] = value
    return out


def paired(a: dict[str, float], b: dict[str, float]) -> tuple[list[str], np.ndarray, np.ndarray]:
    names = sorted(set(a) & set(b))
    return names, np.array([a[name] for name in names], dtype=float), np.array([b[name] for name in names], dtype=float)


def pearson(xs: np.ndarray, ys: np.ndarray) -> tuple[float, float]:
    r = float(np.corrcoef(xs, ys)[0, 1])
    return r, r * r


def fitted_line(xs: np.ndarray, ys: np.ndarray) -> tuple[float, float]:
    slope, intercept = np.polyfit(xs, ys, 1)
    return float(slope), float(intercept)


def nice_range(values: np.ndarray, pad: float = 0.08) -> tuple[float, float]:
    lo, hi = float(np.min(values)), float(np.max(values))
    width = hi - lo or 1.0
    return lo - width * pad, hi + width * pad


def draw_text(
    c: canvas.Canvas,
    x: float,
    y: float,
    text: str,
    size: float = 7.2,
    color=INK,
    font: str = "Helvetica",
    align: str = "left",
) -> None:
    c.setFillColor(color)
    c.setFont(font, size)
    if align == "center":
        x -= stringWidth(text, font, size) / 2
    elif align == "right":
        x -= stringWidth(text, font, size)
    c.drawString(x, y, text)


def setup_page(path: Path, width_cm: float, height_cm: float) -> tuple[canvas.Canvas, float, float]:
    width, height = width_cm * CM, height_cm * CM
    c = canvas.Canvas(str(path), pagesize=(width, height))
    c.setTitle(path.name)
    return c, width, height


def interp_color(hexes: list[str], t: float):
    t = max(0.0, min(1.0, t))
    pos = t * (len(hexes) - 1)
    i = int(math.floor(pos))
    if i >= len(hexes) - 1:
        return HexColor(hexes[-1])
    frac = pos - i
    a, b = colors.HexColor(hexes[i]), colors.HexColor(hexes[i + 1])
    return colors.Color(
        a.red + (b.red - a.red) * frac,
        a.green + (b.green - a.green) * frac,
        a.blue + (b.blue - a.blue) * frac,
    )


def collect_coords(geom: dict):
    polygons = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    for polygon in polygons:
        for ring in polygon:
            for x, y in ring:
                yield x, y


def load_boundaries() -> dict[str, dict]:
    path = DATA / "boundaries_geo.csv"
    if not path.exists():
        raise FileNotFoundError(
            "paper/analysis/data/boundaries_geo.csv is required for the choropleth geometry"
        )
    out: dict[str, dict] = {}
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            out[row["name"]] = json.loads(row["geom"])
    return out


def draw_axes(
    c: canvas.Canvas,
    x0: float,
    y0: float,
    width: float,
    height: float,
    xlim: tuple[float, float],
    ylim: tuple[float, float],
    xlabel: str,
    ylabel: str,
) -> tuple:
    c.setStrokeColor(BASELINE)
    c.setLineWidth(0.6)
    c.line(x0, y0, x0 + width, y0)
    c.line(x0, y0, x0, y0 + height)

    c.setStrokeColor(GRID)
    c.setLineWidth(0.35)
    for i in range(1, 5):
        c.line(x0 + width * i / 4, y0, x0 + width * i / 4, y0 + height)
        c.line(x0, y0 + height * i / 4, x0 + width, y0 + height * i / 4)

    def sx(value: float) -> float:
        return x0 + (value - xlim[0]) / (xlim[1] - xlim[0]) * width

    def sy(value: float) -> float:
        return y0 + (value - ylim[0]) / (ylim[1] - ylim[0]) * height

    for i in range(5):
        xv = xlim[0] + (xlim[1] - xlim[0]) * i / 4
        yv = ylim[0] + (ylim[1] - ylim[0]) * i / 4
        draw_text(c, sx(xv), y0 - 10, f"{xv:.0f}", 6.3, INK_SECONDARY, align="center")
        draw_text(c, x0 - 5, sy(yv) - 2, f"{yv:.0f}", 6.3, INK_SECONDARY, align="right")

    draw_text(c, x0 + width / 2, y0 - 25, xlabel, 7.2, INK, align="center")
    c.saveState()
    c.translate(x0 - 31, y0 + height / 2)
    c.rotate(90)
    draw_text(c, 0, 0, ylabel, 7.2, INK, align="center")
    c.restoreState()

    return sx, sy


def stats_box(c: canvas.Canvas, x: float, y: float, lines: list[str]) -> None:
    width = max(stringWidth(line, "Helvetica", 7) for line in lines) + 12
    height = len(lines) * 10 + 7
    left = x - width
    c.setFillColor(SURFACE)
    c.setStrokeColor(BASELINE)
    c.setLineWidth(0.5)
    c.roundRect(left, y - height, width, height, 4, fill=1, stroke=1)
    for i, line in enumerate(lines):
        draw_text(c, left + 6, y - 12 - i * 10, line, 7, INK)


def make_fig1_architecture() -> None:
    path = FIGURES / "fig1_architecture.pdf"
    if not path.exists():
        raise FileNotFoundError("fig1_architecture.pdf is static and should already exist")


def make_fig2_choropleth() -> None:
    values = series("rent", "Gesamtmiete")
    boundaries = load_boundaries()
    c, width, height = setup_page(FIGURES / "fig2_choropleth.pdf", 8.8, 9.3)

    draw_text(
        c,
        width / 2,
        height - 16,
        "Reported total rent metric by Ortsteil, 2023",
        8.6,
        INK,
        "Helvetica-Bold",
        "center",
    )

    lat0 = 51.34
    projected = []
    for geom in boundaries.values():
        projected.extend((x * math.cos(math.radians(lat0)), y) for x, y in collect_coords(geom))
    minx, maxx = min(x for x, _ in projected), max(x for x, _ in projected)
    miny, maxy = min(y for _, y in projected), max(y for _, y in projected)

    map_x0, map_y0, map_w, map_h = 14, 30, width - 56, height - 58
    scale = min(map_w / (maxx - minx), map_h / (maxy - miny))
    offx = map_x0 + (map_w - (maxx - minx) * scale) / 2
    offy = map_y0 + (map_h - (maxy - miny) * scale) / 2

    def tx(lon: float, lat: float) -> tuple[float, float]:
        x = lon * math.cos(math.radians(lat0))
        return offx + (x - minx) * scale, offy + (lat - miny) * scale

    vals = list(values.values())
    vmin, vmax = min(vals), max(vals)
    for name, geom in boundaries.items():
        value = values.get(name)
        fill = MISSING if value is None else interp_color(RAMP, (value - vmin) / (vmax - vmin))
        c.setFillColor(fill)
        c.setStrokeColor(colors.white)
        c.setLineWidth(0.25)
        polygons = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        for polygon in polygons:
            path = c.beginPath()
            for i, (lon, lat) in enumerate(polygon[0]):
                x, y = tx(lon, lat)
                if i == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            path.close()
            c.drawPath(path, fill=1, stroke=1)

    legend_x, legend_y, legend_w, legend_h = width - 32, 40, 8, height - 85
    steps = 36
    for i in range(steps):
        color = interp_color(RAMP, i / (steps - 1))
        c.setFillColor(color)
        c.rect(legend_x, legend_y + legend_h * i / steps, legend_w, legend_h / steps + 0.5, fill=1, stroke=0)
    c.setStrokeColor(BASELINE)
    c.rect(legend_x, legend_y, legend_w, legend_h, fill=0, stroke=1)
    draw_text(c, legend_x + legend_w + 4, legend_y - 1, f"{vmin:.1f}", 6.3, INK_SECONDARY)
    draw_text(c, legend_x + legend_w + 4, legend_y + legend_h - 4, f"{vmax:.1f}", 6.3, INK_SECONDARY)
    draw_text(c, legend_x + legend_w / 2, legend_y + legend_h + 8, "rent", 6.3, INK_SECONDARY, align="center")

    c.setFillColor(MISSING)
    c.setStrokeColor(BASELINE)
    c.rect(14, 14, 7, 7, fill=1, stroke=1)
    draw_text(c, 25, 15, "missing survey value", 6.3, INK_SECONDARY)
    draw_text(c, width / 2, 15, f"n = {len(values)} numeric Ortsteile", 6.5, INK_SECONDARY, align="center")
    c.showPage()
    c.save()


def make_fig3_scatter() -> None:
    rent = series("rent", "Gesamtmiete")
    income = series("income", "Persönliches Einkommen")
    names, xs, ys = paired(income, rent)
    r, r2 = pearson(xs, ys)
    slope, intercept = fitted_line(xs, ys)

    c, width, height = setup_page(FIGURES / "fig3_scatter.pdf", 8.8, 7.6)
    draw_text(c, width / 2, height - 16, "Reported rent vs. personal net income, 2023", 8.6, INK, "Helvetica-Bold", "center")
    xlim, ylim = nice_range(xs), nice_range(ys)
    sx, sy = draw_axes(c, 42, 38, width - 58, height - 70, xlim, ylim, "Personal net income", "Total rent metric")

    xa, xb = float(np.min(xs)), float(np.max(xs))
    ya, yb = slope * xa + intercept, slope * xb + intercept
    c.setStrokeColor(BLUE_DARK)
    c.setLineWidth(1.2)
    c.line(sx(xa), sy(ya), sx(xb), sy(yb))

    c.setFillColor(BLUE)
    c.setStrokeColor(SURFACE)
    c.setLineWidth(0.4)
    for x, y in zip(xs, ys):
        c.circle(sx(float(x)), sy(float(y)), 2.2, fill=1, stroke=1)

    stats_box(c, width - 12, height - 34, [f"r = {r:+.3f}", f"R2 = {r2:.3f}", f"n = {len(names)}"])
    c.showPage()
    c.save()


def make_fig4_maup() -> None:
    c, width, height = setup_page(FIGURES / "fig4_maup.pdf", 18.1, 8.3)
    draw_text(
        c,
        width / 2,
        height - 16,
        "Residential floor area vs. SGB-II quote, two spatial scales",
        9.0,
        INK,
        "Helvetica-Bold",
        "center",
    )

    panels = []
    for level, title in [("ortsteil", "Ortsteil level"), ("stadtbezirk", "Stadtbezirk level")]:
        area = series("stock", "Wohnfläche je Wohnung", level=level)
        sgb2 = series("sgb2", "SGB-II-Quote", level=level)
        names, xs, ys = paired(sgb2, area)
        r, r2 = pearson(xs, ys)
        slope, intercept = fitted_line(xs, ys)
        panels.append((title, xs, ys, len(names), r, r2, slope, intercept))

    all_x = np.concatenate([panel[1] for panel in panels])
    all_y = np.concatenate([panel[2] for panel in panels])
    xlim, ylim = nice_range(all_x), nice_range(all_y)

    for index, (title, xs, ys, n, r, r2, slope, intercept) in enumerate(panels):
        x0, y0 = 50 + index * (width / 2), 50
        panel_w, panel_h = width / 2 - 70, height - 90
        draw_text(c, x0 + panel_w / 2, height - 32, f"{title} (n = {n})", 8.0, INK, "Helvetica-Bold", "center")
        sx, sy = draw_axes(c, x0, y0, panel_w, panel_h, xlim, ylim, "SGB-II quote (%)", "Floor area per dwelling (m2)")

        xa, xb = float(np.min(xs)), float(np.max(xs))
        ya, yb = slope * xa + intercept, slope * xb + intercept
        c.setStrokeColor(BLUE_DARK if index else INK_MUTED)
        c.setLineWidth(1.2 if index else 1.0)
        if index == 0:
            c.setDash(4, 2)
        c.line(sx(xa), sy(ya), sx(xb), sy(yb))
        c.setDash()

        c.setFillColor(BLUE)
        c.setStrokeColor(SURFACE)
        c.setLineWidth(0.4)
        for x, y in zip(xs, ys):
            c.circle(sx(float(x)), sy(float(y)), 2.2, fill=1, stroke=1)

        stats_box(c, x0 + panel_w - 4, y0 + panel_h - 5, [f"r = {r:+.3f}", f"R2 = {r2:.3f}", f"n = {n}"])

    c.showPage()
    c.save()


if __name__ == "__main__":
    make_fig1_architecture()
    make_fig2_choropleth()
    make_fig3_scatter()
    make_fig4_maup()
    print("wrote fig2_choropleth.pdf, fig3_scatter.pdf, fig4_maup.pdf")
