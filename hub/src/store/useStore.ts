import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface DbCredentials {
  host: string;
  port: string;
  user: string;
  database: string;
  password?: string;
}

interface AppState {
  // Phase 0: Prepper Config
  dbCredentials: DbCredentials | null;
  lmStudioIp: string;
  verified: boolean;
  
  // Agent State
  activeAgent: 'DIO' | 'MEL' | 'SIMO' | null;
  
  // Geospatial State
  availableLayers: any[];
  selectedLayer: string | null;
  selectedGeoJson: any | null;
  
  // Actions
  setDbCredentials: (creds: DbCredentials) => void;
  setLmStudioIp: (ip: string) => void;
  setVerified: (status: boolean) => void;
  setActiveAgent: (agent: 'DIO' | 'MEL' | 'SIMO' | null) => void;
  setAvailableLayers: (layers: any[]) => void;
  setSelectedLayer: (layerId: string | null) => void;
  setSelectedGeoJson: (data: any | null) => void;
  reset: () => void;
}

export const useStore = create<AppState>()(
  persist(
    (set) => ({
      dbCredentials: null,
      lmStudioIp: 'http://localhost:1234/v1',
      verified: false,
      activeAgent: null,
      availableLayers: [],
      selectedLayer: null,
      selectedGeoJson: null,

      setDbCredentials: (dbCredentials) => set({ dbCredentials }),
      setLmStudioIp: (lmStudioIp) => set({ lmStudioIp }),
      setVerified: (verified) => set({ verified }),
      setActiveAgent: (activeAgent) => set({ activeAgent }),
      setAvailableLayers: (availableLayers) => set({ availableLayers }),
      setSelectedLayer: (selectedLayer) => set({ selectedLayer }),
      setSelectedGeoJson: (selectedGeoJson) => set({ selectedGeoJson }),
      reset: () => set({ dbCredentials: null, verified: false, activeAgent: null, availableLayers: [], selectedLayer: null, selectedGeoJson: null }),
    }),
    {
      name: 'slr-pipeline-storage',
    }
  )
);
