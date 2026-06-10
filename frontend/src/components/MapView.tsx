import { useRef, useCallback, useState, useEffect, useMemo } from "react";
import { Map, Source, Layer, Popup } from "@vis.gl/react-maplibre";
import type { MapRef, MapLayerMouseEvent, ViewStateChangeEvent } from "@vis.gl/react-maplibre";
import type { StyleSpecification } from "maplibre-gl";
import { useQuery } from "react-query";
import { useMapStore } from "../store/mapStore";
import {
  fetchParkRide,
  fetchBicycleCounters,
  fetchRestrictions,
  fetchChoropleth,
  fetchAdminBoundaries,
  fetchUnifiedFeatures,
} from "../api/map";
import { loadGothamStyle, datasetColor } from "../map/gothamStyle";
import LayerPanel from "./LayerPanel";
import Reticle from "./chrome/Reticle";

const LEIPZIG_CENTER: [number, number] = [12.3731, 51.3397];
// Kartengrenzen großzügig um das Stadtgebiet — verhindert Laden der Weltkarte
const LEIPZIG_BOUNDS: [[number, number], [number, number]] = [
  [11.85, 51.13],
  [12.90, 51.55],
];

interface PopupInfo {
  lng: number;
  lat: number;
  properties: Record<string, unknown>;
}

interface Bbox {
  xmin: number;
  ymin: number;
  xmax: number;
  ymax: number;
}

const INITIAL_BBOX: Bbox = { xmin: 12.15, ymin: 51.25, xmax: 12.60, ymax: 51.43 };

