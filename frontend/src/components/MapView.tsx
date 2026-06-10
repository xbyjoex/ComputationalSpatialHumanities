import { useRef, useCallback, useState } from "react";
import { Map, Source, Layer, Popup } from "@vis.gl/react-maplibre";
import type { MapRef, MapLayerMouseEvent } from "@vis.gl/react-maplibre";
import type { ViewStateChangeEvent } from "@vis.gl/react-maplibre";
import { useQuery } from "react-query";
import { useMapStore } from "../store/mapStore";
import {
  fetchParkRide,
  fetchBicycleCounters,
  fetchRestrictions,
  fetchChoropleth,
  fetchAdminBoundaries,
} from "../api/map";
import LayerPanel from "./LayerPanel";

const LEIPZIG_CENTER: [number, number] = [12.3731, 51.3397];

interface PopupInfo {
  lng: number;
  lat: number;
  properties: Record<string, unknown>;
}

export default function MapView() {
  const mapRef = useRef<MapRef>(null);
  const [popup, setPopup] = useState<PopupInfo | null>(null);
  const [cursor, setCursor] = useState<{ lng: number; lat: number }>({
    lng: LEIPZIG_CENTER[0],
    lat: LEIPZIG_CENTER[1],
  });
  const [zoom, setZoom] = useState(11);
  const { activeLayers, choroplethMetric, selectedYear, spatialUnit } = useMapStore();

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

  // Choropleth colour scale (5 quantile breaks → 5 colours)
  const choroplethValues = choropleth?.features?.map((f: { properties: { metric_value: number } }) => f.properties.metric_value).filter(Boolean) ?? [];
  const maxVal = choroplethValues.length ? Math.max(...choroplethValues) : 1;

  return (
    <div className="relative h-full w-full">
      <Map
        ref={mapRef}
        initialViewState={{ longitude: LEIPZIG_CENTER[0], latitude: LEIPZIG_CENTER[1], zoom: 11 }}
        mapStyle="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json"
        interactiveLayerIds={[
          "park-ride-circles",
          "bicycle-circles",
          "restrictions-fill",
          "choropleth-fill",
        ]}
        onClick={handleClick}
        onMouseMove={handleMouseMove}
        onMove={handleMove}
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
        <span className="flex items-center gap-1.5 text-signal-green">
          <span className="led animate-led bg-signal-green" />
          Live
        </span>
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
