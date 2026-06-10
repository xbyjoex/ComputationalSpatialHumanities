import type { StyleSpecification, LayerSpecification } from "maplibre-gl";

/**
 * Lädt das CARTO-Dark-Matter-Style-JSON und färbt es auf die
 * Gotham-Palette um — Wasser stahlblau, Straßen als Blueprint-Linien,
 * Labels gedämpft. Ergebnis: eine eigene Leipzig-Karte statt einer
 * generischen Drittanbieter-Basemap.
 */
const STYLE_URL = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";

const C = {
  bg: "#0a1015",
  land: "#0c141a",
  water: "#0e1f2c",
  waterway: "#12283a",
  green: "#0d171c",
  building: "#111a22",
  roadMinor: "#16222c",
  roadMid: "#1c2c39",
  roadMajor: "#273d4f",
  roadCasing: "#0a1015",
  rail: "#1a2a36",
  boundary: "#2b4253",
  aeroway: "#142028",
  text: "#5d7a8d",
  textPlace: "#8aa7ba",
  textHalo: "#0a1015",
} as const;

type Paintable = LayerSpecification & {
  paint?: Record<string, unknown>;
};

function set(layer: Paintable, key: string, value: unknown) {
  if (!layer.paint) layer.paint = {};
  layer.paint[key] = value;
}

function patch(style: StyleSpecification): StyleSpecification {
  for (const layer of style.layers as Paintable[]) {
    const id = layer.id.toLowerCase();

    switch (layer.type) {
      case "background":
        set(layer, "background-color", C.bg);
        break;

      case "fill":
        if (id.includes("water")) set(layer, "fill-color", C.water);
        else if (/park|green|wood|grass|landcover|cemetery|pitch|garden/.test(id))
          set(layer, "fill-color", C.green);
        else if (id.includes("building")) {
          set(layer, "fill-color", C.building);
          set(layer, "fill-outline-color", C.bg);
        } else if (id.includes("aeroway")) set(layer, "fill-color", C.aeroway);
        else set(layer, "fill-color", C.land);
        break;

      case "line":
        if (id.includes("waterway")) set(layer, "line-color", C.waterway);
        else if (/boundary|admin/.test(id)) set(layer, "line-color", C.boundary);
        else if (/rail|transit/.test(id)) set(layer, "line-color", C.rail);
        else if (/case|casing/.test(id)) set(layer, "line-color", C.roadCasing);
        else if (/motorway|trunk|highway_major|primary/.test(id))
          set(layer, "line-color", C.roadMajor);
        else if (/secondary|tertiary|street|highway_minor/.test(id))
          set(layer, "line-color", C.roadMid);
        else set(layer, "line-color", C.roadMinor);
        break;

      case "symbol":
        set(layer, "text-color", /place|city|town/.test(id) ? C.textPlace : C.text);
        set(layer, "text-halo-color", C.textHalo);
        break;
    }
  }
  return style;
}

let cached: Promise<StyleSpecification> | null = null;

export function loadGothamStyle(): Promise<StyleSpecification> {
  if (!cached) {
    cached = fetch(STYLE_URL)
      .then((r) => {
        if (!r.ok) throw new Error(`Basemap-Style ${r.status}`);
        return r.json();
      })
      .then(patch)
      .catch((err) => {
        cached = null; // beim nächsten Versuch erneut laden
        throw err;
      });
  }
  return cached;
}

/** Stabile Signalfarbe je Datensatz für die Datenebene. */
export const FEATURE_COLORS = [
  "#53b9e8",
  "#3dd68c",
  "#ffb02e",
  "#9d8cff",
  "#ff6e5e",
  "#9adcff",
  "#e8d553",
  "#56e0c8",
] as const;

export function datasetColor(datasetId: string): string {
  let h = 0;
  for (let i = 0; i < datasetId.length; i++) {
    h = (h * 31 + datasetId.charCodeAt(i)) | 0;
  }
  return FEATURE_COLORS[Math.abs(h) % FEATURE_COLORS.length];
}
