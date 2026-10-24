# Cedarhaven Municipal AI Knowledge Assistant

A document-grounded, explainable municipal AI assistant built for the fictional **Town of Cedarhaven**, featuring strict zero-hallucination guardrails, verifiable page-level citations, an interactive Citation Inspector, and a high-performance **Multi-Tier Caching Engine**.

---

## 🏛️ Project Overview

The assistant answers resident inquiries strictly based on three official municipal policy documents:
1. **Service Request Management (`CH-SRM-01`)**: 311 intake, response targets, curbside waste, streetlights, and parks.
2. **By-law Enforcement (`CH-BYL-02`)**: Noise limits, construction hours, on-street parking rules, and fence heights.
3. **Permits and Licensing (`CH-PER-03`)**: Sheds, decks, building permits, business licences, and sidewalk encroachments.

### Key Capabilities
- **Strict Grounding & Zero Hallucination**: Every answer is backed by verifiable in-text citations referencing document ID, 1-indexed page number, and section code.
- **Intent Comprehension & Out-of-Scope Filtering**: Analyzes query intent first. Unrelated questions (e.g. general science or chit-chat) are politely refused without pulling unrelated municipal text.
- **Auditable Citation Source Inspector**: Clicking any citation badge opens a side drawer displaying the verbatim original page text directly from the source PDF.
- **Multi-Tier Caching Engine**: SHA-256 query normalization and two-tier storage (in-memory + disk) drops repeat query latency from ~800ms down to **1.5ms**.
- **Deliberate Gap Adherence**: Explicitly acknowledges intentional policy gaps (such as unstated parking fines or street pickup schedules) using the standard disclosure: *"The supplied Cedarhaven documents do not specify that detail."*

---

## 🚀 Quick Start Guide

### 1. Prerequisites
- **Python 3.10+** (tested on Python 3.14)
- **Node.js 18+** (optional; production frontend build is pre-compiled)
- A **Google Gemini API Key**

### 2. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Add your Gemini API key to `.env`:
```env
GEMINI_API_KEY=your_actual_gemini_api_key_here
PORT=8000
```
*(Note: You can also enter or update your Gemini API Key directly inside the web UI using the "Settings" button.)*

### 3. Install Python Dependencies
```bash
pip install -r requirements.txt
```

### 4. Start the Application
Run the backend server (FastAPI serves both the API and the web interface):
```bash
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```
Open your browser and navigate to:
👉 **`http://127.0.0.1:8000`**

*(Optional: Running Frontend in Dev Mode)*
```bash
cd frontend
npm install
npm run dev
```

---

## 🧭 Live Walkthrough & Demonstration Guide

Test these 5 key scenarios to observe the system's core capabilities:

### Scenario 1: Single-Document Rule & Auditable Citation
* **Question**: `What time must curbside waste bins be placed out on collection day?`
* **Result**:
  - The assistant directly answers that bins must be visible at the curb by **7:00 a.m.** [CH-SRM-01, p. 4].
  - Clicking the citation badge `[1] CH-SRM-01 • Page 4` opens the **Citation Source Inspector Drawer** on the right, displaying the original PDF text.

### Scenario 2: Multi-Tier Caching Speedup
* **Action**: Submit the same query again: `what time must curbside waste bins be placed out on collection day`
* **Result**:
  - The query normalizer matches the SHA-256 key in the in-memory cache, returning the response in **~1.5ms** (down from 800ms+), saving API tokens and server latency.

### Scenario 3: Multi-Document Cross-Synthesis
* **Question**: `A contractor is blocking my sidewalk with renovation materials. Who handles this and how fast?`
* **Result**:
  - Synthesizes rules across multiple municipal departments:
    1. `CH-SRM-01`, Page 8 (311 intake and P2 assessment within 1 business day).
    2. `CH-PER-03`, Page 7 (Encroachment permit requirement and mandatory 1.5m continuous pedestrian path).

### Scenario 4: Deliberate Policy Gap Adherence
* **Question**: `What is the fine for parking past the 3-hour limit?`
* **Result**:
  - The assistant responds: *"The supplied Cedarhaven documents do not specify that detail. Parking penalty amounts are not published and represent an intentional policy gap in the municipal corpus [CH-BYL-02, p. 4]."*
  - Demonstrates strict resistance to hallucinating dollar amounts.

### Scenario 5: Out-of-Scope Guardrail
* **Question**: `what is the speed of light`
* **Result**:
  - The domain guard and query understanding recognize that the question is outside municipal scope.
  - Returns a clean refusal notice with **0 citations**, avoiding false keyword matching (e.g. matching "light" to "streetlights").

---

## 📁 Repository Structure

```
├── backend/
│   ├── app.py                # FastAPI REST API & static asset hosting
│   ├── cache_manager.py      # Two-tier in-memory & persistent disk caching
│   ├── config.py             # Configuration, document registry & model settings
│   ├── generator.py          # Gemini API grounding, query understanding & guardrails
│   ├── ingestion.py          # PyMuPDF chunker preserving page numbers & sections
│   ├── retriever.py          # BM25Okapi + municipal domain guard hybrid retrieval
│   └── test_backend.py       # Automated unit & integration tests
├── frontend/
│   ├── src/
│   │   ├── App.tsx           # React UI with recent chats sidebar & Citation Drawer
│   │   ├── main.tsx          # React application root entry point
│   │   ├── services/api.ts   # Typed backend API client
│   │   └── index.css         # Refined Zinc monochrome design system
│   ├── index.html            # Webpage shell
│   ├── package.json          # Dependencies & build scripts
│   ├── tsconfig.json         # TypeScript configuration
│   └── vite.config.ts        # Vite development proxy & bundler config
├── 01_Cedarhaven_Service_Request_Management.pdf   # CH-SRM-01 municipal policy
├── 02_Cedarhaven_Bylaw_Enforcement.pdf            # CH-BYL-02 municipal policy
├── 03_Cedarhaven_Permits_and_Licensing.pdf        # CH-PER-03 municipal policy
├── requirements.txt          # Python dependencies
├── .env.example              # Environment variables template
├── .gitignore                # Protects secrets (.env) and cache
└── README.md                 # Project guide & walkthrough
```