export default function MapView() {
  const mapRef = useRef<MapRef>(null);
  const [popup, setPopup] = useState<PopupInfo | null>(null);
  const [cursor, setCursor] = useState<{ lng: number; lat: number }>({
    lng: LEIPZIG_CENTER[0],
    lat: LEIPZIG_CENTER[1],
  });
  const [zoom, setZoom] = useState(11);
  const [bbox, setBbox] = useState<Bbox>(INITIAL_BBOX);
  const [mapStyle, setMapStyle] = useState<StyleSpecification | null>(null);
  const [styleError, setStyleError] = useState(false);
  const [booted, setBooted] = useState(false);
  const { activeLayers, choroplethMetric, selectedYear, spatialUnit, selectedDatasetIds } =
    useMapStore();

  useEffect(() => {
    loadGothamStyle()
      .then(setMapStyle)
      .catch(() => setStyleError(true));
  }, []);

  const { data: parkRide } = useQuery(
    "parkRide",
    fetchParkRide,
    { enabled: activeLayers.has("park_ride"), refetchInterval: 60_000 }
  );

  const { data: bicycle } = useQuery(
    ["bicycle", 14],
    () => fetchBicycleCounters(14),
    { enabled: activeLayers.has("bicycle"), refetchInterval: 300_000 }
  );

  const { data: restrictions } = useQuery(
    "restrictions",
    fetchRestrictions,
    { enabled: activeLayers.has("restrictions"), refetchInterval: 120_000 }
  );

  const { data: choropleth } = useQuery(
    ["choropleth", choroplethMetric, spatialUnit, selectedYear],
    () => fetchChoropleth(choroplethMetric, spatialUnit, selectedYear ?? undefined),
    { enabled: activeLayers.has("choropleth") && !!choroplethMetric }
  );

  const { data: boundaries } = useQuery(
    ["boundaries", spatialUnit],
    () => fetchAdminBoundaries(spatialUnit),
    { staleTime: 3_600_000 }
  );

  // Vereinheitlichte Datenebene — BBox auf ~100 m gerundet, damit kleine
  // Kartenbewegungen keinen Refetch auslösen
  const bboxKey = useMemo(
    () =>
      [bbox.xmin, bbox.ymin, bbox.xmax, bbox.ymax]
        .map((v) => v.toFixed(3))
        .join(","),
    [bbox]
  );
  const { data: unifiedFeatures, isFetching: featuresLoading } = useQuery(
    ["unifiedFeatures", bboxKey, [...selectedDatasetIds].sort().join("|")],
    () => fetchUnifiedFeatures(bbox, selectedDatasetIds),
    {
      enabled: activeLayers.has("geo_features") && selectedDatasetIds.length > 0,
      keepPreviousData: true,
      staleTime: 30_000,
    }
  );

  // Farbe je Datensatz als data-driven Expression
  const featureColor = useMemo(() => {
    if (selectedDatasetIds.length === 0) return "#53b9e8";
    const expr: unknown[] = ["match", ["get", "dataset_id"]];
    for (const id of selectedDatasetIds) expr.push(id, datasetColor(id));
    expr.push("#53b9e8");
    return expr as unknown as string;
  }, [selectedDatasetIds]);

  const handleClick = useCallback((e: MapLayerMouseEvent) => {
    const feature = e.features?.[0];
    if (!feature) return;
    setPopup({
      lng: e.lngLat.lng,
      lat: e.lngLat.lat,
      properties: feature.properties as Record<string, unknown>,
    });
  }, []);

  const handleMouseMove = useCallback((e: MapLayerMouseEvent) => {
    setCursor({ lng: e.lngLat.lng, lat: e.lngLat.lat });
    if (mapRef.current) {
      mapRef.current.getCanvas().style.cursor = e.features?.length ? "pointer" : "";
    }
  }, []);

  const handleMove = useCallback((e: ViewStateChangeEvent) => {
    setZoom(e.viewState.zoom);
  }, []);

  const handleMoveEnd = useCallback(() => {
    const b = mapRef.current?.getBounds();
    if (!b) return;
    setBbox({
      xmin: b.getWest(),
      ymin: b.getSouth(),
      xmax: b.getEast(),
      ymax: b.getNorth(),
    });
  }, []);

  // Choropleth colour scale (5 quantile breaks → 5 colours)
  const choroplethValues = choropleth?.features?.map((f: { properties: { metric_value: number } }) => f.properties.metric_value).filter(Boolean) ?? [];
  const maxVal = choroplethValues.length ? Math.max(...choroplethValues) : 1;

  return (
    <div className="relative h-full w-full bg-gotham-900">
      {mapStyle && (
        <Map
          ref={mapRef}
          initialViewState={{ longitude: LEIPZIG_CENTER[0], latitude: LEIPZIG_CENTER[1], zoom: 11 }}
          mapStyle={mapStyle}
          maxBounds={LEIPZIG_BOUNDS}
          minZoom={9.5}
          interactiveLayerIds={[
            "park-ride-circles",
            "bicycle-circles",
            "restrictions-fill",
            "choropleth-fill",
            "unified-circle",
            "unified-line",
            "unified-fill",
          ]}
          onClick={handleClick}
          onMouseMove={handleMouseMove}
          onMove={handleMove}
          onMoveEnd={handleMoveEnd}
          onLoad={() => setBooted(true)}
        >
          {/* Admin boundary outlines */}
          {boundaries && (
            <Source id="boundaries" type="geojson" data={boundaries}>
              <Layer
                id="boundaries-line"
                type="line"
                paint={{ "line-color": "#2b4253", "line-width": 0.8, "line-opacity": 0.8 }}
              />
            </Source>
          )}

          {/* Choropleth */}
          {activeLayers.has("choropleth") && choropleth && (
            <Source id="choropleth" type="geojson" data={choropleth}>
              <Layer
                id="choropleth-fill"
                type="fill"
                paint={{
                  "fill-color": [
                    "interpolate", ["linear"],
                    ["get", "metric_value"],
                    0, "#0e2733",
                    maxVal * 0.25, "#14506b",
                    maxVal * 0.5, "#1f7ea6",
                    maxVal * 0.75, "#53b9e8",
                    maxVal, "#c9ecff",
                  ],
                  "fill-opacity": 0.65,
                }}
              />
              <Layer
                id="choropleth-line"
                type="line"
                paint={{ "line-color": "#53b9e8", "line-width": 0.4, "line-opacity": 0.5 }}
              />
            </Source>
          )}

          {/* Vereinheitlichte Datenebene */}
          {activeLayers.has("geo_features") && unifiedFeatures && (
            <Source id="unified" type="geojson" data={unifiedFeatures}>
              <Layer
                id="unified-fill"
                type="fill"
                filter={["any",
                  ["==", ["geometry-type"], "Polygon"],
                  ["==", ["geometry-type"], "MultiPolygon"],
                ]}
                paint={{ "fill-color": featureColor, "fill-opacity": 0.18 }}
              />
              <Layer
                id="unified-fill-line"
                type="line"
                filter={["any",
                  ["==", ["geometry-type"], "Polygon"],
                  ["==", ["geometry-type"], "MultiPolygon"],
                ]}
                paint={{ "line-color": featureColor, "line-width": 1, "line-opacity": 0.8 }}
              />
              <Layer
                id="unified-line"
                type="line"
                filter={["any",
                  ["==", ["geometry-type"], "LineString"],
                  ["==", ["geometry-type"], "MultiLineString"],
                ]}
                paint={{ "line-color": featureColor, "line-width": 1.5, "line-opacity": 0.85 }}
              />
              <Layer
                id="unified-circle"
                type="circle"
                filter={["any",
                  ["==", ["geometry-type"], "Point"],
                  ["==", ["geometry-type"], "MultiPoint"],
                ]}
                paint={{
                  "circle-radius": ["interpolate", ["linear"], ["zoom"], 10, 2, 14, 4.5, 17, 7],
                  "circle-color": featureColor,
                  "circle-opacity": 0.85,
                  "circle-stroke-width": 0.8,
                  "circle-stroke-color": "#0a1015",
                }}
              />
            </Source>
          )}

          {/* Traffic restrictions */}
          {activeLayers.has("restrictions") && restrictions && (
            <Source id="restrictions" type="geojson" data={restrictions}>
              <Layer
                id="restrictions-fill"
                type="fill"
                filter={["==", ["geometry-type"], "Polygon"]}
                paint={{ "fill-color": "#ffb02e", "fill-opacity": 0.25 }}
              />
              <Layer
                id="restrictions-line"
                type="line"
                paint={{ "line-color": "#ffb02e", "line-width": 1.5, "line-opacity": 0.8 }}
              />
              <Layer
                id="restrictions-circle"
                type="circle"
                filter={["==", ["geometry-type"], "Point"]}
                paint={{
                  "circle-radius": 5,
                  "circle-color": "#ffb02e",
                  "circle-opacity": 0.9,
                  "circle-stroke-width": 1.5,
                  "circle-stroke-color": "#0a1015",
                }}
              />
            </Source>
          )}

          {/* Park + Ride */}
          {activeLayers.has("park_ride") && parkRide && (
            <Source id="park-ride" type="geojson" data={parkRide}>
              <Layer
                id="park-ride-circles"
                type="circle"
                paint={{
                  "circle-radius": ["interpolate", ["linear"], ["get", "occupancy_pct"], 0, 8, 100, 18],
                  "circle-color": [
                    "interpolate", ["linear"], ["get", "occupancy_pct"],
                    0, "#3dd68c", 60, "#ffb02e", 90, "#ff6e5e",
                  ],
                  "circle-stroke-width": 1.5,
                  "circle-stroke-color": "#0a1015",
                  "circle-opacity": 0.9,
                }}
              />
            </Source>
          )}

          {/* Bicycle counters */}
          {activeLayers.has("bicycle") && bicycle && (
            <Source id="bicycle" type="geojson" data={bicycle}>
              <Layer
                id="bicycle-circles"
                type="circle"
                paint={{
                  "circle-radius": 7,
                  "circle-color": "#9adcff",
                  "circle-stroke-width": 1.5,
                  "circle-stroke-color": "#0a1015",
                }}
              />
            </Source>
          )}

          {/* Popup */}
          {popup && (
            <Popup
              longitude={popup.lng}
              latitude={popup.lat}
              closeButton
              onClose={() => setPopup(null)}
              maxWidth="300px"
            >
              <PopupContent properties={popup.properties} />
            </Popup>
          )}
        </Map>
      )}

      {/* Boot-Overlay bis Karte und Style geladen sind */}
      {!booted && (
        <div className="absolute inset-0 z-30 flex flex-col items-center justify-center bg-gotham-900">
          <Reticle className="h-12 w-12 text-signal-cyan" />
          <p className="hud-label mt-5 text-signal-cyan">
            {styleError ? "Basemap nicht erreichbar" : "Initialisiere Lagebild …"}
          </p>
          {styleError && (
            <button
              onClick={() => {
                setStyleError(false);
                loadGothamStyle().then(setMapStyle).catch(() => setStyleError(true));
              }}
              className="btn-ghost mt-4"
            >
              ▸ Erneut versuchen
            </button>
          )}
        </div>
      )}

      {/* HUD frame — corner brackets over the viewport */}
      <div className="corners pointer-events-none absolute inset-3 z-10 opacity-50" style={{ "--bracket-size": "18px" } as React.CSSProperties} />

      {/* Layer control panel */}
      <LayerPanel />

      {/* Coordinate readout */}
      <div className="pointer-events-none absolute bottom-5 left-5 z-10 flex items-center gap-4 border border-gotham-700 bg-gotham-900/85 px-3 py-1.5 font-mono text-[10px] tracking-wider text-gotham-300 backdrop-blur-sm">
        <span>
          <span className="text-gotham-500">LON&nbsp;</span>
          {cursor.lng.toFixed(5)}
        </span>
        <span>
          <span className="text-gotham-500">LAT&nbsp;</span>
          {cursor.lat.toFixed(5)}
        </span>
        <span>
          <span className="text-gotham-500">Z&nbsp;</span>
          {zoom.toFixed(1)}
        </span>
        {featuresLoading ? (
          <span className="flex items-center gap-1.5 text-signal-amber">
            <span className="led animate-led bg-signal-amber" />
            Lade Ebene
          </span>
        ) : (
          <span className="flex items-center gap-1.5 text-signal-green">
            <span className="led animate-led bg-signal-green" />
            Live
          </span>
        )}
        {activeLayers.has("geo_features") && unifiedFeatures && (
          <span>
            <span className="text-gotham-500">OBJ&nbsp;</span>
            {unifiedFeatures.features?.length?.toLocaleString() ?? 0}
            {unifiedFeatures.features?.length >= 5000 && (
              <span className="text-signal-amber"> (Limit)</span>
            )}
          </span>
        )}
      </div>
    </div>
  );
}

function PopupContent({ properties }: { properties: Record<string, unknown> }) {
  const skip = new Set(["geometry"]);
  const entries = Object.entries(properties).filter(([k]) => !skip.has(k));
  return (
    <div>
      <div className="flex items-center gap-2 border-b border-gotham-700 px-3 py-2">
        <span className="led animate-led bg-signal-cyan" />
        <span className="hud-label text-signal-cyan">Objektdaten</span>
      </div>
      <div className="max-h-48 space-y-1 overflow-y-auto px-3 py-2 font-mono text-[11px]">
        {entries.map(([k, v]) => (
          <div key={k} className="flex gap-2">
            <span className="shrink-0 text-gotham-500">{k}</span>
            <span className="break-all text-gotham-200">{String(v ?? "–")}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
