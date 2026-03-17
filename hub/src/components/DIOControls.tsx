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
  X
} from "lucide-react";
import { useState, useEffect, useMemo } from "react";

export const DIOControls = () => {
  const { 
    dbCredentials, 
    availableLayers, 
    setAvailableLayers, 
    selectedLayer, 
    setSelectedLayer,
    setSelectedGeoJson
  } = useStore();
  
  const [loading, setLoading] = useState(false);
  const [loadingGeoJson, setLoadingGeoJson] = useState(false);
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
        body: JSON.stringify(dbCredentials)
      });
      const data = await response.json();
      if (data.success) {
        setAvailableLayers(data.layers);
      } else {
        setError(data.error);
      }
    } catch (err) {
      setError("Failed to fetch database layers");
    } finally {
      setLoading(false);
    }
  };

  const fetchGeoJSON = async (layerId: string) => {
    if (!dbCredentials) return;
    setLoadingGeoJson(true);
    setSelectedGeoJson(null);
    try {
      const response = await fetch("/api/get-geojson", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...dbCredentials,
          table: layerId
        })
      });
      const data = await response.json();
      if (data.success) {
        setSelectedGeoJson(data.data);
      } else {
        console.error("GeoJSON Error:", data.error);
      }
    } catch (err) {
      console.error("Failed to fetch GeoJSON");
    } finally {
      setLoadingGeoJson(false);
    }
  };

  useEffect(() => {
    if (availableLayers.length === 0 && dbCredentials) {
      fetchLayers();
    }
  }, []);

  const handleLayerSelect = (layerId: string) => {
    if (selectedLayer === layerId) {
      setSelectedLayer(null);
      setSelectedGeoJson(null);
    } else {
      setSelectedLayer(layerId);
      fetchGeoJSON(layerId);
    }
  };

  const filteredLayers = useMemo(() => {
    if (!searchQuery) return availableLayers;
    const query = searchQuery.toLowerCase();
    return availableLayers.filter(layer => 
      layer.name.toLowerCase().includes(query) || 
      layer.schema.toLowerCase().includes(query)
    );
  }, [availableLayers, searchQuery]);

  return (
    <div className="absolute top-8 left-8 z-[1000] w-80 pointer-events-auto">
      <div className="bg-white/95 backdrop-blur shadow-xl border border-border rounded-sm overflow-hidden">
        <div className="bg-navy-dark px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Database size={14} className="text-teal" />
            <h4 className="text-[10px] font-bold uppercase tracking-wider text-white">PostGIS Layer Browser</h4>
          </div>
          <button 
            onClick={fetchLayers}
            disabled={loading}
            className="text-teal hover:text-teal-light transition-colors"
          >
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
        
        <div className="p-4">
          <div className="relative mb-4">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={14} />
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
                <X size={12} />
              </button>
            )}
          </div>

          <div className="max-h-60 overflow-y-auto space-y-1 pr-1 custom-scrollbar">
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
                <span className="text-[10px] text-slate-400 font-medium italic">
                  {availableLayers.length === 0 ? "No spatial tables found" : "No matches found"}
                </span>
              </div>
            ) : (
              filteredLayers.map((layer) => (
                <button
                  key={layer.id}
                  onClick={() => handleLayerSelect(layer.id)}
                  disabled={loadingGeoJson && selectedLayer !== layer.id}
                  className={`w-full text-left px-3 py-2.5 rounded-sm transition-all flex items-center justify-between group ${
                    selectedLayer === layer.id ? 'bg-teal/10 border-teal/20 border' : 'hover:bg-slate-50 border border-transparent'
                  }`}
                >
                  <div className="overflow-hidden">
                    <div className={`text-[11px] font-bold truncate ${selectedLayer === layer.id ? 'text-teal' : 'text-navy-dark'}`}>
                      {layer.name}
                    </div>
                    <div className="text-[9px] text-slate-400 uppercase tracking-tighter">
                      {layer.schema} • {layer.type}
                    </div>
                  </div>
                  {selectedLayer === layer.id ? (
                    loadingGeoJson ? <Loader2 size={14} className="animate-spin text-teal" /> : <Check size={14} className="text-teal shrink-0" />
                  ) : (
                    <ChevronRight size={14} className="text-slate-300 opacity-0 group-hover:opacity-100 transition-opacity shrink-0" />
                  )}
                </button>
              ))
            )}
          </div>
        </div>

        {selectedLayer && (
          <div className="bg-slate-50 border-t border-border p-4">
            <div className="flex items-center gap-2 mb-2">
              <Activity size={12} className="text-teal" />
              <span className="text-[9px] font-bold text-navy-dark uppercase tracking-widest">Active Layer Telemetry</span>
            </div>
            <div className="grid grid-cols-2 gap-2 text-[10px]">
              <div className="bg-white border border-border p-2">
                <div className="text-slate-400 uppercase text-[8px] mb-1">Status</div>
                <div className="font-bold text-teal">{loadingGeoJson ? "LOADING..." : "SYNCED"}</div>
              </div>
              <div className="bg-white border border-border p-2">
                <div className="text-slate-400 uppercase text-[8px] mb-1">Features</div>
                <div className="font-bold">Loaded</div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
