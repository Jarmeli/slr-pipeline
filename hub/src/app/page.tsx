"use client";

import { useState, useCallback } from "react";
import { 
  Rocket, 
  Settings, 
  Activity, 
  CheckCircle, 
  XCircle,
  Database, 
  Layers,
  BarChart3,
  ChevronDown,
  Info,
  Server,
  Terminal,
  Cpu,
  ShieldCheck,
  Zap,
  Loader2
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { useStore } from "@/store/useStore";
import KnowledgeGraph from "@/components/KnowledgeGraph";
import { useRouter } from "next/navigation";

// Agent metadata
const agents = [
  {
    id: "DIO",
    name: "DIO (Data Operator)",
    role: "Specialist in data ingestion, cleaning, and schema management.",
    icon: Database,
    behaviors: [
      "Strict read-only access to raw source tables.",
      "Writes restricted to the 'clean_data' schema.",
      "Transforms must be logged for auditability."
    ],
    knowledge: [
      "PostgreSQL / PostGIS schema design",
      "Automated cleaning pipelines",
      "MVT generation"
    ]
  },
  {
    id: "MEL",
    name: "MEL (Model Evaluation)",
    role: "Analytical engine for model training and metric validation.",
    icon: BarChart3,
    behaviors: [
      "Ensemble training on historical claims.",
      "Evaluation using R², RMSE, and MAE.",
      "Export to versioned artifact store only."
    ],
    knowledge: [
      "Random Forest & XGBoost Ensembles",
      "Yeo-Johnson transformations",
      "GMM Distribution Modeling"
    ]
  },
  {
    id: "SIMO",
    name: "SIMO (Impact Modeler)",
    role: "Simulation specialist for parcel-level flood risk.",
    icon: Layers,
    behaviors: [
      "Applies MEL-trained models to parcel data.",
      "Scenario-based (1ft-5ft) damage calculation.",
      "Memory limited to verified results (ChromaDB)."
    ],
    knowledge: [
      "Flood exposure modeling",
      "RAG-based simulation memory",
      "Municipal risk aggregation"
    ]
  }
];

export default function Home() {
  const router = useRouter();
  const { dbCredentials, setDbCredentials, lmStudioIp, setLmStudioIp, verified, setVerified } = useStore();
  
  const [activeTab, setActiveTab] = useState("DIO");
  const [isTopographyExpanded, setIsTopographyExpanded] = useState(false);
  const [isVerifying, setIsVerifying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Form state
  const [formData, setFormData] = useState({
    host: dbCredentials?.host || "sea-level-rise.postgres.database.azure.com",
    port: dbCredentials?.port || "5432",
    user: dbCredentials?.user || "SLRuser",
    database: dbCredentials?.database || "SeaLevelRise",
    password: ""
  });

  const handleVerify = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsVerifying(true);
    setError(null);
    
    try {
      const response = await fetch("/api/verify-db", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(formData)
      });

      const data = await response.json();

      if (data.success) {
        setDbCredentials(formData);
        setVerified(true);
      } else {
        setError(data.error || "Connection failed");
        setVerified(false);
      }
    } catch (err) {
      setError("Network error during verification");
      setVerified(false);
    } finally {
      setIsVerifying(false);
    }
  };

  const launchSimulator = () => {
    if (verified) {
      router.push("/simulator");
    }
  };

  return (
    <div className="min-h-screen bg-white">
      {/* Header */}
      <header className="border-b border-border bg-slate-50/50">
        <div className="max-w-7xl mx-auto px-8 h-20 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="w-10 h-10 bg-navy-dark flex items-center justify-center rounded-sm">
              <Zap className="text-teal" size={24} />
            </div>
            <div>
              <h1 className="text-xl font-bold tracking-tight text-navy-dark uppercase">SLR Pipeline</h1>
              <p className="text-[10px] text-slate-500 font-bold tracking-[0.2em] uppercase">Control Plane v2.0</p>
            </div>
          </div>
          
          <div className="flex items-center gap-6">
            <div className={`flex items-center gap-3 px-4 py-2 rounded-sm border ${verified ? 'border-teal/20 bg-teal/5' : 'border-slate-200 bg-slate-50'}`}>
              <div className={`w-2 h-2 rounded-full ${verified ? 'bg-teal animate-pulse' : 'bg-slate-300'}`} />
              <span className={`text-[11px] font-bold tracking-widest uppercase ${verified ? 'text-teal' : 'text-slate-400'}`}>
                {verified ? 'System Verified' : 'Awaiting Config'}
              </span>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-8 py-12">
        {/* Phase 0: Prepper Wizard Section */}
        <section className="grid grid-cols-1 lg:grid-cols-3 gap-12 mb-16">
          <div className="lg:col-span-1">
            <div className="flex items-center gap-3 mb-6">
              <ShieldCheck className="text-teal" size={28} />
              <h2 className="text-2xl font-bold text-navy-dark tracking-tight">Phase 0: Prepper</h2>
            </div>
            <p className="text-slate-600 mb-8 leading-relaxed text-sm">
              The Prepper is a deterministic configuration wizard. Enter your environment credentials to unlock the AI-driven simulation workflows for DIO, MEL, and SIMO.
            </p>
            
            <div className="space-y-6">
              <div className="flex items-start gap-4">
                <div className="w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center shrink-0 text-navy-dark font-bold text-xs border border-border">01</div>
                <div>
                  <h4 className="text-xs font-bold uppercase tracking-wider text-navy-dark mb-1">Database Handshake</h4>
                  <p className="text-[11px] text-slate-500">Connect to the Azure PostGIS instance for geospatial operations.</p>
                </div>
              </div>
              <div className="flex items-start gap-4">
                <div className="w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center shrink-0 text-navy-dark font-bold text-xs border border-border">02</div>
                <div>
                  <h4 className="text-xs font-bold uppercase tracking-wider text-navy-dark mb-1">Inference Config</h4>
                  <p className="text-[11px] text-slate-500">Define the LM Studio endpoint for model orchestration.</p>
                </div>
              </div>
            </div>
          </div>

          <div className="lg:col-span-2">
            <div className="card">
              <h3 className="label-text mb-6">Environment Configuration</h3>
              <form onSubmit={handleVerify} className="space-y-6">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div className="space-y-2">
                    <label className="label-text">Database Host</label>
                    <input 
                      type="text" 
                      className="input-field" 
                      value={formData.host}
                      onChange={(e) => setFormData({...formData, host: e.target.value})}
                    />
                  </div>
                  <div className="space-y-2">
                    <label className="label-text">Port</label>
                    <input 
                      type="text" 
                      className="input-field" 
                      value={formData.port}
                      onChange={(e) => setFormData({...formData, port: e.target.value})}
                    />
                  </div>
                </div>
                
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div className="space-y-2">
                    <label className="label-text">User</label>
                    <input 
                      type="text" 
                      className="input-field" 
                      value={formData.user}
                      onChange={(e) => setFormData({...formData, user: e.target.value})}
                    />
                  </div>
                  <div className="space-y-2">
                    <label className="label-text">Database Name</label>
                    <input 
                      type="text" 
                      className="input-field" 
                      value={formData.database}
                      onChange={(e) => setFormData({...formData, database: e.target.value})}
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div className="space-y-2">
                    <label className="label-text">Password</label>
                    <input 
                      type="password" 
                      className="input-field" 
                      placeholder="••••••••"
                      value={formData.password}
                      onChange={(e) => setFormData({...formData, password: e.target.value})}
                    />
                  </div>
                  <div className="space-y-2">
                    <label className="label-text">LM Studio Endpoint</label>
                    <input 
                      type="text" 
                      className="input-field" 
                      value={lmStudioIp}
                      onChange={(e) => setLmStudioIp(e.target.value)}
                    />
                  </div>
                </div>

                <div className="pt-4 flex items-center justify-between">
                  <button 
                    disabled={isVerifying}
                    className="btn-primary"
                  >
                    {isVerifying && <Loader2 size={16} className="animate-spin" />}
                    {isVerifying ? "Verifying Handshake..." : "Verify Connection"}
                  </button>
                  
                  {verified && !error && (
                    <motion.div 
                      initial={{ opacity: 0, x: 20 }}
                      animate={{ opacity: 1, x: 0 }}
                      className="flex items-center gap-2 text-teal font-bold text-[11px] uppercase tracking-widest"
                    >
                      <CheckCircle size={16} />
                      Connection Established
                    </motion.div>
                  )}

                  {error && (
                    <motion.div 
                      initial={{ opacity: 0, x: 20 }}
                      animate={{ opacity: 1, x: 0 }}
                      className="flex items-center gap-2 text-red-500 font-bold text-[11px] uppercase tracking-widest"
                    >
                      <XCircle size={16} />
                      {error}
                    </motion.div>
                  )}
                </div>
              </form>
            </div>
          </div>
        </section>

        {/* System Architecture Tabs */}
        <section className={`transition-all duration-700 ${verified ? 'opacity-100' : 'opacity-40 grayscale pointer-events-none'}`}>
          <div className="mb-8">
            <h2 className="text-lg font-bold text-navy-dark tracking-tight uppercase flex items-center gap-3">
              <Server className="text-teal" size={20} />
              Agent Core Profiles
            </h2>
          </div>

          <div className="flex items-center mb-8 border-b border-border">
            {agents.map((agent) => (
              <div
                key={agent.id}
                onClick={() => setActiveTab(agent.id)}
                className={activeTab === agent.id ? "tab-active" : "tab-inactive"}
              >
                <agent.icon size={18} />
                {agent.name}
              </div>
            ))}
          </div>

          <AnimatePresence mode="wait">
            <motion.div
              key={activeTab}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.2 }}
              className="grid grid-cols-1 lg:grid-cols-2 gap-8"
            >
              <div className="card card-hover">
                <div className="flex items-center gap-4 mb-6">
                  {(() => {
                    const agent = agents.find(a => a.id === activeTab)!;
                    return <agent.icon size={32} className="text-teal" />;
                  })()}
                  <h3 className="text-xl font-bold text-navy-dark">{agents.find(a => a.id === activeTab)?.name}</h3>
                </div>
                <p className="text-sm text-slate-600 leading-relaxed mb-6 italic">
                  "{agents.find(a => a.id === activeTab)?.role}"
                </p>
                <div className="pt-6 border-t border-border">
                  <h4 className="label-text mb-4">Core Behaviors</h4>
                  <ul className="space-y-3">
                    {agents.find(a => a.id === activeTab)?.behaviors.map((b, i) => (
                      <li key={i} className="flex items-start gap-3 text-xs text-slate-600">
                        <div className="w-1.5 h-1.5 rounded-full bg-teal mt-1.5 shrink-0" />
                        {b}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>

              <div className="card card-hover">
                <h4 className="label-text mb-6">Domain Knowledge Base</h4>
                <div className="space-y-6">
                  {agents.find(a => a.id === activeTab)?.knowledge.map((k, i) => (
                    <div key={i} className="flex items-center justify-between p-4 bg-slate-50 border border-slate-100">
                      <span className="text-sm font-semibold text-navy-dark">{k}</span>
                      <Activity size={16} className="text-teal/30" />
                    </div>
                  ))}
                </div>
              </div>
            </motion.div>
          </AnimatePresence>
        </section>

        {/* Launcher */}
        <div className="mt-16 text-center">
          <motion.button
            whileHover={verified ? { scale: 1.05 } : {}}
            whileTap={verified ? { scale: 0.95 } : {}}
            onClick={launchSimulator}
            disabled={!verified}
            className={`btn-primary px-12 py-5 text-lg ${!verified && 'opacity-30 cursor-not-allowed grayscale'}`}
          >
            <Rocket size={24} />
            Launch SLR Simulator
          </motion.button>
          {!verified && (
            <p className="text-[11px] text-slate-400 mt-4 font-bold tracking-widest uppercase">
              Verification Required to Initialize Simulator
            </p>
          )}
        </div>

        {/* Collapsible Architecture Graph */}
        <div className="mt-16 border-t border-border pt-12">
          <button 
            onClick={() => setIsTopographyExpanded(!isTopographyExpanded)}
            className="flex items-center justify-between w-full group"
          >
            <div className="flex items-center gap-3">
              <Cpu className="text-teal" size={20} />
              <h2 className="text-lg font-bold text-navy-dark tracking-tight uppercase">System Topography & Knowledge Graph</h2>
            </div>
            <motion.div animate={{ rotate: isTopographyExpanded ? 180 : 0 }}>
              <ChevronDown size={24} className="text-slate-400 group-hover:text-teal transition-colors" />
            </motion.div>
          </button>
          
          <AnimatePresence>
            {isTopographyExpanded && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                className="overflow-hidden"
              >
                <div className="pt-12">
                  <KnowledgeGraph />
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </main>
    </div>
  );
}
