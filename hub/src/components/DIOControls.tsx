"use client";

import { useStore } from "@/store/useStore";
import {
  Database,
  RefreshCw,
  Search,
  Check,
  ChevronRight,
  Loader2,
  Activity,
  X,
  Layers,
  Square,
  Trash2
} from "lucide-react";
import { useState, useEffect, useMemo } from "react";

// Color palette for multi-layer visualization
const LAYER_COLORS = [
  "#20B2AA", // teal
  "#E86F52", // coral
  "#5B8AF5", // blue
  "#F5C542", // gold
  "#A78BFA", // violet
  "#34D399", // emerald
];

export const DIOControls = () => {
  const {
    dbCredentials,
    availableLayers,
    setAvailableLayers,
    selectedLayers,
    toggleLayer,
    setLayerGeoJson,
    clearLayers,
    clipBounds,
  } = useStore();

  const [loading, setLoading] = useState(false);
  const [loadingLayers, setLoadingLayers] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");

  const fetchLayers = async () => {
    if (!dbCredentials) return;
    setLoading(true);
    setError(null);
    try {
      const response = await fetch("/api/get-layers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(dbCredentials),
      });
      const data = await response.json();
      if (data.success) {
        setAvailableLayers(data.layers);
      } else {
        setError(data.error);
      }
    } catch {
      setError("Failed to fetch database layers");
    } finally {
      setLoading(false);
    }
  };

  const fetchGeoJSON = async (layerId: string) => {
    if (!dbCredentials) return;
    setLoadingLayers((prev) => new Set(prev).add(layerId));
    try {
      const response = await fetch("/api/get-geojson", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...dbCredentials,
          table: layerId,
          ...(clipBounds
            ? {
                bounds: {
                  south: clipBounds[0][0],
                  west: clipBounds[0][1],
                  north: clipBounds[1][0],
                  east: clipBounds[1][1],
                },
              }
            : {}),
        }),
      });
      const data = await response.json();
      if (data.success) {
        setLayerGeoJson(layerId, data.data);
      }
    } catch {
      console.error("Failed to fetch GeoJSON for", layerId);
    } finally {
      setLoadingLayers((prev) => {
        const next = new Set(prev);
        next.delete(layerId);
        return next;
      });
    }
  };

  const handleToggle = (layerId: string) => {
    const isSelected = selectedLayers.includes(layerId);
    toggleLayer(layerId);
    if (!isSelected) {
      // Just selected — fetch GeoJSON
      fetchGeoJSON(layerId);
    }
  };

  useEffect(() => {
    if (availableLayers.length === 0 && dbCredentials) {
      fetchLayers();
    }
  }, []);

  const filteredLayers = useMemo(() => {
    if (!searchQuery) return availableLayers;
    const q = searchQuery.toLowerCase();
    return availableLayers.filter(
      (l) => l.name.toLowerCase().includes(q) || l.schema.toLowerCase().includes(q)
    );
  }, [availableLayers, searchQuery]);

  return (
    <div className="absolute top-8 left-8 z-[1000] w-80 pointer-events-auto">
      <div className="bg-white/97 backdrop-blur shadow-2xl border border-border rounded-sm overflow-hidden">
        {/* Header */}
        <div className="bg-navy-dark px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Database size={14} className="text-teal" />
            <h4 className="text-[10px] font-bold uppercase tracking-wider text-white">PostGIS Layer Browser</h4>
          </div>
          <div className="flex items-center gap-3">
            {selectedLayers.length > 0 && (
              <button onClick={clearLayers} className="text-red-400 hover:text-red-300 transition-colors" title="Clear all layers">
                <Trash2 size={12} />
              </button>
            )}
            <button onClick={fetchLayers} disabled={loading} className="text-teal hover:text-white transition-colors">
              <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
            </button>
          </div>
        </div>

        {/* Active layer count badge */}
        {selectedLayers.length > 0 && (
          <div className="bg-teal/10 border-b border-teal/20 px-4 py-2 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Layers size={11} className="text-teal" />
              <span className="text-[9px] font-bold text-teal uppercase tracking-widest">
                {selectedLayers.length} Layer{selectedLayers.length > 1 ? "s" : ""} Active
              </span>
            </div>
            <div className="flex gap-1">
              {selectedLayers.map((id, i) => (
                <div
                  key={id}
                  className="w-3 h-3 rounded-full border border-white/50"
                  style={{ backgroundColor: LAYER_COLORS[i % LAYER_COLORS.length] }}
                  title={id}
                />
              ))}
            </div>
          </div>
        )}

        {/* Clip bounds indicator */}
        {clipBounds && (
          <div className="bg-amber-50 border-b border-amber-200 px-4 py-2">
            <span className="text-[9px] font-bold text-amber-700 uppercase tracking-widest">
              Clip Bounds Active — Layers clipped to drawn area
            </span>
          </div>
        )}

        <div className="p-4">
          {/* Search */}
          <div className="relative mb-3">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={13} />
            <input
              type="text"
              placeholder="Search tables..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-slate-50 border border-border pl-9 pr-8 py-2 text-xs rounded-sm focus:outline-none focus:border-teal/50"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery("")}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-navy-dark"
              >
                <X size={11} />
              </button>
            )}
          </div>

          {/* Layer list */}
          <div className="max-h-56 overflow-y-auto space-y-1 pr-1">
            {loading ? (
              <div className="py-8 flex flex-col items-center gap-2">
                <Loader2 className="animate-spin text-slate-300" size={20} />
                <span className="text-[9px] font-bold text-slate-400 uppercase tracking-widest">Scanning Schemas...</span>
              </div>
            ) : error ? (
              <div className="py-4 text-center">
                <span className="text-[10px] text-red-500 font-medium">{error}</span>
              </div>
            ) : filteredLayers.length === 0 ? (
              <div className="py-4 text-center">
                <span className="text-[10px] text-slate-400 italic">
                  {availableLayers.length === 0 ? "No spatial tables found" : "No matches"}
                </span>
              </div>
            ) : (
              filteredLayers.map((layer) => {
                const isSelected = selectedLayers.includes(layer.id);
                const colorIndex = selectedLayers.indexOf(layer.id);
                const color = isSelected ? LAYER_COLORS[colorIndex % LAYER_COLORS.length] : undefined;
                const isLoading = loadingLayers.has(layer.id);

                return (
                  <button
                    key={layer.id}
                    onClick={() => handleToggle(layer.id)}
                    className={`w-full text-left px-3 py-2.5 rounded-sm transition-all flex items-center gap-3 group ${
                      isSelected ? "bg-slate-50 border border-slate-200" : "hover:bg-slate-50 border border-transparent"
                    }`}
                  >
                    {/* Color dot / checkbox */}
                    <div
                      className={`w-3 h-3 rounded-sm shrink-0 border-2 transition-all ${
                        isSelected ? "border-transparent" : "border-slate-300 group-hover:border-slate-400"
                      }`}
                      style={isSelected ? { backgroundColor: color } : {}}
                    >
                      {isSelected && !isLoading && (
                        <Check size={9} className="text-white m-auto" strokeWidth={3} />
                      )}
                    </div>

                    <div className="overflow-hidden flex-1">
                      <div className={`text-[11px] font-bold truncate ${isSelected ? "text-navy-dark" : "text-slate-600"}`}>
                        {layer.name}
                      </div>
                      <div className="text-[9px] text-slate-400 uppercase tracking-tighter">
                        {layer.schema} • {layer.type}
                      </div>
                    </div>

                    {isLoading ? (
                      <Loader2 size={12} className="animate-spin text-teal shrink-0" />
                    ) : !isSelected ? (
                      <ChevronRight size={12} className="text-slate-300 opacity-0 group-hover:opacity-100 shrink-0" />
                    ) : null}
                  </button>
                );
              })
            )}
          </div>
        </div>

        {/* Telemetry footer */}
        {selectedLayers.length > 0 && (
          <div className="bg-slate-50 border-t border-border p-3">
            <div className="flex items-center gap-2 mb-2">
              <Activity size={11} className="text-teal" />
              <span className="text-[9px] font-bold text-navy-dark uppercase tracking-widest">Layer Telemetry</span>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div className="bg-white border border-border p-2">
                <div className="text-slate-400 uppercase text-[8px] mb-1">Status</div>
                <div className="font-bold text-[10px] text-teal">SYNCED</div>
              </div>
              <div className="bg-white border border-border p-2">
                <div className="text-slate-400 uppercase text-[8px] mb-1">Active</div>
                <div className="font-bold text-[10px]">{selectedLayers.length} layer{selectedLayers.length > 1 ? 's' : ''}</div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
