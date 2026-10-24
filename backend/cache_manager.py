import hashlib
import json
import re
import time
from typing import Dict, Any, Optional, List
from pathlib import Path
from backend.config import CACHE_FILE, CACHE_TTL_SECONDS

class CacheManager:
    def __init__(self, cache_file: Path = CACHE_FILE, ttl_seconds: int = CACHE_TTL_SECONDS):
        self.cache_file = cache_file
        self.ttl_seconds = ttl_seconds
        self.memory_cache: Dict[str, Dict[str, Any]] = {}
        self.stats = {
            "total_queries": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "total_latency_saved_ms": 0.0,
            "estimated_tokens_saved": 0
        }
        self.load_cache()

    def normalize_query(self, query: str) -> str:
        """Normalizes a query string for deterministic cache keying."""
        # Lowercase, strip punctuation (except alphanumeric and basic spaces), collapse whitespaces
        q = query.lower().strip()
        q = re.sub(r'[^\w\s]', '', q)
        q = re.sub(r'\s+', ' ', q).strip()
        return q

    def _hash_query(self, normalized_query: str) -> str:
        return hashlib.sha256(normalized_query.encode('utf-8')).hexdigest()

    def load_cache(self) -> None:
        """Loads cached responses and stats from disk if available."""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.memory_cache = data.get("entries", {})
                    self.stats = data.get("stats", self.stats)
            except Exception as e:
                print(f"[CacheManager] Warning: Failed to load cache file: {e}")
                self.memory_cache = {}

    def save_cache(self) -> None:
        """Saves current cache entries and statistics to disk."""
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump({
                    "entries": self.memory_cache,
                    "stats": self.stats
                }, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[CacheManager] Warning: Failed to save cache: {e}")

    def get(self, query: str) -> Optional[Dict[str, Any]]:
        """Look up response from cache. Returns payload if valid, None if cache miss."""
        self.stats["total_queries"] += 1
        normalized = self.normalize_query(query)
        q_hash = self._hash_query(normalized)

        entry = self.memory_cache.get(q_hash)
        if not entry:
            self.stats["cache_misses"] += 1
            return None

        # Check TTL expiration
        age = time.time() - entry.get("timestamp", 0)
        if age > self.ttl_seconds:
            # Expired
            del self.memory_cache[q_hash]
            self.stats["cache_misses"] += 1
            return None

        # Cache Hit!
        self.stats["cache_hits"] += 1
        entry["hit_count"] = entry.get("hit_count", 0) + 1
        saved_latency = entry.get("original_latency_ms", 1200.0)
        self.stats["total_latency_saved_ms"] += saved_latency

        # Estimate saved tokens (~1 token per 4 chars for prompt + response)
        approx_tokens = (len(query) + len(entry.get("answer", ""))) // 4 + 400
        self.stats["estimated_tokens_saved"] += approx_tokens

        return {
            "answer": entry["answer"],
            "citations": entry.get("citations", []),
            "retrieved_chunks": entry.get("retrieved_chunks", []),
            "is_supported": entry.get("is_supported", True),
            "cache_status": "HIT",
            "cached_at": entry.get("timestamp"),
            "hit_count": entry["hit_count"],
            "latency_ms": 1.5,  # Sub-2ms in-memory cache return
            "saved_latency_ms": saved_latency
        }

    def set(
        self,
        query: str,
        answer: str,
        citations: List[Dict[str, Any]],
        retrieved_chunks: List[Dict[str, Any]],
        original_latency_ms: float,
        is_supported: bool = True
    ) -> None:
        """Stores a new query response in cache and syncs to disk."""
        normalized = self.normalize_query(query)
        q_hash = self._hash_query(normalized)

        self.memory_cache[q_hash] = {
            "original_query": query,
            "normalized_query": normalized,
            "answer": answer,
            "citations": citations,
            "retrieved_chunks": retrieved_chunks,
            "is_supported": is_supported,
            "timestamp": time.time(),
            "original_latency_ms": original_latency_ms,
            "hit_count": 0
        }
        self.save_cache()

    def get_stats(self) -> Dict[str, Any]:
        """Returns cache telemetry for dashboard and UI."""
        total = self.stats["total_queries"]
        hits = self.stats["cache_hits"]
        hit_ratio = round((hits / total * 100), 1) if total > 0 else 0.0

        return {
            "total_queries": total,
            "cache_hits": hits,
            "cache_misses": self.stats["cache_misses"],
            "hit_ratio_percent": hit_ratio,
            "cached_entries_count": len(self.memory_cache),
            "total_latency_saved_ms": round(self.stats["total_latency_saved_ms"], 2),
            "estimated_tokens_saved": self.stats["estimated_tokens_saved"]
        }

    def clear(self) -> None:
        """Purges the entire cache and resets hit stats (useful for demos)."""
        self.memory_cache.clear()
        self.stats = {
            "total_queries": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "total_latency_saved_ms": 0.0,
            "estimated_tokens_saved": 0
        }
        self.save_cache()

# Global cache instance
cache_manager = CacheManager()
