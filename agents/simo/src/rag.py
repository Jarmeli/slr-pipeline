"""SIMO RAG Pipeline — ChromaDB + LM Studio."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import chromadb
from openai import OpenAI

CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "/artifacts/chroma")
LM_STUDIO_URL = os.getenv("LM_STUDIO_URL", "http://host.docker.internal:1234/v1")
LM_STUDIO_MODEL = os.getenv("LM_STUDIO_MODEL", "local-model")

_chroma_client: Optional[chromadb.PersistentClient] = None
_collection: Optional[chromadb.Collection] = None
_llm_client: Optional[OpenAI] = None


def _get_chroma() -> chromadb.Collection:
    global _chroma_client, _collection
    if _collection is None:
        # Disable telemetry to prevent crashes in restricted network/env
        settings = chromadb.Settings(anonymized_telemetry=False)
        _chroma_client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR, settings=settings)
        _collection = _chroma_client.get_or_create_collection(
            name="slr_reports",
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def _get_llm() -> OpenAI:
    global _llm_client
    if _llm_client is None:
        _llm_client = OpenAI(base_url=LM_STUDIO_URL, api_key="lm-studio")
    return _llm_client


def index_simulation_report(run_id: str, report: Dict[str, Any]) -> int:
    """Index a simulation report into ChromaDB. Returns number of chunks indexed."""
    col = _get_chroma()
    chunks: List[Dict[str, str]] = []

    summary = (
        f"Simulation run {run_id} covered {report.get('total_parcels', 0)} parcels "
        f"across flood levels {report.get('flood_levels', [])} feet."
    )
    chunks.append({"id": f"{run_id}_summary", "text": summary})

    for level_str, stats in report.get("results_by_level", {}).items():
        text = (
            f"At {level_str} of flooding: "
            f"{stats['parcel_count']} parcels affected, "
            f"total exposure ${stats['total_exposure']:,.0f}, "
            f"mean damage per parcel ${stats['mean_damage']:,.0f}."
        )
        chunks.append({"id": f"{run_id}_{level_str}", "text": text})

    col.upsert(
        ids=[c["id"] for c in chunks],
        documents=[c["text"] for c in chunks],
        metadatas=[{"run_id": run_id} for _ in chunks],
    )
    return len(chunks)


def chat(question: str, top_k: int = 4) -> str:
    """Retrieve relevant context from ChromaDB and answer via LM Studio."""
    col = _get_chroma()
    results = col.query(query_texts=[question], n_results=top_k)
    docs = results.get("documents", [[]])[0]

    context = "\n".join(f"- {d}" for d in docs) if docs else "No simulation reports available yet."

    system_prompt = (
        "You are an expert assistant for the Rookery Bay Sea Level Rise research project. "
        "Answer questions about flood damage predictions, parcel exposure, and simulation results "
        "using only the provided context. Be concise and precise."
    )
    user_message = f"Context:\n{context}\n\nQuestion: {question}"

    llm = _get_llm()
    response = llm.chat.completions.create(
        model=LM_STUDIO_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=0.3,
        max_tokens=512,
    )
    return response.choices[0].message.content or ""
