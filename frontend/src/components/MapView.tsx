import { useRef, useCallback, useState } from "react";
import { Map, Source, Layer, Popup } from "@vis.gl/react-maplibre";
import type { MapRef, MapLayerMouseEvent } from "@vis.gl/react-maplibre";
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

  // Choropleth colour scale (5 quantile breaks → 5 colours)
  const choroplethValues = choropleth?.features?.map((f: { properties: { metric_value: number } }) => f.properties.metric_value).filter(Boolean) ?? [];
  const maxVal = choroplethValues.length ? Math.max(...choroplethValues) : 1;

  return (
    <div className="relative w-full h-full">
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
        onMouseEnter={() => { if (mapRef.current) mapRef.current.getCanvas().style.cursor = "pointer"; }}
        onMouseLeave={() => { if (mapRef.current) mapRef.current.getCanvas().style.cursor = ""; }}
      >
        {/* Admin boundary outlines */}
        {boundaries && (
          <Source id="boundaries" type="geojson" data={boundaries}>
            <Layer
              id="boundaries-line"
              type="line"
              paint={{ "line-color": "#475569", "line-width": 0.8, "line-opacity": 0.7 }}
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
                  0, "#1e3a5f",
                  maxVal * 0.25, "#1d4ed8",
                  maxVal * 0.5, "#3b82f6",
                  maxVal * 0.75, "#93c5fd",
                  maxVal, "#dbeafe",
                ],
                "fill-opacity": 0.7,
              }}
            />
            <Layer
              id="choropleth-line"
              type="line"
              paint={{ "line-color": "#94a3b8", "line-width": 0.5 }}
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
              paint={{ "fill-color": "#f97316", "fill-opacity": 0.4 }}
            />
            <Layer
              id="restrictions-line"
              type="line"
              paint={{ "line-color": "#f97316", "line-width": 2, "line-opacity": 0.8 }}
            />
            <Layer
              id="restrictions-circle"
              type="circle"
              filter={["==", ["geometry-type"], "Point"]}
              paint={{ "circle-radius": 6, "circle-color": "#f97316", "circle-opacity": 0.9 }}
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
                  0, "#22c55e", 60, "#eab308", 90, "#ef4444",
                ],
                "circle-stroke-width": 2,
                "circle-stroke-color": "#fff",
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
                "circle-radius": 8,
                "circle-color": "#a78bfa",
                "circle-stroke-width": 2,
                "circle-stroke-color": "#fff",
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

      {/* Layer control panel */}
      <LayerPanel />
    </div>
  );
}

function PopupContent({ properties }: { properties: Record<string, unknown> }) {
  const skip = new Set(["geometry"]);
  const entries = Object.entries(properties).filter(([k]) => !skip.has(k));
  return (
    <div className="text-xs space-y-1 max-h-48 overflow-y-auto">
      {entries.map(([k, v]) => (
        <div key={k} className="flex gap-2">
          <span className="text-slate-400 shrink-0">{k}:</span>
          <span className="text-slate-200 break-all">{String(v ?? "–")}</span>
        </div>
      ))}
    </div>
  );
}
