import os
import socket
import time

# Force IPv4 on Windows to prevent IPv6 timeout (WinError 10060)
_orig_getaddrinfo = socket.getaddrinfo
def _getaddrinfo_ipv4(*args, **kwargs):
    responses = _orig_getaddrinfo(*args, **kwargs)
    ipv4 = [r for r in responses if r[0] == socket.AF_INET]
    return ipv4 if ipv4 else responses
socket.getaddrinfo = _getaddrinfo_ipv4

from typing import Dict, Any, Optional, List
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from pathlib import Path

from backend.config import DOCUMENTS, ROOT_DIR
from backend.ingestion import ingester
from backend.retriever import retriever
from backend.generator import generator
from backend.cache_manager import cache_manager

app = FastAPI(
    title="Cedarhaven Municipal AI Knowledge Assistant",
    description="Document-grounded AI knowledge assistant with Multi-Tier Caching for the Town of Cedarhaven.",
    version="1.0.0"
)

# Enable CORS for local frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    message: str = Field(..., description="Resident question or query")
    use_cache: bool = Field(default=True, description="Whether to query the response cache")

class SetKeyRequest(BaseModel):
    api_key: str = Field(..., description="Gemini API Key")

@app.on_event("startup")
async def startup_event():
    print("[Startup] Initializing Cedarhaven Knowledge Base & Caching layer...")
    # Pre-warm ingestion and retriever
    chunks, docs = ingester.load_or_ingest()
    print(f"[Startup] Ingested {len(chunks)} chunks across {len(docs)} documents.")
    cache_stats = cache_manager.get_stats()
    print(f"[Startup] Cache initialized with {cache_stats['cached_entries_count']} entries.")

@app.get("/api/health")
def health_check():
    has_key = bool(generator.api_key)
    return {
        "status": "healthy",
        "gemini_configured": has_key,
        "model": generator.model_name,
        "document_count": len(DOCUMENTS)
    }

@app.post("/api/config/key")
def set_gemini_key(req: SetKeyRequest):
    """Allows setting the Gemini API key from the UI without restarting the server."""
    if not req.api_key.strip():
        raise HTTPException(status_code=400, detail="API key cannot be empty.")
    generator.update_api_key(req.api_key)
    return {"status": "success", "message": "Gemini API Key updated successfully."}

@app.get("/api/documents")
def get_documents():
    """Returns the list of authoritative Cedarhaven policy documents."""
    docs = []
    for d in DOCUMENTS.values():
        item = dict(d)
        item["path"] = str(item["path"])
        docs.append(item)
    return {
        "documents": docs
    }

@app.get("/api/documents/{doc_id}/page/{page_number}")
def get_document_page(doc_id: str, page_number: int):
    """Returns full page content for the Citation Inspector Drawer."""
    doc_id_upper = doc_id.upper()
    if doc_id_upper not in DOCUMENTS:
        raise HTTPException(status_code=404, detail="Document ID not found.")
    
    text = ingester.get_full_page(doc_id_upper, page_number)
    if not text:
        raise HTTPException(status_code=404, detail=f"Page {page_number} not found for document {doc_id}.")

    return {
        "doc_id": doc_id_upper,
        "doc_title": DOCUMENTS[doc_id_upper]["filename"],
        "doc_label": DOCUMENTS[doc_id_upper]["title"],
        "page_number": page_number,
        "content": text
    }

@app.get("/api/cache/stats")
def get_cache_stats():
    """Returns real-time cache telemetry (hits, misses, ratio, latency saved)."""
    return cache_manager.get_stats()

@app.post("/api/cache/clear")
def clear_cache():
    """Purges the query cache and resets statistics."""
    cache_manager.clear()
    return {"status": "success", "message": "Cache successfully cleared."}

@app.post("/api/chat")
def chat(req: ChatRequest):
    """
    Main endpoint for resident queries.
    Executes Caching Lookup -> Hybrid Retrieval -> Gemini Grounding -> Citation Verification.
    """
    query = req.message.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    # 1. Caching Layer Check
    if req.use_cache:
        cached_result = cache_manager.get(query)
        if cached_result:
            return cached_result

    # 2. Hybrid Retrieval (BM25 + Domain Boosts)
    retrieved = retriever.retrieve(query, top_k=5)

    # 3. Gemini Generation with Grounding & Guardrails
    answer, citations, latency_ms, is_supported = generator.generate_answer(query, retrieved)

    # 4. Save to Cache
    if req.use_cache and answer:
        cache_manager.set(
            query=query,
            answer=answer,
            citations=citations,
            retrieved_chunks=retrieved,
            original_latency_ms=latency_ms,
            is_supported=is_supported
        )

    return {
        "answer": answer,
        "citations": citations,
        "retrieved_chunks": retrieved,
        "is_supported": is_supported,
        "cache_status": "MISS",
        "cached_at": None,
        "hit_count": 0,
        "latency_ms": latency_ms,
        "saved_latency_ms": 0.0
    }

# Mount static frontend build if it exists
frontend_dist = ROOT_DIR / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
