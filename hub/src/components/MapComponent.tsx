"use client";

import { MapContainer, TileLayer, useMap, ZoomControl, GeoJSON } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import L from "leaflet";
import { useEffect } from "react";
import { useStore } from "@/store/useStore";

// Fix for default Leaflet icon not appearing
const DefaultIcon = L.icon({
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
  iconSize: [25, 41],
  iconAnchor: [12, 41],
});
L.Marker.prototype.options.icon = DefaultIcon;

// Child component to handle map side-effects like zooming to bounds
function MapResizer({ geoJson }: { geoJson: any }) {
  const map = useMap();
  
  useEffect(() => {
    if (geoJson) {
      const geoJsonLayer = L.geoJSON(geoJson);
      const bounds = geoJsonLayer.getBounds();
      if (bounds.isValid()) {
        map.fitBounds(bounds, { padding: [50, 50] });
      }
    }
  }, [geoJson, map]);

  return null;
}

interface MapComponentProps {
  center?: [number, number];
  zoom?: number;
}

export default function MapComponent({ 
  center = [26.0, -81.7], // Rookery Bay area
  zoom = 10 
}: MapComponentProps) {
  const { selectedGeoJson } = useStore();

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
        
        {selectedGeoJson && (
          <GeoJSON 
            key={JSON.stringify(selectedGeoJson.features?.[0]?.id || 'layer')}
            data={selectedGeoJson} 
            style={{
              color: "#20B2AA",
              weight: 2,
              opacity: 0.8,
              fillColor: "#20B2AA",
              fillOpacity: 0.2
            }}
          />
        )}
        
        <MapResizer geoJson={selectedGeoJson} />
        <ZoomControl position="bottomright" />
      </MapContainer>
    </div>
  );
}
