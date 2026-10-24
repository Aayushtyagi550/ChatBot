import re
from typing import List, Dict, Any, Optional
from rank_bm25 import BM25Okapi
from backend.ingestion import ingester

class HybridRetriever:
    def __init__(self):
        self.chunks, self.documents = ingester.load_or_ingest()
        self.corpus_tokens = [self._tokenize(c["text"]) for c in self.chunks]
        self.bm25 = BM25Okapi(self.corpus_tokens) if self.corpus_tokens else None

    def _tokenize(self, text: str) -> List[str]:
        """Simple, robust tokenization for municipal documents."""
        text = text.lower()
        # Keep words and alphanumeric identifiers like ch-srm-01, 7:00, 14m2
        tokens = re.findall(r'[a-z0-9]+(?:[-:][a-z0-9]+)?', text)
        return tokens

    def retrieve(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Retrieves top relevant passages for a resident query,
        balancing BM25 lexical precision with document diversity.
        """
        if not self.bm25 or not self.chunks:
            return []

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        # 1. BM25 scoring
        raw_scores = self.bm25.get_scores(query_tokens)

        # 2. Keyword & semantic boosts
        scored_candidates = []
        lower_query = query.lower()

        STOP_WORDS = {"what", "is", "the", "a", "an", "of", "and", "in", "to", "for", "on", "with", "at", "by", "from", "it", "this", "that", "do", "does", "did", "can", "could", "would", "should", "how", "why", "when", "where", "who", "which", "tell", "me", "about"}
        meaningful_tokens = [t for t in query_tokens if t not in STOP_WORDS]
        if not meaningful_tokens:
            return []

        # Domain Guard: Check for municipal concepts vs completely unrelated general knowledge
        MUNICIPAL_TERMS = {
            "service", "services", "request", "requests", "report", "reporting", "portal", "311",
            "pothole", "potholes", "streetlight", "streetlights", "traffic", "sign", "signs",
            "sidewalk", "sidewalks", "curbside", "waste", "garbage", "recycling", "organics", "bin", "bins",
            "pickup", "collection", "drainage", "water", "watermain", "water-main", "flood", "flooding",
            "park", "parks", "tree", "trees", "pruning", "branch", "branches", "snow", "ice", "winter",
            "bylaw", "by-law", "bylaws", "by-laws", "noise", "construction", "equipment", "saw", "decibel",
            "sound", "amplified", "speaker", "speakers", "grass", "weeds", "height", "fence", "fences",
            "parking", "parked", "overnight", "vehicle", "car", "dog", "dogs", "barking", "animal", "animals",
            "patio", "patios", "encroachment", "permit", "permits", "licence", "licences", "license",
            "shed", "sheds", "deck", "decks", "renovation", "renovations", "addition", "additions",
            "inspection", "inspections", "fee", "fees", "variance", "pool", "barrier", "barriers",
            "cedarhaven", "town", "municipal", "ch-srm-01", "ch-byl-02", "ch-per-03", "srm", "byl", "per"
        }

        # If none of the meaningful tokens match municipal terms, query is outside municipal scope
        has_municipal_term = any(t in MUNICIPAL_TERMS for t in meaningful_tokens)
        if not has_municipal_term:
            return []

        for idx, chunk in enumerate(self.chunks):
            base_score = float(raw_scores[idx])
            boost = 0.0

            text_lower = chunk["text"].lower()
            section_lower = chunk["section"].lower()
            sub_lower = chunk.get("subsection", "").lower()

            # Boost if whole meaningful query keywords appear in section or subsection headers
            for tok in meaningful_tokens:
                if len(tok) > 2:
                    if re.search(rf'\b{re.escape(tok)}\b', sub_lower):
                        boost += 3.5
                    elif re.search(rf'\b{re.escape(tok)}\b', section_lower):
                        boost += 2.5

            # Boost exact phrases or critical domain keywords
            critical_keywords = [
                "shed", "deck", "fence", "noise", "pothole", "waste", "garbage",
                "recycling", "barking", "parking", "encroachment", "patio", "pool",
                "permit", "fine", "decibel", "business licence", "7:00", "overnight"
            ]
            for kw in critical_keywords:
                if kw in lower_query and re.search(rf'\b{re.escape(kw)}\b', text_lower):
                    boost += 2.0

            # Boost document ID references if user explicitly mentioned them
            for doc_prefix in ["ch-srm-01", "ch-byl-02", "ch-per-03", "srm", "byl", "per"]:
                if doc_prefix in lower_query and doc_prefix in chunk["doc_id"].lower():
                    boost += 4.0

            final_score = base_score + boost
            # Require meaningful relevance threshold to avoid matching unrelated queries
            if final_score >= 1.5:
                candidate = dict(chunk)
                candidate["score"] = round(final_score, 3)
                scored_candidates.append(candidate)

        # Sort descending by score
        scored_candidates.sort(key=lambda x: x["score"], reverse=True)

        # 3. Deduplication and Context Balancing across documents
        # Ensure we prioritize diverse pages when multi-document queries occur
        selected: List[Dict[str, Any]] = []
        seen_keys = set()

        for c in scored_candidates:
            # Group by doc_id and page_number to avoid redundant tiny slices of the same page
            page_key = (c["doc_id"], c["page_number"])
            if page_key in seen_keys:
                # If we already have this page, only include another subsection if score is exceptionally high
                if len(selected) < top_k and c["score"] > 8.0:
                    selected.append(c)
                continue
            
            seen_keys.add(page_key)
            selected.append(c)

            if len(selected) >= top_k:
                break

        # Fallback if no specific chunks found
        if not selected and scored_candidates:
            selected = scored_candidates[:top_k]

        return selected

# Global retriever instance
retriever = HybridRetriever()
