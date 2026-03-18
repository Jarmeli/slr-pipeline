"use client";

import { MapContainer, TileLayer, useMap, ZoomControl, GeoJSON, FeatureGroup } from "react-leaflet";
import { EditControl } from "react-leaflet-draw";
import "leaflet/dist/leaflet.css";
import "leaflet-draw/dist/leaflet.draw.css";
import L from "leaflet";
import { useEffect } from "react";
import { useStore } from "@/store/useStore";

// Fix default icon
const DefaultIcon = L.icon({
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
  iconSize: [25, 41],
  iconAnchor: [12, 41],
});
L.Marker.prototype.options.icon = DefaultIcon;

// Layer color palette (matches DIOControls)
const LAYER_COLORS = [
  "#20B2AA", "#E86F52", "#5B8AF5", "#F5C542", "#A78BFA", "#34D399",
];

// Handles auto-zoom to the first loaded layer's bounds
function BoundsController({ layerGeoJsonMap }: { layerGeoJsonMap: Record<string, any> }) {
  const map = useMap();

  useEffect(() => {
    const keys = Object.keys(layerGeoJsonMap);
    if (keys.length === 0) return;
    // Zoom to most recently added layer
    const latest = layerGeoJsonMap[keys[keys.length - 1]];
    if (!latest) return;
    try {
      const layer = L.geoJSON(latest);
      const bounds = layer.getBounds();
      if (bounds.isValid()) {
        map.fitBounds(bounds, { padding: [50, 50], maxZoom: 14 });
      }
    } catch {
      // ignore invalid geometries
    }
  }, [Object.keys(layerGeoJsonMap).length]); // eslint-disable-line

  return null;
}

interface MapComponentProps {
  center?: [number, number];
  zoom?: number;
  enableDraw?: boolean;
}

export default function MapComponent({
  center = [26.0, -81.7],
  zoom = 10,
  enableDraw = false,
}: MapComponentProps) {
  const { selectedLayers, layerGeoJsonMap, setClipBounds, clipBounds } = useStore();

  const handleDrawCreated = (e: any) => {
    const bounds = e.layer.getBounds();
    setClipBounds([
      [bounds.getSouth(), bounds.getWest()],
      [bounds.getNorth(), bounds.getEast()],
    ]);
  };

  const handleDrawDeleted = () => {
    setClipBounds(null);
  };

  return (
    <div className="w-full h-full relative">
      <MapContainer
        center={center}
        zoom={zoom}
        scrollWheelZoom={true}
        className="w-full h-full z-0"
        zoomControl={false}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        {/* Clipping draw control — only shown when enableDraw is true (DIO view) */}
        {enableDraw && (
          <FeatureGroup>
            <EditControl
              position="topright"
              onCreated={handleDrawCreated}
              onDeleted={handleDrawDeleted}
              draw={{
                rectangle: true,
                polygon: false,
                circle: false,
                polyline: false,
                circlemarker: false,
                marker: false,
              }}
              edit={{ edit: false }}
            />
          </FeatureGroup>
        )}

        {/* Render each selected layer with its unique color */}
        {selectedLayers.map((layerId, index) => {
          const geoJson = layerGeoJsonMap[layerId];
          if (!geoJson) return null;
          const color = LAYER_COLORS[index % LAYER_COLORS.length];
          return (
            <GeoJSON
              key={`${layerId}-${JSON.stringify(geoJson.features?.[0]?.id || index)}`}
              data={geoJson}
              style={{
                color,
                weight: 2,
                opacity: 0.85,
                fillColor: color,
                fillOpacity: 0.18,
              }}
            />
          );
        })}

        <BoundsController layerGeoJsonMap={layerGeoJsonMap} />
        <ZoomControl position="bottomright" />
      </MapContainer>
    </div>
  );
}
