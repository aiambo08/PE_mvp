# Private Equity Deal Sourcing & Financial Due Diligence Platform

[![Python 3.11](https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110.0-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Pydantic v2](https://img.shields.io/badge/Pydantic-v2.7.0-E92063?style=for-the-badge&logo=pydantic&logoColor=white)](https://docs.pydantic.dev/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.32.2-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)](https://streamlit.io/)
[![Qdrant](https://img.shields.io/badge/Qdrant-Vector_DB-DC2626?style=for-the-badge&logo=qdrant&logoColor=white)](https://qdrant.tech/)
[![Ollama](https://img.shields.io/badge/Ollama-Local_LLM-000000?style=for-the-badge&logo=ollama&logoColor=white)](https://ollama.com/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)

> **Institutional-grade Deal Sourcing & M&A Due Diligence Cockpit** engineered for Mid-Market Private Equity Funds, Investment Committees (IC), and Corporate Finance Advisors. Combines automated web entity ingestion, deterministic thesis scoring, financial covenant stress modeling, and table-aware confidential RAG document intelligence.

---

## 📑 Table of Contents

1. [Executive Overview & Value Proposition](#-executive-overview--value-proposition)
2. [End-to-End System Architecture](#-end-to-end-system-architecture)
3. [Key Features Deep Dive](#-key-features-deep-dive)
   - [Automated Deal Sourcing & Deterministic PE Scoring](#1-automated-deal-sourcing--deterministic-pe-scoring)
   - [LBO Leverage & Debt Covenant Stress Engine](#2-lbo-leverage--debt-covenant-stress-engine)
   - [Confidential Due Diligence RAG with Table Extraction](#3-confidential-due-diligence-rag-with-table-extraction)
   - [Buy-and-Build (Roll-Up) Benchmarking Matrix](#4-buy-and-build-roll-up-benchmarking-matrix)
   - [1-Click Investment Committee Teaser Generator](#5-1-click-investment-committee-teaser-generator)
4. [Tech Stack & Engineering Foundations](#-tech-stack--engineering-foundations)
5. [Project Directory Layout](#-project-directory-layout)
6. [Local Installation & Quickstart Guide](#-local-installation--quickstart-guide)
7. [API Reference Summary](#-api-reference-summary)
8. [Hardware Optimization & Benchmarks (RTX 4060)](#-hardware-optimization--benchmarks-rtx-4060)
9. [Roadmap & Institutional Milestones](#-roadmap--institutional-milestones)

---

## 🏛️ Executive Overview & Value Proposition

Traditional Mid-Market Private Equity origination and preliminary due diligence face three structural bottlenecks:

1. **Manual Sourcing & Inefficient Filtering:** Investment teams waste hundreds of hours manually screening unqualified SMEs that lack institutional maturity, B2B cash conversion, or succession angles.
2. **AI Hallucination & Financial Fragility:** Generic LLM wrappers hallucinate critical financial figures, invert operating leverage formulas, or misinterpret non-recurring EBITDA add-backs.
3. **Data Leakage & Privacy Concerns:** Uploading proprietary CIMs (Confidential Information Memorandums) and commercial audit reports to public cloud APIs violates standard M&A Non-Disclosure Agreements (NDAs).

### Core Architectural Differentiators

```
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│                             ARCHITECTURAL DIFFERENTIATORS                                │
├──────────────────────────┬──────────────────────────────┬────────────────────────────────┤
│ Feature                  │ Standard AI Prototypes       │ PE Deal Sourcing Platform      │
├──────────────────────────┼──────────────────────────────┼────────────────────────────────┤
│ Target Scoring           │ LLM hallucinated scores (0-10)│ Deterministic Rule Engine (0-100)│
│ Financial RAG            │ Plain text chunking (breaks  │ Table-aware PDF parsing        │
│                          │ financial statement columns) │ (pdfplumber + Markdown pipes)  │
│ Data Isolation           │ Third-party cloud endpoints  │ 100% On-Premise GPU Inference  │
│ LBO Stress Modeling      │ Absent or naive fixed margin │ Degree of Operating Leverage   │
│                          │                              │ (DOL) + DSCR + Covenant Headroom│
│ Decoupling               │ Hardcoded monolithic logic   │ Clean REST API + Pydantic v2   │
└──────────────────────────┴──────────────────────────────┴────────────────────────────────┘
```

---

## 🏗️ End-to-End System Architecture

```mermaid
flowchart TD
    subgraph INGESTION ["1. Multi-Modal Ingestion Layer"]
        A1[Target Website URL] -->|Playwright Headless + BS4| B1[Raw HTML & Subpages]
        A2[Confidential CIM / Audit PDF] -->|pdfplumber Structured Extractor| B2[Markdown Tables + Paragraphs]
    end

    subgraph STRUCTURAL_AI ["2. Inference & Schema Validation"]
        B1 --> C1[Instructor + Qwen2.5 7B / Gemini / OpenAI]
        C1 -->|Pydantic v2 Contract| D1[StructuredCompanyProfile]
        D1 --> E1[PEScoringEngine Deterministic 0-100]
    end

    subgraph VECTOR_ENGINE ["3. Vector Storage & Neural Retrieval"]
        B2 --> F1[LlamaIndex SentenceWindowNodeParser]
        F1 -->|BAAI/bge-small-en-v1.5| G1[Qdrant Vector DB Collection]
        H1[Analyst Due Diligence Query] -->|Cosine Similarity + Domain Filter| G1
        G1 -->|Expanded Context Window + Exact Sources| I1[FinancialRAGService Anti-Hallucination]
    end

    subgraph FINANCIAL_SIM ["4. Financial Modeling & Stress Engine"]
        J1[LBO Capital Structure Inputs] --> K1[FinancialStressEngine]
        K1 -->|DOL + Variable Cost Absorption| L1[Sensitivity Scenarios -5% to -20%]
    end

    subgraph PRESENTATION ["5. Presentation & Deal Cockpit"]
        E1 --> M1[FastAPI Backend /api/v1]
        I1 --> M1
        L1 --> M1
        M1 --> N1[Streamlit Deal Cockpit UI - Terminal Noir]
        N1 --> O1[1-Click IC Teaser PDF Export]
    end
```

---

## 🚀 Key Features Deep Dive

### 1. Automated Deal Sourcing & Deterministic PE Scoring

The platform ingests target company websites via a Windows-safe asynchronous `Playwright` crawler, extracting main navigation paths, value propositions, client portals, and contact emails.

The raw content is parsed by `Instructor` into strict `Pydantic v2` models (`StructuredCompanyProfile`) and evaluated by the **Deterministic PE Scoring Engine** across 4 institutional pillars:

$$\text{PE Target Score} = S_{\text{Business Model}} + S_{\text{Scale}} + S_{\text{Digital Signals}} + S_{\text{M&A Thesis}}$$

* **Business Model (Max 30 pts):** Prioritizes B2B SaaS (30 pts), Industrial Manufacturing (28 pts), and Logistics/Distribution (25 pts) over B2C/Mixed models.
* **Company Scale (Max 25 pts):** Optimal sweet spot for Mid-Market Buyouts: Medium Businesses (50–249 FTEs: 25 pts) and Small Businesses (10–49 FTEs: 18 pts).
* **Digital Transformation Opportunity (Max 15 pts):** Detects Client Portals (+8), Modern Tech Stack (+7), direct eCommerce (+5), and active tech hiring (+2).
* **M&A & Generational Succession Thesis (Max 30 pts):** Considers inorganic Buy-and-Build potential (+15) and founder-led / family-owned succession dynamics (+15).

Targets are assigned institutional tiers:
* 🟢 **Tier 1 (High Priority):** $\ge 75\text{ pts}$ (Prime candidate for Investment Committee review).
* 🟡 **Tier 2 (Qualified):** $50 - 74\text{ pts}$ (Requires commercial qualification).
* 🔴 **Tier 3 (Discard):** $< 50\text{ pts}$ (Non-strategic / Out of mandate).

---

### 2. LBO Leverage & Debt Covenant Stress Engine

A dedicated financial sensitivity engine (`FinancialStressEngine`) that models the impact of demand contraction on cash flows using the **Degree of Operating Leverage (DOL)**:

$$\Delta \text{Costes Variables} = \Delta \text{Ventas} \times \left(\frac{(\text{Ventas} - \text{EBITDA}) \times (1 - \text{Fixed Ratio})}{\text{Ventas}}\right)$$

$$\Delta \text{EBITDA} = \Delta \text{Ventas} - \Delta \text{Costes Variables}$$

* **Covenant Headroom:** Quantifies the exact percentage buffer before breaching the Net Debt / EBITDA threshold.
* **Debt Service Coverage Ratio (DSCR):** Computes $CFADS / \text{Annual Debt Service}$ across $-5\%$, $-10\%$, $-15\%$, and $-20\%$ demand shocks.
* **Net Cash Resiliency:** Formally guards against division-by-zero anomalies in debt-free targets.


---

### 3. Confidential Due Diligence RAG with Table Extraction

Standard RAG pipelines break financial statements because traditional chunkers slice multi-column PDF tables into illegible fragments.

This platform implements a specialized ingestion and retrieval architecture:
* **Table-Preserving Extraction:** `pdfplumber` isolates tabular coordinates and converts financial statements into clean Markdown pipes.
* **Sentence-Window Retrieval:** `LlamaIndex`'s `SentenceWindowNodeParser` indexes focused sentence units while retaining a $\pm 5$ sentence context window for query-time synthesis.
* **Strict Anti-Hallucination System Prompt:** Enforces strict provenance rules—if a figure is not explicitly recorded, the engine outputs *"INFORMACIÓN INSUFICIENTE EN LOS DOCUMENTOS ANALIZADOS"*, completely forbidding speculative calculations.
* **Granular Source Attribution:** Every response provides the exact filename, page number, semantic similarity score, and verbatim excerpt.

---

### 4. Buy-and-Build (Roll-Up) Benchmarking Matrix

A comparative side-by-side cockpit allowing investment directors to benchmark 2 to 5 targets simultaneously:
* Dynamic comparison across all evaluation criteria, digital maturity signals, and key operational risks.
* Aggregate group synergy analytics: Average PE Score, Roll-up Eligibility count, Generational Transition count, and Digital Gap opportunities.

---

### 5. 1-Click Investment Committee Teaser Generator

Generates executive, institutional-grade 1-page PDF Investment Teasers formatted specifically for Partner / Investment Committee distribution. Rendered cleanly using a headless HTML-to-PDF pipeline with complete visual score breakdowns.

---

## 🛠️ Tech Stack & Engineering Foundations

| Domain | Technology / Library | Version | Purpose |
| :--- | :--- | :--- | :--- |
| **Web Ingestion** | `Playwright` / `BeautifulSoup4` | `1.42.0` | Async headless browser crawling & DOM cleaning |
| **Document Processing** | `pdfplumber` | `0.11.0` | Tabular PDF extraction with Markdown pipe preservation |
| **Structured AI** | `instructor` | `1.1.0` | Strict Pydantic JSON schema extraction from LLMs |
| **Local LLM Inference** | `Ollama` (`Qwen2.5 7B`) | `0.5.x` | On-premise, privacy-first reasoning (Q5_K_M quantization) |
| **Cloud LLM (Fallback)** | Google Gemini / OpenAI | `v1beta` / `v1` | Optional high-throughput enterprise API providers |
| **Vector Store** | `Qdrant` | `1.8.0` | Production vector database with metadata payload filtering |
| **Embeddings** | `BAAI/bge-small-en-v1.5` | `384-dim` | Fast, high-accuracy semantic vector representations |
| **RAG Orchestration** | `LlamaIndex` | `0.10.19` | Sentence-Window parsing & context expansion |
| **Backend API** | `FastAPI` / `Uvicorn` | `0.110.0` | Async REST microservice with automated OpenAPI docs |
| **Data Contracts** | `Pydantic v2` / `Pydantic-Settings` | `2.7.0` | Strict data validation & environment configuration |
| **Frontend UI** | `Streamlit` | `1.32.2` | High-density Terminal Noir Deal Cockpit |
| **PDF Reporting** | `Playwright` / `WeasyPrint` | `1.42.0` | High-resolution Investment Committee Teaser PDFs |

---

## 📂 Project Directory Layout

```text
pe-deal-sourcing-mvp/
├── .env.example                 # Template for environment variables
├── docker-compose.yml           # Multi-container orchestration (FastAPI + Streamlit + Qdrant)
├── pyproject.toml               # Modern Python build & packaging metadata
├── requirements.txt             # Pinned project dependencies
├── run.py                       # Windows-safe startup script with ProactorEventLoop
│
├── app/
│   ├── config.py                # Pydantic BaseSettings configuration
│   ├── main.py                  # FastAPI application entrypoint & API routes
│   ├── streamlit_app.py         # Streamlit Deal Cockpit frontend
│   │
│   ├── models/                  # Pydantic v2 Data Contracts
│   │   ├── financial_schemas.py # LBO sensitivity & EBITDA bridge schemas
│   │   ├── rag_schemas.py       # RAG upload, query & source citation models
│   │   ├── raw_schemas.py       # Raw scraped web page data structures
│   │   └── structured_schemas.py# Structured SME profiles & scoring enums
│   │
│   ├── scrapers/                # Web Ingestion Layer
│   │   └── company_scraper.py   # Threaded Playwright scraper with retry logic
│   │
│   ├── services/                # Core Business Logic Layer
│   │   ├── document_service.py  # PDF table parser & Qdrant ingestion pipeline
│   │   ├── extraction_service.py# Multi-provider LLM extractor (Instructor)
│   │   ├── financial_simulation_service.py # LBO DOL & Covenant sensitivity engine
│   │   ├── rag_service.py       # Anti-hallucination RAG reasoning & source citations
│   │   ├── report_service.py    # Executive PDF Teaser generator
│   │   └── scoring_service.py   # Deterministic PE Scoring Engine (0-100)
│   │
│   └── ui/                      # Frontend Components & API Client
│       ├── api_client.py        # Decoupled REST client for FastAPI
│       └── benchmarking_view.py # Buy-and-Build comparative matrix
│
├── data/
│   ├── processed_json/          # Structured target outputs
│   ├── reports/                 # Generated IC PDF teasers
│   └── uploaded_pdfs/           # Temporary storage for indexed CIMs
│
└── test/
    ├── test_scoring.py          # Deterministic scoring validation tests
    └── test_phase3_rag.py       # End-to-end RAG verification suite
```

---

## ⚡ Local Installation & Quickstart Guide

### Prerequisites

* **Operating System:** Windows 10/11, macOS, or Linux (Ubuntu 22.04 LTS recommended).
* **Python:** Python 3.11 installed.
* **Package Manager:** `uv` (recommended) or standard `pip`.
* **Local LLM Engine:** [Ollama](https://ollama.com/) installed and running.
* **GPU Requirements:** NVIDIA GPU with $\ge 8\text{ GB VRAM}$ (e.g. RTX 3060/4060) for local inference.

---

### Step 1: Clone Repository & Create Virtual Environment

```bash
git clone https://github.com/aiambo08/PE_mvp.git
cd PE_mvp/pe-deal-sourcing-mvp

# Using uv (recommended for ultra-fast setup):
uv venv .venv --python 3.11
.venv\Scripts\activate      # On Windows
# source .venv/bin/activate # On Linux/macOS

uv pip install -r requirements.txt
playwright install chromium
```

---

### Step 2: Configure Environment Variables

Create a `.env` file in the root directory:

```ini
PROJECT_NAME="PE Deal Sourcing MVP"
ENVIRONMENT=development
LOG_LEVEL=INFO

HOST=0.0.0.0
PORT=8000

# Qdrant Vector DB
QDRANT_HOST=localhost
QDRANT_PORT=6333

# LLM Provider Configuration ("ollama", "gemini", or "openai")
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434/v1
LOCAL_LLM_MODEL=qwen2.5:7b-instruct-q5_K_M

# Optional Cloud API Fallbacks:
GEMINI_API_KEY=""
GEMINI_MODEL=gemini-2.0-flash
OPENAI_API_KEY=""
OPENAI_MODEL=gpt-4o-mini
```

---

### Step 3: Pull Ollama Local Model

Ensure Ollama is running and download the optimized Q5_K_M quantized Qwen2.5 model:

```bash
ollama pull qwen2.5:7b-instruct-q5_K_M
```

---

### Step 4: Launch Applications

#### 🔹 Option A: Launching Locally

1. **Start the FastAPI Backend:**
   ```bash
   uv run python run.py --reload
   ```
   * Swagger Documentation: [http://localhost:8000/docs](http://localhost:8000/docs)
   * API Healthcheck: [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health)

2. **Start the Streamlit Deal Cockpit (in a second terminal):**
   ```bash
   uv run streamlit run app/streamlit_app.py
   ```
   * Interactive Cockpit: [http://localhost:8501](http://localhost:8501)

#### 🔹 Option B: Docker Compose (Full Stack + Qdrant)

```bash
docker-compose up --build
```

---

## 📡 API Reference Summary

| Method | Endpoint | Description | Request Payload | Response Model |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/health` | Service health status | _None_ | `{"status": "ok"}` |
| `POST`| `/api/v1/analyze-company`| Crawls website & extracts structured profile | `{"url": "https://company.com"}` | `JSONResponse` (Profile + Score) |
| `GET` | `/api/v1/companies` | Lists all analyzed company profiles | _None_ | `List[Dict[str, Any]]` |
| `POST`| `/api/v1/simulate-leverage`| Runs LBO sensitivity & covenant matrix | `StressSimulationRequest` | `SensitivityMatrixResponse` |
| `POST`| `/api/v1/upload-document`| Indexes CIM PDF into Qdrant vector store | `Multipart (file, company_domain)` | `DocumentUploadResponse` |
| `POST`| `/api/v1/query-rag` | Queries indexed documents with citations | `RAGQueryRequest` | `RAGQueryResponse` |

---

## 📊 Hardware Optimization & Benchmarks (RTX 4060)

The architecture is tuned for consumer GPUs (8 GB VRAM) using strict memory bounds:

```text
+-----------------------------------------------------------------------------+
| VRAM Allocation Breakdown (NVIDIA GeForce RTX 4060 8GB Laptop GPU)          |
+=============================================================================+
| Qwen2.5 7B Instruct (Q5_K_M quantized via Ollama):             ~5.40 GB    |
| BAAI/bge-small-en-v1.5 Embedding Model (PyTorch):              ~0.38 GB    |
| Context Window Buffer (16k max characters limit):              ~0.65 GB    |
| PyTorch CUDA Runtime & Headroom:                               ~0.85 GB    |
+-----------------------------------------------------------------------------+
| Total Peak VRAM Utilization:                                    ~7.28 GB    |
| Safety Headroom Remaining:                                      ~0.72 GB    |
+-----------------------------------------------------------------------------+
```

* **Inference Speed:** $\approx 42 - 48\text{ tokens/sec}$ (FP16 KV Cache offloaded to GPU).
* **Vector Retrieval Latency:** $< 65\text{ ms}$ for Top-4 similarity search in Qdrant.
* **End-to-End Extraction:** $\approx 8 - 14\text{ seconds}$ per target (Scraping + LLM + Scoring).

---

## 🗺️ Roadmap & Institutional Milestones

- [x] **Phase 1:** Asynchronous Headless Scraping with Windows `ProactorEventLoop` safety.
- [x] **Phase 2:** Deterministic PE Target Scoring (0–100) & `Instructor` validation.
- [x] **Phase 3:** Table-preserving Financial RAG with Sentence Window expansion & citations.
- [x] **Phase 4:** Terminal Noir Deal Cockpit, LBO Stress Simulator & Buy-and-Build Matrix.
- [ ] **Phase 5 (Next):** Automated EBITDA Quality of Earnings (QoE) add-back bridges extracted directly from PDF footnotes.
- [ ] **Phase 6:** Multi-tenant workspace isolation with role-based access control (RBAC).
- [ ] **Phase 7:** Automated connector integrations with S&P Capital IQ and PitchBook API feeds.

---

## 📄 License

Distributed under the **MIT License**. See `LICENSE` for more information.

---

<p align="center">
  <b>Built for Institutional Private Equity & M&A Technology Excellence</b><br>
  <sub>Architected with FastAPI, LlamaIndex, Qdrant, Instructor & Streamlit</sub>
</p>
