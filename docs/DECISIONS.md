# Open UI Copilot: Architectural Decisions & Capability Probes (v3)

## 1. Pinned Dependencies & Licenses

| Package / Library | Pinned Version | License | Compatibility Verified |
| :--- | :--- | :--- | :--- |
| **`mem0ai`** (Python) | `2.2.1` | **Apache-2.0** | Compatible with Python 3.11+, Qdrant client, and custom embedder configurations. |
| **`@openuidev/react-lang`** (NPM) | `1.0.1` | **MIT** | `peerDependencies: { "react": "*", "react-dom": "*" }` — fully compatible with React 19.3.1 and Next.js 16.4.1. |
| **`openai`** (Python SDK for C1) | `3.33.0` | **Apache-2.0** | Compatible with Python 3.10+ / 3.11+, supports custom `base_url` (`https://api.thesys.dev/v1/embed`) and async streaming. |

---

## 2. Core Directory Reference Clones
The repository references external read-only clones located in the core workspace:
- **`openui`**: `c:\Users\Priyanshu Patil\Documents\program01\savi\openui`
  - Commit Hash: `9823ec05d4b29bc78d101676dc16b44fe17f1830`
  - Status: Read-only reference, excluded via `.gitignore`.
- **`mem0`**: `c:\Users\Priyanshu Patil\Documents\program01\savi\mem0`
  - Commit Hash: `0724291bd864cf807e88ee8981c8226644e8fb42`
  - Status: Read-only reference, excluded via `.gitignore`.

---

## 3. Pre-Phase 0 Baseline Status
- **Branch**: `copilot-v3`
- **Initial Tag**: `copilot-v3-start`
- **Backend Tests**: 48 passed, 0 failed.
- **Copilot Backend Unit Tests**: 20 passed (`backend/tests/test_copilot.py`).
- **Frontend Test Suite**: 22 passed, 0 failed (`npm test` in `frontend/MCC`).
- **Frontend TypeScript Check**: Exited with code 0 (zero type errors via `tsc -p tsconfig.json --noEmit`).
- **Frontend ESLint**: Exited with code 0 (zero lint errors via `eslint .`).
- **Frontend Production Build**: Succeeded in 8.7s with static optimization of 30 pages.

---

## 4. Live Database Truth Reconciliation
Inspecting `backend/eureka.db`:
1. **District Codes**:
   - `MH-03`: **Palghar** (`DIV-KON`)
   - `MH-04`: **Thane** (`DIV-KON`)
   - Assigned collector in `users`: `collector_thane` is mapped to `MH-04`.
   - Verified that earlier test assertions mapping Thane to MH-03 were inverted; the live database establishes MH-04 as Thane and MH-03 as Palghar.
2. **Divisions**:
   - 9 DGIPR divisions exist in `divisions`:
     - `DIV-MUM` (Mumbai)
     - `DIV-KON` (Konkan)
     - `DIV-PUN` (Pune)
     - `DIV-KOL` (Kolhapur)
     - `DIV-LAT` (Latur)
     - `DIV-CSN` (Chhatrapati Sambhajinagar)
     - `DIV-NSK` (Nashik)
     - `DIV-AMT` (Amravati)
     - `DIV-NGP` (Nagpur)
   - User `divhead_pune` is present with `ROLE_DIVISION_HEAD` and `division_code: DIV-PUN`.
3. **District Aliases & 36 vs 37 Districts**:
   - `media_events` contains 37 distinct district strings because both `'Ahilyanagar'` and `'Ahmednagar'` (its former name) are present.
   - `district_aliases` explicitly maps `'Ahmednagar'` to `MH-25` (`Ahilyanagar`).

---

## 5. Phase 1: Thesys C1 Capability Probe & Architectural Choices
- **Target Endpoint**: `https://api.thesys.dev/v1/embed`
- **Live Probe Verification**:
  - `GET https://api.thesys.dev/v1/embed/models` returned HTTP 200 with available models: `c1-20250416`, `c1-latest`, `c1-nightly`, `c1/google/gemini-3-flash/v-20251230`, `c1/openai/gpt-5/v-20251230`.
  - Tested `c1-20250416` with the provided `THESYS_API_KEY`: Key authenticated successfully, model recognized, returned HTTP 429 (`insufficient balance`).
  - Selected Stable Model ID: **`c1-20250416`**.
- **Engine Control & Fallback**:
  - Controlled by `COPILOT_UI_ENGINE`:
    - `deterministic` (default in Phase 1)
    - `c1` (Thesys C1 generative UI with fail-open fallback to deterministic ViewSpec)
- **Role Split**:
  - Gemma handles reasoning, function calling, and grounded factual summary narrative.
  - C1 generates visual presentation specs from quoted tool data.
  - Custom components registered with C1: `KpiCard`, `DataTable`, `BarChart`, `LineChart`, `GraphView`, `Callout`, `Heading`.
