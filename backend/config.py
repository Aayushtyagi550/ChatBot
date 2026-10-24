import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root
ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

# Document directory & files
DOCS_DIR = ROOT_DIR
CACHE_DIR = ROOT_DIR / ".cache"
CACHE_DIR.mkdir(exist_ok=True)

# Three authoritative municipal policy documents
DOCUMENTS = {
    "CH-SRM-01": {
        "id": "CH-SRM-01",
        "filename": "01_Cedarhaven_Service_Request_Management.pdf",
        "title": "Service Request Management (CH-SRM-01)",
        "short_title": "Service Requests",
        "path": DOCS_DIR / "01_Cedarhaven_Service_Request_Management.pdf"
    },
    "CH-BYL-02": {
        "id": "CH-BYL-02",
        "filename": "02_Cedarhaven_Bylaw_Enforcement.pdf",
        "title": "By-law Enforcement (CH-BYL-02)",
        "short_title": "By-law Enforcement",
        "path": DOCS_DIR / "02_Cedarhaven_Bylaw_Enforcement.pdf"
    },
    "CH-PER-03": {
        "id": "CH-PER-03",
        "filename": "03_Cedarhaven_Permits_and_Licensing.pdf",
        "title": "Permits and Licensing (CH-PER-03)",
        "short_title": "Permits & Licensing",
        "path": DOCS_DIR / "03_Cedarhaven_Permits_and_Licensing.pdf"
    }
}

# API and Model Config
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash").strip()

# Cache Configuration
CACHE_FILE = CACHE_DIR / "query_cache.json"
INGESTION_CACHE_FILE = CACHE_DIR / "ingestion_cache.json"
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "86400"))  # 24 hours default

# Server configuration
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))
