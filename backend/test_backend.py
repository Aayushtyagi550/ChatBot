import os
import sys
from pathlib import Path

# Add project root to sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.ingestion import ingester
from backend.retriever import retriever
from backend.cache_manager import cache_manager
from backend.generator import generator

def run_tests():
    print("========================================")
    print("Testing Cedarhaven Backend & Ingestion")
    print("========================================")

    # 1. Test Ingestion
    chunks, docs = ingester.load_or_ingest()
    print(f"[OK] Ingested {len(chunks)} chunks across {len(docs)} documents.")
    assert len(docs) == 3, f"Expected 3 documents, got {len(docs)}"
    assert len(chunks) > 20, f"Expected >20 chunks, got {len(chunks)}"

    # 2. Test Retrieval for Benchmark Questions
    print("\n--- Testing Retrieval Accuracy ---")
    
    # Test 1: Single Doc - Waste bin set-out time
    q1 = "What time must waste bins be set out by?"
    res1 = retriever.retrieve(q1, top_k=3)
    print(f"Query 1: '{q1}' -> Top match: {res1[0]['doc_id']} Page {res1[0]['page_number']} ({res1[0]['section']})")
    assert res1[0]["doc_id"] == "CH-SRM-01"
    assert res1[0]["page_number"] == 4, f"Expected page 4 for waste rules, got {res1[0]['page_number']}"

    # Test 2: Construction noise hours
    q2 = "Can a contractor use a power saw at 8 a.m. on Saturday?"
    res2 = retriever.retrieve(q2, top_k=3)
    print(f"Query 2: '{q2}' -> Top match: {res2[0]['doc_id']} Page {res2[0]['page_number']} ({res2[0]['section']})")
    assert res2[0]["doc_id"] == "CH-BYL-02"
    assert res2[0]["page_number"] in [2, 8], f"Expected page 2 or 8 for noise hours, got {res2[0]['page_number']}"

    # Test 3: Shed permit threshold
    q3 = "What size shed requires a building permit?"
    res3 = retriever.retrieve(q3, top_k=3)
    print(f"Query 3: '{q3}' -> Top match: {res3[0]['doc_id']} Page {res3[0]['page_number']} ({res3[0]['section']})")
    assert res3[0]["doc_id"] == "CH-PER-03"
    assert res3[0]["page_number"] == 2, f"Expected page 2 for shed rules, got {res3[0]['page_number']}"

    # 3. Test Caching Layer
    print("\n--- Testing Multi-Tier Caching Layer ---")
    cache_manager.clear()
    assert cache_manager.get(q1) is None, "Cache should be empty after clear"

    # Store entry in cache
    cache_manager.set(
        query=q1,
        answer="Waste bins must be set out by 7:00 a.m. on collection day [CH-SRM-01, Page 4].",
        citations=[{"doc_id": "CH-SRM-01", "page_number": 4}],
        retrieved_chunks=res1,
        original_latency_ms=950.0
    )

    # First retrieval from cache (Hit)
    hit_result = cache_manager.get(q1)
    assert hit_result is not None, "Expected cache hit!"
    assert hit_result["cache_status"] == "HIT"
    print(f"[OK] Cache HIT verified! Returned in {hit_result['latency_ms']}ms (Original saved: {hit_result['saved_latency_ms']}ms)")

    # Punctuation/case normalized hit
    hit_normalized = cache_manager.get("what time must waste bins be set out by???")
    assert hit_normalized is not None, "Expected cache hit on normalized query!"
    print(f"[OK] Normalized Query Cache HIT verified!")

    stats = cache_manager.get_stats()
    print(f"[OK] Cache stats: {stats}")
    assert stats["cache_hits"] == 2

    print("\n========================================")
    print("ALL BACKEND & RETRIEVAL TESTS PASSED! [100%]")
    print("========================================")

if __name__ == "__main__":
    run_tests()
