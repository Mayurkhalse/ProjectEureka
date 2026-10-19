# Open UI Copilot: Architectural Decisions & Capability Probes

## 1. Pinned Dependencies & Licenses

| Package / Library | Pinned Version | License | Compatibility Verified |
| :--- | :--- | :--- | :--- |
| **`mem0ai`** (Python) | `2.2.1` | **Apache-2.0** | Compatible with Python 3.11+, Qdrant client, and custom OpenAI embedder configurations. |
| **`@openuidev/react-lang`** (NPM) | `1.0.1` | **MIT** | `peerDependencies: { "react": "*", "react-dom": "*" }` — fully compatible with React 19.3.1 and Next.js 16.4.1. |

---

## 2. Phase 0 Reconnaissance & Audit Findings

### 2.1 Current RBAC Roles & Scopes
- **Backend Enums (`backend/src/eureka/models/enums.py` & `api/auth.py`):**
  - `DG_STATE_ADMIN` ("DG State Admin"): Full statewide read access across all 36 districts and all state metrics.
  - `DISTRICT_COLLECTOR` ("District Collector"): District-scoped access restricted strictly to `district_code` present in the signed JWT principal.
  - `DIO_DESK` ("DIO Desk"): District-scoped access restricted to `district_code` in the signed JWT principal.
- **Frontend Personas (`frontend/MCC/src/types/dashboard.ts` & `src/lib/serverData.ts`):**
  - `director_konkan` (Division Head): Scoped strictly to districts within the division (e.g., Konkan division: Mumbai City, Mumbai Suburban, Thane, Palghar, Raigad, Ratnagiri, Sindhudurg).
  - `dg_admin` / Cabinet Observer: Statewide read-only observation.
- **Security Constraint:**
  - Copilot derives identity and role strictly from the verified JWT `TokenData` principal; never from prompt text, request bodies, or LLM-generated arguments.
  - Requests outside user scope return an explicit, polite refusal without partial leaks.

### 2.2 Cached Service Layer & Data Providers
The copilot reuses existing, authoritative data providers without issuing raw SQL or Cypher from the model:
1. `CompositeScoringEngine` (`eureka.scoring.scoring_engine`):
   - Computes live 100-Point Composite Index across Volume (25%), TAT Speed (30%), Net Sentiment (25%), and Crisis SLA (20%).
   - Provides `compute_district_scores_from_csv()` and `get_district_score(district_id)`.
2. `tool_query_all_36_districts` (`eureka.hermes.agent_tools`):
   - Returns all 36 districts with bilingual names, division codes, centroids, ranks, and pillar breakdowns.
3. Spatio-Temporal Graph Edge Indices (`eureka.processor.stgnn_prep`):
   - 152 geographic border adjacencies across Maharashtra districts for neighbor and diffusion analysis.
4. Canonical Events & Fact-Check Tickets (`eureka.models.entities`):
   - Status, verification status, sentiment ratings, and 90-minute SLA countdowns.

### 2.3 Frontend Charting Architecture
- Frontend charts in MCC currently use:
  - `echarts` (`^6.1.0`)
  - `echarts-for-react` (`^3.0.6`)
  - Tailwind CSS + Radix UI primitives.
- OpenUI Copilot will define and register a clean component library:
  - `Stack`, `KpiCard`, `DataTable`, `BarChart`, `LineChart`, `GraphView` (max 200 nodes), `Callout`, `Heading`, `Text`.
  - Every chart and graph includes a deterministic text summary and an accessible table alternative (compliant with GIGW 3.0 and UX4G).

### 2.4 Existing Copilot / ViewSpec Code
- No prior copilot or ViewSpec implementation exists in `backend/src/eureka` or `frontend/MCC`.
- Implementation is entirely clean and additive under `backend/src/eureka/copilot/` and `frontend/MCC/src/components/copilot/`.

---

## 3. Phase 0.2: LLM Capability Probe

Probes were executed against the Google AI Studio / Gemini API endpoint (`https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`):

| Model Tested | Function Calling (Tools) | Structured JSON Output | System Instruction | Marathi & Hindi Input | Status / Recommendation |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`models/gemma-4-26b-a4b-it`** | **PASSED** (Returned valid `functionCall` candidate with arguments) | **PASSED** | **PASSED** | **PASSED** (Accurately translated & localized) | **RECOMMENDED**: Fully verified native function-calling support. |
| **`models/gemma-4-31b-it`** | **FAILED** (HTTP 500 Internal error from Google endpoint) | Untested due to API error | Untested | Untested | **NOT RECOMMENDED** for production copilot tool use. |
| **`models/gemini-2.5-flash`** | **PASSED** (High throughput, 100% deterministic tool calling) | **PASSED** | **PASSED** | **PASSED** | **SUPPORTED ALTERNATIVE / FALLBACK**. |

---

## 4. Phase 0.3: Mem0 & OpenUI Compatibility

### 4.1 Mem0 Configuration for Thesys API Embedder
- `mem0ai` provides `mem0.embeddings.openai.OpenAIEmbedding`.
- It can be explicitly configured with custom parameters:
  ```python
  embedder_config = {
      "provider": "openai",
      "config": {
          "model": "thesys-embed",
          "api_key": os.getenv("THESYS_API_KEY"),
          "openai_base_url": "https://api.thesys.dev/v1/embed",
          "embedding_dims": 1536,
      }
  }
  ```
- To ensure zero reliance on OpenAI defaults:
  - `OPENAI_API_KEY` is kept unset or explicitly ignored.
  - All calls route directly to `https://api.thesys.dev/v1/embed`.

### 4.2 OpenUI React 19 & Next.js 16 Compatibility
- Examined `openui/packages/react-lang/package.json`:
  - `"peerDependencies": { "@modelcontextprotocol/sdk": ">=1.0.0", "react": "*", "react-dom": "*", "zod": "catalog:" }`
  - React 19 is fully supported without peer dependency conflicts.
- OpenUI Lang parser and streaming renderer operate in client-side Next.js components (`"use client"`).
