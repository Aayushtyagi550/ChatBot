import hashlib
import json
import re
from typing import List, Dict, Any, Tuple
from pathlib import Path
import fitz  # PyMuPDF
from backend.config import DOCUMENTS, INGESTION_CACHE_FILE, ROOT_DIR

class DocumentIngester:
    def __init__(self, cache_file: Path = INGESTION_CACHE_FILE):
        self.cache_file = cache_file
        self.documents: Dict[str, Dict[str, Any]] = {}
        self.chunks: List[Dict[str, Any]] = []
        self.pages_by_doc: Dict[str, Dict[int, str]] = {}

    def _compute_checksums(self) -> Dict[str, str]:
        """Calculates MD5 hash for each PDF file to detect changes."""
        checksums = {}
        for doc_id, doc_meta in DOCUMENTS.items():
            path = doc_meta["path"]
            if path.exists():
                hasher = hashlib.md5()
                with open(path, "rb") as f:
                    hasher.update(f.read())
                checksums[doc_id] = hasher.hexdigest()
        return checksums

    def load_or_ingest(self, force_refresh: bool = False) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Loads processed documents from disk cache or permanent corpus data, else parses PDFs."""
        current_checksums = self._compute_checksums()
        raw_pdfs_present = any(doc_meta["path"].exists() for doc_meta in DOCUMENTS.values())

        # Check candidate cache files: 1. Runtime cache, 2. Committed pre-processed corpus
        candidate_files = [
            self.cache_file,
            ROOT_DIR / "backend" / "data" / "cedarhaven_corpus.json"
        ]

        if not force_refresh:
            for cfile in candidate_files:
                if cfile.exists():
                    try:
                        with open(cfile, "r", encoding="utf-8") as f:
                            cached_data = json.load(f)
                        
                        cached_checksums = cached_data.get("checksums", {})
                        cached_chunks = cached_data.get("chunks", [])

                        # Valid if checksums match, or if running in cloud deployment where raw PDFs are absent
                        if (cached_checksums and cached_checksums == current_checksums) or (not raw_pdfs_present and cached_chunks):
                            print(f"[Ingestion] Loaded {len(cached_chunks)} pre-processed chunks from {cfile.name}.")
                            self.chunks = cached_chunks
                            self.documents = cached_data.get("documents", {})
                            self.pages_by_doc = cached_data.get("pages_by_doc", {})
                            return self.chunks, self.documents
                    except Exception as e:
                        print(f"[Ingestion] Warning reading {cfile}: {e}")

        # Perform actual ingestion
        self.chunks, self.documents, self.pages_by_doc = self._parse_all_pdfs()

        # Save to disk cache
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump({
                    "checksums": current_checksums,
                    "chunks": self.chunks,
                    "documents": self.documents,
                    "pages_by_doc": self.pages_by_doc
                }, f, indent=2, ensure_ascii=False)
            print(f"[Ingestion] Cached {len(self.chunks)} passages to {self.cache_file}.")
        except Exception as e:
            print(f"[Ingestion] Warning: Failed to write ingestion cache: {e}")

        return self.chunks, self.documents

    def _parse_all_pdfs(self) -> Tuple[List[Dict[str, Any]], Dict[str, Any], Dict[str, Dict[int, str]]]:
        all_chunks: List[Dict[str, Any]] = []
        doc_registry: Dict[str, Any] = {}
        pages_by_doc: Dict[str, Dict[int, str]] = {}

        for doc_id, doc_meta in DOCUMENTS.items():
            path = doc_meta["path"]
            if not path.exists():
                print(f"[Ingestion] Error: Document file not found: {path}")
                continue

            doc_pdf = fitz.open(path)
            doc_pages: Dict[int, str] = {}
            doc_registry[doc_id] = {
                "id": doc_id,
                "title": doc_meta["title"],
                "filename": doc_meta["filename"],
                "short_title": doc_meta["short_title"],
                "page_count": len(doc_pdf)
            }

            for page_index in range(len(doc_pdf)):
                page_num = page_index + 1
                raw_text = doc_pdf[page_index].get_text()
                doc_pages[page_num] = raw_text

                # Extract header line for section
                lines = [l.strip() for l in raw_text.split("\n") if l.strip()]
                section_title = f"Page {page_num}"
                for line in lines[:6]:
                    if any(prefix in line for prefix in ["SRM ", "BYL ", "PER ", "Purpose,"]):
                        section_title = line
                        break

                # 1. Full page chunk (essential for cross-table and context cohesion)
                all_chunks.append({
                    "chunk_id": f"{doc_id}_p{page_num}_full",
                    "doc_id": doc_id,
                    "doc_title": doc_meta["filename"],
                    "doc_label": doc_meta["title"],
                    "page_number": page_num,
                    "section": section_title,
                    "subsection": "Full Page Overview & Details",
                    "text": raw_text.strip(),
                    "chunk_type": "page"
                })

                # 2. Granular subsections (for precise BM25 keyword matching)
                subsections = self._split_into_subsections(raw_text, section_title, doc_id, doc_meta["filename"], page_num)
                all_chunks.extend(subsections)

            pages_by_doc[doc_id] = doc_pages
            doc_pdf.close()

        return all_chunks, doc_registry, pages_by_doc

    def _split_into_subsections(
        self,
        text: str,
        section_title: str,
        doc_id: str,
        doc_title: str,
        page_num: int
    ) -> List[Dict[str, Any]]:
        """Splits page text into logical subsection blocks (e.g. '1.1 Accepted channels')."""
        sub_chunks = []
        # Pattern matching e.g. "1.1 Accepted channels" or "2.3 Distinguish the milestones"
        pattern = r'(?m)^(\d+\.\d+\s+[^\n]+)'
        parts = re.split(pattern, text)

        if len(parts) > 1:
            # parts[0] is intro text before first subsection
            intro = parts[0].strip()
            if len(intro) > 60:
                sub_chunks.append({
                    "chunk_id": f"{doc_id}_p{page_num}_sub_0",
                    "doc_id": doc_id,
                    "doc_title": doc_title,
                    "doc_label": DOCUMENTS[doc_id]["title"],
                    "page_number": page_num,
                    "section": section_title,
                    "subsection": "Intro / Context",
                    "text": intro,
                    "chunk_type": "subsection"
                })
            
            for i in range(1, len(parts), 2):
                heading = parts[i].strip()
                body = parts[i+1].strip() if i+1 < len(parts) else ""
                full_sub_text = f"{heading}\n{body}".strip()
                sub_chunks.append({
                    "chunk_id": f"{doc_id}_p{page_num}_sub_{i//2 + 1}",
                    "doc_id": doc_id,
                    "doc_title": doc_title,
                    "doc_label": DOCUMENTS[doc_id]["title"],
                    "page_number": page_num,
                    "section": section_title,
                    "subsection": heading,
                    "text": full_sub_text,
                    "chunk_type": "subsection"
                })
        return sub_chunks

    def get_full_page(self, doc_id: str, page_num: int) -> str:
        """Retrieves complete text of a specific page for the UI drawer."""
        doc_pages = self.pages_by_doc.get(doc_id, {})
        return doc_pages.get(page_num) or doc_pages.get(str(page_num), "")

# Global ingester instance
ingester = DocumentIngester()
