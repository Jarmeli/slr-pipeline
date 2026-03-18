"use client";

import { useStore, ChatMessage, StudyConfig } from "@/store/useStore";
import {
  BarChart3,
  Database,
  Layers,
  MessageSquare,
  Settings,
  LogOut,
  ShieldAlert,
  Send,
  Loader2,
  Trash2,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

export default function SimulatorLayout({ children }: { children: React.ReactNode }) {
  const { activeAgent, setActiveAgent, verified, chatHistory, addMessage, clearChat, lmStudioIp, setStudyConfig, studyConfig } = useStore();
  const router = useRouter();
  const pathname = usePathname();
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!verified && pathname.startsWith("/simulator")) {
      router.push("/");
    }
  }, [verified, pathname, router]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatHistory]);

  const navItems = [
    { id: "DIO", label: "Data Operator", icon: Database },
    { id: "MEL", label: "Model Evaluator", icon: BarChart3 },
    { id: "SIMO", label: "Impact Modeler", icon: Layers },
  ];

  const handleSend = async () => {
    const trimmed = input.trim();
    if (!trimmed || isStreaming) return;
    setInput("");

    addMessage({ role: "user", content: trimmed });
    setIsStreaming(true);

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: trimmed,
          agent: activeAgent,
          lmStudioIp,
          history: chatHistory.slice(-10),
        }),
      });
      const data = await response.json();
      if (data.success) {
        addMessage({ role: "assistant", content: data.reply });
        // If the API parsed a study configuration, persist it and acknowledge
        if (data.studyConfig && (data.studyConfig.trainingTable || data.studyConfig.parcelsTable)) {
          setStudyConfig(data.studyConfig);
          addMessage({
            role: "system",
            content: `Study configuration committed:\n• Training: ${data.studyConfig.trainingTable || 'not specified'}\n• Parcels: ${data.studyConfig.parcelsTable || 'not specified'}\n• Values: ${data.studyConfig.valuesTable || 'not specified'}`,
          });
        }
      } else {
        addMessage({
          role: "assistant",
          content: `System error: ${data.error}. Ensure LM Studio is running at ${lmStudioIp}.`,
        });
      }
    } catch {
      addMessage({
        role: "assistant",
        content: `Connection failed. Check that LM Studio is running at ${lmStudioIp}.`,
      });
    } finally {
      setIsStreaming(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  if (!verified) return null;



  return (
    <div className="flex h-screen bg-navy-dark overflow-hidden font-inter">
      {/* Sidebar */}
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
                activeAgent === item.id ? "bg-navy-light" : "hover:bg-navy-light/50"
              }`}
            >
              <item.icon
                size={22}
                className={activeAgent === item.id ? "text-teal" : "text-slate-400 group-hover:text-slate-200"}
              />
              <div className="absolute left-full ml-4 px-3 py-1 bg-white text-navy-dark text-[10px] font-bold uppercase tracking-widest whitespace-nowrap opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity rounded-sm shadow-xl z-50">
                {item.label}
              </div>
              {activeAgent === item.id && (
                <motion.div layoutId="active-nav" className="absolute left-0 top-0 bottom-0 w-1 bg-teal" />
              )}
            </button>
          ))}
        </div>

        <button onClick={() => router.push("/")} className="p-4 text-slate-500 hover:text-red-400 transition-colors">
          <LogOut size={22} />
        </button>
      </aside>

      {/* Main */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left: Chat Panel */}
        <div className="w-[440px] border-r border-navy-light flex flex-col bg-navy-dark shrink-0">
          {/* Chat Header */}
          <div className="h-14 border-b border-navy-light flex items-center justify-between px-5">
            <div className="flex items-center gap-2">
              <MessageSquare size={16} className="text-teal" />
              <h2 className="text-[10px] font-bold uppercase tracking-[0.2em] text-white">
                Conversational Orchestrator
              </h2>
            </div>
            {chatHistory.length > 1 && (
              <button onClick={clearChat} className="text-slate-500 hover:text-slate-300 transition-colors" title="Clear chat">
                <Trash2 size={14} />
              </button>
            )}
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-5 space-y-4">
            {chatHistory.map((msg, i) => (
              <ChatBubble key={i} message={msg} />
            ))}
            {isStreaming && (
              <div className="flex items-center gap-2 px-4 py-3 bg-navy-light/30 rounded-sm border border-navy-light w-fit">
                <Loader2 size={12} className="animate-spin text-teal" />
                <span className="text-[10px] text-slate-400 uppercase tracking-widest font-bold">Processing...</span>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>

          {/* Input */}
          <div className="p-5 border-t border-navy-light">
            {activeAgent && (
              <div className="mb-3 flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-teal animate-pulse" />
                <span className="text-[9px] font-bold text-teal uppercase tracking-widest">
                  {activeAgent} Agent Context Active
                </span>
              </div>
            )}
            <div className="relative">
              <textarea
                rows={2}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="PROMPT AGENT..."
                disabled={isStreaming}
                className="w-full bg-navy-light/30 border border-navy-light px-4 py-3 pr-12 rounded-sm text-white focus:outline-none focus:border-teal/50 text-xs tracking-wide placeholder:text-slate-500 uppercase font-medium resize-none disabled:opacity-50"
              />
              <button
                onClick={handleSend}
                disabled={!input.trim() || isStreaming}
                className="absolute right-3 bottom-3 p-1.5 bg-teal/20 hover:bg-teal/40 text-teal disabled:opacity-30 rounded-sm transition-colors"
              >
                <Send size={13} />
              </button>
            </div>
            <p className="text-[8px] text-slate-600 mt-2 font-bold uppercase tracking-widest text-center">
              Press Enter to send · Shift+Enter for new line
            </p>

            {/* Study Config Status Strip */}
            {(studyConfig.trainingTable || studyConfig.parcelsTable) && (
              <div className="mt-4 bg-navy-light/40 border border-teal/20 rounded-sm p-3 space-y-1.5">
                <div className="flex items-center gap-2 mb-2">
                  <div className="w-1.5 h-1.5 rounded-full bg-teal" />
                  <span className="text-[9px] font-bold text-teal uppercase tracking-widest">Study Config Active</span>
                </div>
                {studyConfig.trainingTable && (
                  <div className="flex justify-between items-center">
                    <span className="text-[8px] text-slate-500 uppercase font-bold">Training</span>
                    <code className="text-[8px] text-slate-300 bg-navy-dark px-2 py-0.5 rounded-sm truncate max-w-[200px]">{studyConfig.trainingTable}</code>
                  </div>
                )}
                {studyConfig.parcelsTable && (
                  <div className="flex justify-between items-center">
                    <span className="text-[8px] text-slate-500 uppercase font-bold">Parcels</span>
                    <code className="text-[8px] text-slate-300 bg-navy-dark px-2 py-0.5 rounded-sm truncate max-w-[200px]">{studyConfig.parcelsTable}</code>
                  </div>
                )}
                {studyConfig.valuesTable && (
                  <div className="flex justify-between items-center">
                    <span className="text-[8px] text-slate-500 uppercase font-bold">Values</span>
                    <code className="text-[8px] text-slate-300 bg-navy-dark px-2 py-0.5 rounded-sm truncate max-w-[200px]">{studyConfig.valuesTable}</code>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Right: Canvas */}
        <main className="flex-1 bg-slate-100 relative">{children}</main>
      </div>
    </div>
  );
}

function ChatBubble({ message }: { message: ChatMessage }) {
  if (message.role === "system") {
    return (
      <div className="bg-navy-light/40 p-4 rounded-sm border border-navy-light">
        <p className="text-xs text-slate-300 leading-relaxed font-light">{message.content}</p>
        <div className="mt-3 flex items-center gap-2 text-[9px] font-bold text-teal uppercase tracking-widest">
          <ShieldAlert size={11} />
          Protocol: Active Surveillance
        </div>
      </div>
    );
  }

  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] bg-teal/15 border border-teal/25 px-4 py-3 rounded-sm">
          <p className="text-xs text-slate-200 leading-relaxed">{message.content}</p>
        </div>
      </div>
    );
  }

  // assistant
  return (
    <div className="flex justify-start">
      <div className="max-w-[90%] bg-navy-light/50 border border-navy-light px-4 py-3 rounded-sm">
        <div className="flex items-center gap-2 mb-2">
          <div className="w-1.5 h-1.5 rounded-full bg-teal" />
          <span className="text-[9px] font-bold text-teal uppercase tracking-widest">Agent</span>
        </div>
        <p className="text-xs text-slate-300 leading-relaxed whitespace-pre-wrap">{message.content}</p>
      </div>
    </div>
  );
}
