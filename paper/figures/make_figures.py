#!/usr/bin/env python3
"""Generate the four paper figures from paper/analysis/results.json.

Every number shown on a figure (r, R^2, p, n, turnout percentages) is read
from results.json. Nothing in this file recomputes a statistic — the only
place numpy.polyfit is used is to draw the *geometry* of a trend line; the
r / R^2 / p / n values printed on the figure always come from the JSON.

Design follows the project's `dataviz` skill: one sequential hue (blue) for
magnitude (the choropleth), the same categorical slot-1 blue for a single
scatter series (so no legend box is needed), significance encoded by line
style (not color, since IEEE proceedings are frequently printed in
greyscale), and no confidence band on the n=10 fit (Fig. 4 honesty
requirement).

Run: paper/.venv/bin/python paper/figures/make_figures.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, PathPatch
from matplotlib.path import Path as MplPath

ROOT = Path(__file__).resolve().parents[1]  # paper/
ANALYSIS = ROOT / "analysis"
DATA = ANALYSIS / "data"
FIGURES = ROOT / "figures"
FIGURES.mkdir(exist_ok=True)

CM = 1 / 2.54  # inches per centimetre — figsize is always given in inches

RESULTS = json.loads((ANALYSIS / "results.json").read_text(encoding="utf-8"))

# ---------------------------------------------------------------------------
# Palette — from the dataviz skill's validated reference instance
# (references/palette.md). Categorical slot 1 = blue; the sequential blue
# ramp (steps 100..700) is used verbatim for the choropleth.
# ---------------------------------------------------------------------------
BLUE = "#2a78d6"        # categorical slot 1 (single-series marks)
BLUE_DARK_TEXT = "#184f95"
INK = "#0b0b0b"          # primary ink
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"    # axis / gridline ink
GRID = "#e1e0d9"         # hairline gridline
BASELINE = "#c3c2b7"     # axis baseline
SURFACE = "#fcfcfb"

SEQUENTIAL_BLUE_STEPS = [
    "#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7",
    "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b",
]
SEQ_CMAP = LinearSegmentedColormap.from_list("dataviz_seq_blue", SEQUENTIAL_BLUE_STEPS)

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
    "font.size": 8,
    "axes.titlesize": 8.5,
    "axes.labelsize": 8,
    "xtick.labelsize": 7.5,
    "ytick.labelsize": 7.5,
    "legend.fontsize": 7.5,
    "figure.facecolor": "white",
    "savefig.facecolor": "white",
    "axes.edgecolor": BASELINE,
    "axes.labelcolor": INK,
    "text.color": INK,
    "xtick.color": INK_SECONDARY,
    "ytick.color": INK_SECONDARY,
    "axes.grid": False,
    "axes.linewidth": 0.7,
    # Vector text, not Type-3 bitmapped glyphs — required for a clean vector PDF.
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
})


def read_csv(name: str) -> list[dict]:
    with (DATA / name).open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def fmt_p(p: float) -> str:
    return "p < 0.001" if p < 0.001 else f"p = {p:.2f}"


def stats_box(ax, lines: list[str], loc: str = "upper right", **kwargs):
    """A small muted annotation box carrying only numbers read from results.json."""
    x, ha = (0.97, "right") if "right" in loc else (0.03, "left")
    y, va = (0.95, "top") if "upper" in loc else (0.05, "bottom")
    ax.text(
        x, y, "\n".join(lines), transform=ax.transAxes, ha=ha, va=va,
        fontsize=7.5, color=INK, linespacing=1.5,
        bbox=dict(boxstyle="round,pad=0.35", facecolor=SURFACE,
                   edgecolor=BASELINE, linewidth=0.6, alpha=0.95),
        **kwargs,
    )


def fitted_line(x, y):
    """Least-squares line for the *geometry* only — never the reported r/R^2/p/n."""
    slope, intercept = np.polyfit(x, y, 1)
    xs = np.linspace(min(x), max(x), 50)
    return xs, slope * xs + intercept


# ===========================================================================
# Figure 1 — system architecture
# ===========================================================================

def make_fig1_architecture():
    fig, ax = plt.subplots(figsize=(18.1 * CM, 12.0 * CM))
    ax.set_xlim(0, 104)
    ax.set_ylim(-5, 100)
    ax.axis("off")

    service_style = dict(boxstyle="round,pad=0.02,rounding_size=0.02",
                          facecolor="#dbe9fb", edgecolor=INK, linewidth=0.9)
    external_style = dict(boxstyle="round,pad=0.02,rounding_size=0.02",
                           facecolor="none", edgecolor=INK_SECONDARY,
                           linewidth=0.8, linestyle=(0, (4, 2)))

    def box(cx, cy, w, h, label, sub=None, style=service_style, fontsize=7.6):
        b = FancyBboxPatch((cx - w / 2, cy - h / 2), w, h, **style, mutation_scale=1)
        ax.add_patch(b)
        if sub:
            ax.text(cx, cy + h * 0.16, label, ha="center", va="center",
                     fontsize=fontsize, fontweight="bold", color=INK)
            ax.text(cx, cy - h * 0.26, sub, ha="center", va="center",
                     fontsize=fontsize - 1.2, color=INK_SECONDARY)
        else:
            ax.text(cx, cy, label, ha="center", va="center",
                     fontsize=fontsize, fontweight="bold", color=INK)
        return (cx, cy, w, h)

    def arrow(p_from, p_to, label=None, label_dx=2.0, style="-", color=INK,
              lw=1.0, label_side="right", fontsize=6.6):
        a = FancyArrowPatch(p_from, p_to, arrowstyle="-|>", mutation_scale=9,
                             linewidth=lw, color=color, linestyle=style,
                             shrinkA=1, shrinkB=1, zorder=1)
        ax.add_patch(a)
        if label:
            mx, my = (p_from[0] + p_to[0]) / 2, (p_from[1] + p_to[1]) / 2
            dx = label_dx if label_side == "right" else -label_dx
            ax.text(mx + dx, my, label, ha="left" if label_side == "right" else "right",
                     va="center", fontsize=fontsize, color=INK_SECONDARY)

    # Main pipeline centreline (CX); uptime-kuma lives in a reserved right
    # margin so its monitoring arrow never has to cross another service box.
    CX = 40
    y_source, y_etl, y_data, y_app, y_gateway, y_browser = 94, 79, 62, 45, 26, 8

    box(CX, y_source, 64, 8, "opendata.leipzig.de / statistik.leipzig.de",
        style=external_style, fontsize=7.2)

    box(CX, y_etl, 26, 9, "etl", "scheduler (httpx + tenacity)")
    db = box(CX - 18, y_data, 26, 10, "db", "PostgreSQL 16 + PostGIS")
    redis = box(CX + 18, y_data, 22, 10, "redis", "query cache, 128 MB LRU")
    box(CX, y_app, 30, 9, "backend", "FastAPI, async psycopg3")
    box(CX + 30, y_app, 22, 9, "frontend", "React SPA (static build)")
    box(CX, y_gateway, 34, 9, "nginx", "reverse proxy + TLS")
    box(CX, y_browser, 30, 7.5, "Browser", style=external_style, fontsize=7.6)

    # Data flow (solid, source -> browser)
    arrow((CX, y_source - 4), (CX, y_etl + 4.5), "extract, raw + audit log")
    arrow((CX - 4, y_etl - 4.5), (db[0], y_data + 5), "normalise + upsert",
          label_dx=-2.0, label_side="left")
    arrow((db[0], y_data - 5), (CX - 6, y_app + 4.5), "async SQL, mart views",
          label_dx=-2.0, label_side="left")
    arrow((redis[0], y_data - 5), (CX + 8, y_app + 4.5), "cache 60–3600s TTL")
    arrow((CX, y_app - 4.5), (CX, y_gateway + 4.5), "/api/*, JSON (orjson)",
          label_dx=-2.0, label_side="left")
    arrow((CX + 30, y_app - 4.5), (CX + 8, y_gateway + 4.5), "/*, static SPA")
    arrow((CX, y_gateway - 4.5), (CX, y_browser + 3.75), ":443 HTTPS (Let's Encrypt)",
          label_dx=-2.0, label_side="left")

    # etl writes only into db -- no path to backend (explicit per ARCHITECTURE.md).
    # Placed clear of the etl->db arrow, in the open gap right of redis's column.
    ax.text(CX + 30, (y_etl + y_data) / 2 + 1.5,
            "etl has no network path\nto backend — writes to db only",
            ha="center", va="center", fontsize=6.1, color=INK_MUTED, style="italic")

    # uptime-kuma: shares the etl row, far enough right that its box and
    # monitoring arrow sit entirely in that row's open space (nothing else
    # occupies x > 53 at y_etl) — no crossing, no overlap with another box.
    uk_x = 94
    uk_y = y_etl
    uk = box(uk_x, uk_y, 18, 9, "uptime-kuma", "monitoring")
    arrow_start = (uk_x - 9, uk_y)
    arrow_end = (75, uk_y)
    arrow(arrow_start, arrow_end, style=(0, (1, 1.6)), color=INK_MUTED, lw=0.8)
    ax.text((arrow_start[0] + arrow_end[0]) / 2, uk_y + 6.0,
            "HTTP healthchecks on\nall six other services",
            ha="center", va="bottom", fontsize=6.0, color=INK_MUTED, style="italic")

    # Single legend note for the two dashed boxes, instead of a per-box
    # caption that risks colliding with the box border.
    ax.text(CX, y_browser - 6.8,
            "dashed boxes: external endpoints (data sources, browser) — "
            "not counted among the seven services",
            ha="center", va="center", fontsize=6.2, color=INK_MUTED, style="italic")

    ax.set_title(
        "Leipzig Open Data Dashboard — seven services, source to browser",
        fontsize=9.2, color=INK, pad=8,
    )
    fig.savefig(FIGURES / "fig1_architecture.pdf", format="pdf", bbox_inches="tight")
    plt.close(fig)


# ===========================================================================
# Figure 2 — turnout choropleth
# ===========================================================================

def ring_to_path(ring: list[list[float]]):
    pts = ring
    if len(pts) >= 2 and tuple(pts[0]) == tuple(pts[-1]):
        pts = pts[:-1]
    n = len(pts)
    verts = pts + [pts[0]]
    codes = [MplPath.MOVETO] + [MplPath.LINETO] * (n - 1) + [MplPath.CLOSEPOLY]
    return verts, codes


def geometry_patch(geom: dict, **kwargs) -> PathPatch:
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    verts_all, codes_all = [], []
    for poly in polys:
        for ring in poly:
            v, c = ring_to_path(ring)
            verts_all.extend(v)
            codes_all.extend(c)
    return PathPatch(MplPath(verts_all, codes_all), **kwargs)


def load_boundaries():
    rows = read_csv("boundaries_geo.csv")
    out = {}
    for r in rows:
        out[r["code"]] = {"name": r["name"], "geom": json.loads(r["geom"])}
    return out


def make_fig2_choropleth():
    boundaries = load_boundaries()
    votes = RESULTS["ortsteil"]["votes"]

    turnout_pct = {
        code: votes[code]["turnout"] * 100
        for code in boundaries
        if code in votes and "turnout" in votes[code]
    }
    vmin, vmax = min(turnout_pct.values()), max(turnout_pct.values())

    fig, ax = plt.subplots(figsize=(8.8 * CM, 9.3 * CM))

    for code, b in boundaries.items():
        v = turnout_pct.get(code)
        facecolor = SEQ_CMAP((v - vmin) / (vmax - vmin)) if v is not None else "#eeeeee"
        patch = geometry_patch(b["geom"], facecolor=facecolor, edgecolor="white",
                                linewidth=0.4, zorder=1)
        ax.add_patch(patch)

    ax.set_aspect(1 / np.cos(np.radians(51.34)))
    ax.autoscale_view()
    ax.axis("off")

    sm = plt.cm.ScalarMappable(cmap=SEQ_CMAP, norm=plt.Normalize(vmin, vmax))
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, fraction=0.046, pad=0.03, shrink=0.75)
    cbar.set_label("Turnout (%)", fontsize=8, color=INK)
    cbar.ax.tick_params(labelsize=7.5, color=INK_SECONDARY, labelcolor=INK_SECONDARY)
    cbar.outline.set_edgecolor(BASELINE)
    cbar.outline.set_linewidth(0.6)

    # Selectively label only the extremes (never a number on every polygon).
    max_code = max(turnout_pct, key=turnout_pct.get)
    min_code = min(turnout_pct, key=turnout_pct.get)
    for code, tag in [(max_code, "highest"), (min_code, "lowest")]:
        name = boundaries[code]["name"]
        v = turnout_pct[code]
        cx, cy = polygon_centroid(boundaries[code]["geom"])
        ax.annotate(
            f"{name}\n{v:.0f}% ({tag})", xy=(cx, cy), xytext=(0, 0),
            textcoords="offset points", ha="center", va="center",
            fontsize=6.6, color=INK,
            bbox=dict(boxstyle="round,pad=0.22", facecolor=SURFACE,
                      edgecolor=BASELINE, linewidth=0.5, alpha=0.92),
            zorder=5,
        )

    ax.set_title(
        f"Voter turnout by Ortsteil\nEuropean election 2024 (n = {len(turnout_pct)})",
        fontsize=8.6, color=INK, pad=6,
    )
    fig.savefig(FIGURES / "fig2_choropleth.pdf", format="pdf", bbox_inches="tight")
    plt.close(fig)


def polygon_centroid(geom: dict) -> tuple[float, float]:
    """Area-weighted centroid of the largest ring — good enough for label placement."""
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    best_area, best_c = -1.0, (0.0, 0.0)
    for poly in polys:
        ring = poly[0]
        pts = ring[:-1] if ring[0] == ring[-1] else ring
        x = np.array([p[0] for p in pts])
        y = np.array([p[1] for p in pts])
        x2, y2 = np.roll(x, -1), np.roll(y, -1)
        cross = x * y2 - x2 * y
        area = cross.sum() / 2.0
        if abs(area) < 1e-12:
            continue
        cx = ((x + x2) * cross).sum() / (6 * area)
        cy = ((y + y2) * cross).sum() / (6 * area)
        if abs(area) > best_area:
            best_area, best_c = abs(area), (cx, cy)
    return best_c


# ===========================================================================
# Figure 3 — strongest correlation scatter (turnout vs single-parent share)
# ===========================================================================

def make_fig3_scatter():
    shares = RESULTS["ortsteil"]["shares"]
    votes = RESULTS["ortsteil"]["votes"]
    stat = RESULTS["ortsteil"]["correlations"]["turnout|single_parent"]

    codes = sorted(
        c for c in shares
        if c in votes and "single_parent" in shares[c] and "turnout" in votes[c]
    )
    x = np.array([shares[c]["single_parent"] * 100 for c in codes])
    y = np.array([votes[c]["turnout"] * 100 for c in codes])

    fig, ax = plt.subplots(figsize=(8.8 * CM, 7.6 * CM))

    ax.scatter(x, y, s=22, facecolor=BLUE, edgecolor=SURFACE, linewidth=0.6,
               alpha=0.9, zorder=3)

    lx, ly = fitted_line(x, y)
    ax.plot(lx, ly, color=BLUE_DARK_TEXT, linewidth=1.6, zorder=2)

    ax.set_xlabel("Single-parent household share (%)")
    ax.set_ylabel("Turnout (%)")
    ax.set_title(
        f"Turnout vs. single-parent share, {stat['n']} Ortsteile\n"
        "European election 2024",
        fontsize=8.6, pad=6,
    )

    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color(BASELINE)
    ax.tick_params(colors=INK_SECONDARY)
    ax.grid(axis="both", color=GRID, linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)

    stats_box(ax, [
        f"r = {stat['r']:.3f}",
        f"R² = {stat['r2']:.3f}",
        f"n = {stat['n']}",
    ], loc="upper right")

    fig.savefig(FIGURES / "fig3_scatter.pdf", format="pdf", bbox_inches="tight")
    plt.close(fig)


# ===========================================================================
# Figure 4 — MAUP: AfD share vs. unemployment share, two spatial resolutions
# ===========================================================================

def _pairing_xy(level: str):
    shares = RESULTS[level]["shares"]
    votes = RESULTS[level]["votes"]
    codes = sorted(
        c for c in shares
        if c in votes and "unemployment" in shares[c] and "AfD" in votes[c]
    )
    x = np.array([shares[c]["unemployment"] * 100 for c in codes])
    y = np.array([votes[c]["AfD"] * 100 for c in codes])
    return x, y


def make_fig4_maup():
    key = "AfD|unemployment"
    cmp = RESULTS["maup"][key]
    stat_ot, stat_sb = cmp["ortsteil"], cmp["stadtbezirk"]

    x_ot, y_ot = _pairing_xy("ortsteil")
    x_sb, y_sb = _pairing_xy("stadtbezirk")

    # Shared axis conventions across both panels — required for the sign
    # reversal to read as a property of the data, not of the axes.
    all_x = np.concatenate([x_ot, x_sb])
    all_y = np.concatenate([y_ot, y_sb])
    pad_x = (all_x.max() - all_x.min()) * 0.10
    pad_y = (all_y.max() - all_y.min()) * 0.10
    xlim = (all_x.min() - pad_x, all_x.max() + pad_x)
    ylim = (all_y.min() - pad_y, all_y.max() + pad_y)

    fig, axes = plt.subplots(1, 2, figsize=(18.1 * CM, 8.3 * CM), sharex=True, sharey=True)

    panels = [
        (axes[0], x_ot, y_ot, stat_ot, f"Ortsteil level (n = {stat_ot['n']})", False),
        (axes[1], x_sb, y_sb, stat_sb, f"Stadtbezirk level (n = {stat_sb['n']})", True),
    ]

    for ax, x, y, stat, title, significant in panels:
        marker_size = 20 if not significant else 42
        ax.scatter(x, y, s=marker_size, facecolor=BLUE, edgecolor=SURFACE,
                   linewidth=0.6, alpha=0.9, zorder=3)

        lx, ly = fitted_line(x, y)
        # Significance encoded by line style (readable in greyscale), not
        # by color alone — dashed/thin = not significant, solid/bold = significant.
        # No confidence band on the n=10 fit (or the n=63 fit, for parity).
        if significant:
            ax.plot(lx, ly, color=BLUE_DARK_TEXT, linewidth=1.8,
                    linestyle="-", zorder=2)
        else:
            ax.plot(lx, ly, color=INK_MUTED, linewidth=1.3,
                    linestyle=(0, (4, 2)), zorder=2)

        ax.set_xlim(xlim)
        ax.set_ylim(ylim)
        ax.set_xlabel("Unemployment share (%)")
        ax.set_title(title, fontsize=8.6, pad=5)

        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
        for spine in ("left", "bottom"):
            ax.spines[spine].set_color(BASELINE)
        # Both panels keep their y tick labels even though the scale is
        # shared — a reader glancing at one panel alone must still be able
        # to read it (matplotlib hides them on the second axis by default).
        ax.tick_params(colors=INK_SECONDARY, labelleft=True)
        ax.grid(axis="both", color=GRID, linewidth=0.6, zorder=0)
        ax.set_axisbelow(True)

        sig_label = "significant (α = 0.05)" if significant else "not significant"
        stats_box(ax, [
            f"r = {stat['r']:+.3f}",
            fmt_p(stat["p"]),
            f"n = {stat['n']}",
            sig_label,
        ], loc="upper right" if not significant else "lower right")

    axes[0].set_ylabel("AfD vote share (%)")
    axes[1].set_ylabel("AfD vote share (%)")

    fig.suptitle(
        "AfD vote share vs. unemployment share — same votes, two spatial resolutions",
        fontsize=9.2, y=1.03,
    )
    fig.text(
        0.5, -0.06,
        "Same underlying data at every point; only the spatial aggregation differs.\n"
        "Neither panel is the ‘correct’ scale — this is the Modifiable Areal Unit Problem, "
        f"not a change in the votes (Δr = {cmp['delta_r']:+.3f}). "
        "At n = 10, treat the right-hand r with caution.",
        ha="center", va="top", fontsize=6.8, color=INK_SECONDARY,
    )

    fig.savefig(FIGURES / "fig4_maup.pdf", format="pdf", bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    make_fig1_architecture()
    make_fig2_choropleth()
    make_fig3_scatter()
    make_fig4_maup()
    print("wrote fig1_architecture.pdf, fig2_choropleth.pdf, fig3_scatter.pdf, fig4_maup.pdf")
