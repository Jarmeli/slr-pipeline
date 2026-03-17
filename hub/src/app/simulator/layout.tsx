"use client";

import { useStore } from "@/store/useStore";
import { 
  BarChart3, 
  Database, 
  Layers, 
  MessageSquare, 
  Settings, 
  LogOut,
  ChevronLeft,
  ChevronRight,
  Menu,
  ShieldAlert
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

export default function SimulatorLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { activeAgent, setActiveAgent, verified } = useStore();
  const router = useRouter();
  const pathname = usePathname();

  // Redirect to Home if not verified or if trying to access simulator directly
  useEffect(() => {
    if (!verified && pathname.startsWith("/simulator")) {
      router.push("/");
    }
  }, [verified, pathname, router]);

  const navItems = [
    { id: "DIO", label: "Data Operator", icon: Database, color: "text-teal" },
    { id: "MEL", label: "Model Evaluator", icon: BarChart3, color: "text-teal" },
    { id: "SIMO", label: "Impact Modeler", icon: Layers, color: "text-teal" },
  ];

  if (!verified) return null;

  return (
    <div className="flex h-screen bg-navy-dark overflow-hidden font-inter">
      {/* Minimalist Sidebar */}
      <aside className="w-20 border-r border-navy-light flex flex-col items-center py-8 gap-10 shrink-0">
        <Link href="/" className="p-3 bg-teal/10 rounded-sm group transition-all hover:bg-teal/20">
          <Settings size={20} className="text-teal group-hover:rotate-45 transition-transform" />
        </Link>
        
        <div className="flex-1 flex flex-col gap-6">
          {navItems.map((item) => (
            <button
              key={item.id}
              onClick={() => setActiveAgent(item.id as any)}
              className={`p-4 rounded-sm transition-all relative group ${
                activeAgent === item.id ? 'bg-navy-light' : 'hover:bg-navy-light/50'
              }`}
            >
              <item.icon 
                size={22} 
                className={activeAgent === item.id ? 'text-teal' : 'text-slate-400 group-hover:text-slate-200'} 
              />
              {/* Tooltip */}
              <div className="absolute left-full ml-4 px-3 py-1 bg-white text-navy-dark text-[10px] font-bold uppercase tracking-widest whitespace-nowrap opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity rounded-sm shadow-xl z-50">
                {item.label}
              </div>
              {activeAgent === item.id && (
                <motion.div 
                  layoutId="active-nav"
                  className="absolute left-0 top-0 bottom-0 w-1 bg-teal" 
                />
              )}
            </button>
          ))}
        </div>

        <button 
          onClick={() => router.push("/")}
          className="p-4 text-slate-500 hover:text-red-400 transition-colors"
        >
          <LogOut size={22} />
        </button>
      </aside>

      {/* Main Container: Split-Screen Layout */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Panel: Conversational Orchestrator */}
        <div className="w-[450px] border-r border-navy-light flex flex-col bg-navy-dark shrink-0">
          <div className="h-16 border-b border-navy-light flex items-center px-6 gap-3">
            <MessageSquare size={18} className="text-teal" />
            <h2 className="text-xs font-bold uppercase tracking-[0.2em] text-white">Conversational Orchestrator</h2>
          </div>
          
          <div className="flex-1 overflow-y-auto p-6 space-y-6">
            <div className="bg-navy-light/40 p-5 rounded-sm border border-navy-light">
              <p className="text-sm text-slate-300 leading-relaxed font-light">
                Secure link established with the SLR MCP agents. System telemetry is initialized.
              </p>
              <div className="mt-4 flex items-center gap-2 text-[10px] font-bold text-teal uppercase tracking-widest">
                <ShieldAlert size={12} />
                Protocol: Active Surveillance
              </div>
            </div>
          </div>

          <div className="p-6 border-t border-navy-light">
            <div className="relative">
              <input 
                type="text" 
                placeholder="PROMPT AGENT..."
                className="w-full bg-navy-light/30 border border-navy-light px-4 py-4 rounded-sm text-white focus:outline-none focus:border-teal/50 text-sm tracking-wide placeholder:text-slate-500 uppercase font-medium"
              />
            </div>
            <p className="text-[9px] text-slate-500 mt-3 font-bold uppercase tracking-widest text-center">
              Targeted Multi-Agent Coordination Layer
            </p>
          </div>
        </div>

        {/* Right Panel: Dynamic Canvas (The Active Agent View) */}
        <main className="flex-1 bg-slate-100 relative">
          {children}
        </main>
      </div>
    </div>
  );
}
