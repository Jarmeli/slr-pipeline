"""API Client for the SLR Multi-Agent Pipeline.

Provides asynchronous functions to interact with the backend FastAPI services.
"""
import httpx
from typing import Any, Dict, List, Optional
import os


class APIClient:
    def __init__(self):
        # Allow overriding endpoints via env, but default to localhost ports
        self.dio_url = os.getenv("DIO_URL", "http://localhost:7001")
        self.mel_url = os.getenv("MEL_URL", "http://localhost:7002")
        self.simo_url = os.getenv("SIMO_URL", "http://localhost:7003")

    async def _post(self, url: str, endpoint: str, json_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        full_url = f"{url}{endpoint}"
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(full_url, json=json_data or {})
            response.raise_for_status()
            return response.json()

    async def _get(self, url: str, endpoint: str) -> Any:
        full_url = f"{url}{endpoint}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(full_url)
            response.raise_for_status()
            return response.json()

    # --- Prepper (Phase 0) ---
    # In a real deployed version, Prepper has an endpoint. For local UI, we might just test the DB connection
    # directly or hit a healthcheck endpoint on any agent.
    async def check_health(self) -> bool:
        """Check if backend services are up."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{self.dio_url}/tools")
                return resp.status_code == 200
        except Exception:
            return False

    # --- DIO (Phase 1) ---
    async def clean_claims(self) -> Dict[str, Any]:
        return await self._post(self.dio_url, "/call/clean_claims")

    async def clip_study_area(self, bounds_geojson: Dict[str, Any]) -> Dict[str, Any]:
        # For now, DIO's clean_claims just does standard processing. We simulate clipping or just call clean.
        # This can be expanded if DIO adds a specific clip tool.
        return await self.clean_claims()

    async def get_raw_tables(self) -> List[Dict[str, str]]:
        return await self._get(self.dio_url, "/tables")

    async def export_handoff(self, source_table: Optional[str] = None, source_schema: str = "clean_data") -> Dict[str, Any]:
        payload = {}
        if source_table:
            payload["source_table"] = source_table
            payload["source_schema"] = source_schema
        return await self._post(self.dio_url, "/handoff", payload)

    async def get_table_extent(self, table: str, schema: str = "public") -> Dict[str, Any]:
        return await self._get(self.dio_url, f"/table-extent?table={table}&schema={schema}")

    # --- MEL (Phase 2) ---
    async def configure_run(self, handoff_token: Dict[str, Any], target_col: str) -> Dict[str, Any]:
        return await self._post(self.mel_url, "/call/configure_run", {"handoff_token": handoff_token, "target_col": target_col})

    async def run_full_training_pipeline(self, handoff_token: Dict[str, Any], target_col: str) -> Dict[str, Any]:
        """Convenience to run the 5 MEL steps sequentially."""
        print("Configuring run...")
        config_res = await self.configure_run(handoff_token, target_col)
        
        print("Fitting GMM...")
        await self._post(self.mel_url, "/call/fit_gmm", {"n_components": 3})
        
        print("Applying transform...")
        await self._post(self.mel_url, "/call/apply_transform", {"method": "yeo-johnson"})
        
        print("Training ensemble...")
        train_res = await self._post(self.mel_url, "/call/train_ensemble", {})
        
        print("Selecting best...")
        await self._post(self.mel_url, "/call/select_best", {"metric": "R2"})
        
        print("Exporting artifact...")
        artifact_token = await self._post(self.mel_url, "/call/export_artifacts", {})
        
        return {
            "metrics": train_res.get("metrics", []),
            "artifact_token": artifact_token
        }

    # --- SIMO (Phase 3) ---
    async def load_artifact(self, artifact_token: Dict[str, Any]) -> Dict[str, Any]:
        return await self._post(self.simo_url, "/call/load_artifact", {"artifact_token": artifact_token})

    async def run_simulation(self, flood_levels: List[float], value_table: Optional[str] = None, value_col: Optional[str] = None, parcel_table: Optional[str] = None) -> Dict[str, Any]:
        payload = {"flood_levels": flood_levels}
        if value_table: payload["value_table"] = value_table
        if value_col: payload["value_col"] = value_col
        if parcel_table: payload["parcel_table"] = parcel_table
        return await self._post(self.simo_url, "/call/run_simulation", payload)

    async def get_regional_stats(self, polygon: Dict[str, Any], flood_level: float) -> Dict[str, Any]:
        return await self._post(self.simo_url, "/call/regional_stats", {"polygon": polygon, "flood_level": flood_level})

    async def get_report_summary(self, flood_level: float, limit: int = 5) -> Dict[str, Any]:
        return await self._post(self.simo_url, "/call/get_report_summary", {"flood_level": flood_level, "limit": limit})

    async def simo_chat(self, question: str) -> Dict[str, Any]:
        """Ask a natural-language question about simulation results via the SIMO RAG pipeline."""
        return await self._post(self.simo_url, "/call/chat", {"question": question})
