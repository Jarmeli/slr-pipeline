"use client";

import React, { useMemo } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  Edge,
  Node,
  MarkerType,
  Position,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { 
  User, 
  Settings, 
  Database, 
  Cpu, 
  BarChart3, 
  Layers,
  Circle
} from 'lucide-react';

const nodeDefaults = {
  sourcePosition: Position.Right,
  targetPosition: Position.Left,
  style: {
    borderRadius: '2px',
    border: '1px solid #E2E8F0',
    background: '#fff',
    width: 220,
    padding: '12px',
  },
};

const NodeLabel = ({ icon: Icon, label, sublabel }: { icon: any, label: string, sublabel: string }) => (
  <div className="flex items-center gap-3">
    <div className="w-8 h-8 rounded-sm bg-slate-50 border border-slate-100 flex items-center justify-center shrink-0">
      <Icon size={16} className="text-teal" />
    </div>
    <div className="text-left overflow-hidden">
      <div className="text-[10px] font-bold text-navy-dark truncate uppercase tracking-tight">{label}</div>
      <div className="text-[9px] text-slate-400 truncate font-medium uppercase tracking-widest">{sublabel}</div>
    </div>
  </div>
);

const initialNodes: Node[] = [
  {
    id: 'user',
    type: 'default',
    data: { label: <NodeLabel icon={User} label="Researcher" sublabel="Instruction Layer" /> },
    position: { x: 0, y: 150 },
    ...nodeDefaults,
  },
  {
    id: 'prepper',
    type: 'default',
    data: { label: <NodeLabel icon={Settings} label="Prepper Config" sublabel="Phase 0: Orchestrator" /> },
    position: { x: 300, y: 150 },
    ...nodeDefaults,
  },
  {
    id: 'postgres',
    type: 'default',
    data: { label: <NodeLabel icon={Database} label="PostgreSQL / PostGIS" sublabel="Azure Geo-Database" /> },
    position: { x: 600, y: 150 },
    ...nodeDefaults,
    style: { ...nodeDefaults.style, border: '1px solid #20B2AA' },
  },
  {
    id: 'dio',
    type: 'default',
    data: { label: <NodeLabel icon={Cpu} label="DIO Agent" sublabel="Data Operations" /> },
    position: { x: 900, y: 50 },
    ...nodeDefaults,
  },
  {
    id: 'mel',
    type: 'default',
    data: { label: <NodeLabel icon={BarChart3} label="MEL Agent" sublabel="Model Evaluation" /> },
    position: { x: 900, y: 150 },
    ...nodeDefaults,
  },
  {
    id: 'simo',
    type: 'default',
    data: { label: <NodeLabel icon={Layers} label="SIMO Agent" sublabel="Impact Modeling" /> },
    position: { x: 900, y: 250 },
    ...nodeDefaults,
  },
];

const initialEdges: Edge[] = [
  { 
    id: 'e1-2', source: 'user', target: 'prepper', 
    markerEnd: { type: MarkerType.ArrowClosed, color: '#20B2AA' },
    style: { stroke: '#20B2AA' }
  },
  { 
    id: 'e2-3', source: 'prepper', target: 'postgres', 
    markerEnd: { type: MarkerType.ArrowClosed, color: '#20B2AA' },
    style: { stroke: '#20B2AA' }
  },
  { 
    id: 'e3-4', source: 'postgres', target: 'dio', animated: true,
    markerEnd: { type: MarkerType.ArrowClosed, color: '#E2E8F0' },
    style: { stroke: '#E2E8F0' }
  },
  { 
    id: 'e3-5', source: 'postgres', target: 'mel', animated: true,
    markerEnd: { type: MarkerType.ArrowClosed, color: '#E2E8F0' },
    style: { stroke: '#E2E8F0' }
  },
  { 
    id: 'e3-6', source: 'postgres', target: 'simo', animated: true,
    markerEnd: { type: MarkerType.ArrowClosed, color: '#E2E8F0' },
    style: { stroke: '#E2E8F0' }
  },
  { 
    id: 'e4-5', source: 'dio', target: 'mel', 
    markerEnd: { type: MarkerType.ArrowClosed, color: '#E2E8F0' },
    style: { stroke: '#E2E8F0' }
  },
  { 
    id: 'e5-6', source: 'mel', target: 'simo', 
    markerEnd: { type: MarkerType.ArrowClosed, color: '#E2E8F0' },
    style: { stroke: '#E2E8F0' }
  },
];

export default function KnowledgeGraph() {
  return (
    <div className="graph-container">
      <ReactFlow
        nodes={initialNodes}
        edges={initialEdges}
        fitView
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={20} color="#F1F5F9" />
        <Controls showInteractive={false} className="bg-white border-border rounded-none shadow-none" />
      </ReactFlow>
      
      {/* Legend */}
      <div className="absolute top-4 right-4 bg-white/90 backdrop-blur-sm border border-border p-3 flex flex-col gap-2">
        <div className="flex items-center gap-2">
          <Circle size={8} className="fill-teal text-teal" />
          <span className="text-[10px] font-bold text-navy-dark uppercase tracking-wider">Active Core</span>
        </div>
        <div className="flex items-center gap-2">
          <Circle size={8} className="fill-slate-200 text-slate-200" />
          <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Passive Service</span>
        </div>
      </div>
    </div>
  );
}
