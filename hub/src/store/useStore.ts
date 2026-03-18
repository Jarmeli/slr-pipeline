import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface DbCredentials {
  host: string;
  port: string;
  user: string;
  database: string;
  password?: string;
}

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: number;
}

export interface StudyConfig {
  trainingTable: string | null;   // e.g. clean_data.collier_claims_cleaned
  parcelsTable: string | null;    // e.g. public.parcels_final
  valuesTable: string | null;     // e.g. public.property_real_value
  targetColumn: string | null;    // e.g. buildingdamageamount
}

interface AppState {
  // Phase 0: Prepper Config
  dbCredentials: DbCredentials | null;
  lmStudioIp: string;
  verified: boolean;

  // Agent State
  activeAgent: 'DIO' | 'MEL' | 'SIMO' | null;

  // Chat State
  chatHistory: ChatMessage[];
  studyConfig: StudyConfig;

  // Geospatial State
  availableLayers: any[];
  selectedLayers: string[];
  layerGeoJsonMap: Record<string, any>;
  clipBounds: [[number, number], [number, number]] | null;

  // Actions
  setDbCredentials: (creds: DbCredentials) => void;
  setLmStudioIp: (ip: string) => void;
  setVerified: (status: boolean) => void;
  setActiveAgent: (agent: 'DIO' | 'MEL' | 'SIMO' | null) => void;
  addMessage: (msg: Omit<ChatMessage, 'timestamp'>) => void;
  clearChat: () => void;
  setStudyConfig: (config: Partial<StudyConfig>) => void;
  setAvailableLayers: (layers: any[]) => void;
  toggleLayer: (layerId: string) => void;
  setLayerGeoJson: (layerId: string, data: any) => void;
  clearLayers: () => void;
  setClipBounds: (bounds: [[number, number], [number, number]] | null) => void;
  reset: () => void;
}

const INITIAL_MESSAGE: ChatMessage = {
  role: 'system',
  content: 'Secure link established with the SLR MCP agents. System telemetry is initialized.',
  timestamp: Date.now(),
};

export const useStore = create<AppState>()(
  persist(
    (set, get) => ({
      dbCredentials: null,
      lmStudioIp: 'http://localhost:1234/v1',
      verified: false,
      activeAgent: null,
      chatHistory: [INITIAL_MESSAGE],
      studyConfig: { trainingTable: null, parcelsTable: null, valuesTable: null, targetColumn: null },
      availableLayers: [],
      selectedLayers: [],
      layerGeoJsonMap: {},
      clipBounds: null,

      setDbCredentials: (dbCredentials) => set({ dbCredentials }),
      setLmStudioIp: (lmStudioIp) => set({ lmStudioIp }),
      setVerified: (verified) => set({ verified }),
      setActiveAgent: (activeAgent) => set({ activeAgent }),

      addMessage: (msg) =>
        set((state) => ({
          chatHistory: [...state.chatHistory, { ...msg, timestamp: Date.now() }],
        })),

      clearChat: () => set({ chatHistory: [INITIAL_MESSAGE] }),

      setStudyConfig: (config) =>
        set((state) => ({ studyConfig: { ...state.studyConfig, ...config } })),

      setAvailableLayers: (availableLayers) => set({ availableLayers }),

      toggleLayer: (layerId) => {
        const { selectedLayers, layerGeoJsonMap } = get();
        if (selectedLayers.includes(layerId)) {
          const newMap = { ...layerGeoJsonMap };
          delete newMap[layerId];
          set({ selectedLayers: selectedLayers.filter((id) => id !== layerId), layerGeoJsonMap: newMap });
        } else {
          set({ selectedLayers: [...selectedLayers, layerId] });
        }
      },

      setLayerGeoJson: (layerId, data) =>
        set((state) => ({ layerGeoJsonMap: { ...state.layerGeoJsonMap, [layerId]: data } })),

      clearLayers: () => set({ selectedLayers: [], layerGeoJsonMap: {} }),

      setClipBounds: (clipBounds) => set({ clipBounds }),

      reset: () =>
        set({
          dbCredentials: null,
          verified: false,
          activeAgent: null,
          chatHistory: [INITIAL_MESSAGE],
          studyConfig: { trainingTable: null, parcelsTable: null, valuesTable: null, targetColumn: null },
          selectedLayers: [],
          layerGeoJsonMap: {},
          clipBounds: null,
          availableLayers: [],
        }),
    }),
    {
      name: 'slr-pipeline-storage',
      partialize: (s) => ({
        dbCredentials: s.dbCredentials,
        lmStudioIp: s.lmStudioIp,
        verified: s.verified,
        activeAgent: s.activeAgent,
        availableLayers: s.availableLayers,
      }),
    }
  )
);
