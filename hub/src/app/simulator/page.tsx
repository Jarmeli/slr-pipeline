"use client";

import { useStore } from "@/store/useStore";
import { 
  Database, 
  BarChart3, 
  Layers, 
  Map as MapIcon, 
  Info,
  Maximize2,
  Minimize2,
  Activity,
  ArrowRightCircle,
  RefreshCw,
  Search,
  Check,
  ChevronRight,
  Loader2
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import dynamic from "next/dynamic";
import { useState, useEffect } from "react";

import { DIOControls } from "@/components/DIOControls";

// Dynamically import MapComponent to avoid SSR errors with Leaflet
const MapComponent = dynamic(() => import("@/components/MapComponent"), {
  ssr: false,
  loading: () => (
    <div className="w-full h-full bg-slate-100 flex items-center justify-center">
      <Loader2 className="animate-spin text-teal" size={32} />
    </div>
  )
});

const MetricsCanvas = () => (
  <div className="w-full h-full bg-white p-12 overflow-y-auto">
    <div className="max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-12">
        <div>
          <h2 className="text-2xl font-bold text-navy-dark tracking-tighter uppercase italic">Model Evaluation Analytics</h2>
          <p className="text-[11px] font-bold text-slate-400 uppercase tracking-widest mt-1">Cross-Validation Metrics & Feature Performance</p>
        </div>
        <div className="w-12 h-12 rounded-sm bg-teal/10 border border-teal/20 flex items-center justify-center">
          <BarChart3 className="text-teal" size={24} />
        </div>
      </div>

      <div className="grid grid-cols-3 gap-6 mb-12">
        {['R-Squared', 'RMSE', 'MAE'].map((metric, i) => (
          <div key={i} className="bg-slate-50 border border-border p-6 rounded-sm">
            <h4 className="text-[9px] font-bold uppercase tracking-[0.2em] text-slate-400 mb-2">{metric}</h4>
            <div className="flex items-baseline gap-2">
              <span className="text-3xl font-black text-navy-dark tracking-tighter">
                {i === 0 ? '0.942' : i === 1 ? '12.4k' : '8.1k'}
              </span>
              <span className="text-[10px] font-bold text-teal">+2.4%</span>
            </div>
          </div>
        ))}
      </div>

      <div className="h-80 bg-slate-50 border border-border flex items-center justify-center p-8">
        <div className="w-full h-full flex items-end gap-2 px-12">
           {[60, 80, 45, 90, 30, 70, 55].map((h, i) => (
             <motion.div 
               initial={{ height: 0 }}
               animate={{ height: `${h}%` }}
               transition={{ delay: i * 0.1 }}
               key={i} 
               className="flex-1 bg-teal/40 border-t-2 border-teal hover:bg-teal transition-colors rounded-t-sm" 
             />
           ))}
        </div>
      </div>
      <p className="text-center text-[9px] font-bold uppercase tracking-widest mt-6 text-slate-400">
        Global Feature Importance Ranking (XGBoost Ensemble)
      </p>
    </div>
  </div>
);

const EmptyCanvas = () => (
  <div className="w-full h-full flex flex-col items-center justify-center bg-slate-100 italic">
    <Activity size={32} className="text-slate-300 animate-pulse mb-6" />
    <span className="text-xs font-bold text-slate-400 uppercase tracking-[0.5em]">Select Core Agent to Initialize Interface</span>
  </div>
);

export default function SimulatorPage() {
  const { activeAgent } = useStore();

  return (
    <div className="w-full h-full relative">
      <AnimatePresence mode="wait">
        {!activeAgent && (
          <motion.div 
            key="empty"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="w-full h-full"
          >
            <EmptyCanvas />
          </motion.div>
        )}

        {activeAgent === "DIO" && (
          <motion.div 
            key="dio"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="w-full h-full relative"
          >
            <MapComponent enableDraw={true} />
            <DIOControls />
          </motion.div>
        )}

        {activeAgent === "MEL" && (
          <motion.div 
            key="mel"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="w-full h-full"
          >
            <MetricsCanvas />
          </motion.div>
        )}

        {activeAgent === "SIMO" && (
          <motion.div 
            key="simo"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="w-full h-full relative"
          >
            <MapComponent />
            
            {/* Depth Slider Overlay for SIMO */}
            <div className="absolute bottom-12 left-1/2 -translate-x-1/2 w-[500px] bg-white border border-border shadow-2xl p-8 z-[1000]">
              <div className="flex justify-between items-center mb-6">
                <h4 className="text-[10px] font-bold uppercase tracking-[0.2em] text-navy-dark">Sea Level Rise Scenario Selection</h4>
                <span className="px-3 py-1 bg-teal text-white text-[10px] font-black italic tracking-tighter uppercase">Simulation Active</span>
              </div>
              <input 
                type="range" 
                min="1" max="5" 
                className="w-full h-1 bg-slate-100 appearance-none cursor-pointer accent-teal border border-slate-200"
              />
              <div className="flex justify-between mt-4 text-[10px] font-bold text-slate-500 tracking-widest">
                <span>1 FT</span>
                <span>2 FT</span>
                <span>3 FT</span>
                <span>4 FT</span>
                <span>5 FT</span>
              </div>
            </div>

            {/* SIMO Stat Cards */}
            <div className="absolute top-8 right-8 space-y-4 z-[1000]">
              <div className="bg-navy-dark border border-navy-light p-6 w-64 shadow-2xl rounded-sm">
                <h4 className="text-[9px] font-bold uppercase tracking-[0.3em] text-teal mb-3">Total Estimated Damage</h4>
                <div className="text-2xl font-black text-white">$14.2B</div>
              </div>
              <div className="bg-navy-dark border border-navy-light p-6 w-64 shadow-2xl rounded-sm">
                <h4 className="text-[9px] font-bold uppercase tracking-[0.3em] text-teal mb-3">Mean Per Parcel</h4>
                <div className="text-2xl font-black text-white">$42.8K</div>
              </div>
              <div className="bg-navy-dark border border-navy-light p-6 w-64 shadow-2xl rounded-sm">
                <h4 className="text-[9px] font-bold uppercase tracking-[0.3em] text-teal mb-3">Critical Facilities</h4>
                <div className="text-2xl font-black text-white">12</div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
