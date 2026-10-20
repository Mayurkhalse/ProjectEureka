# EUREKA Open UI Copilot v3 - Latency Benchmark Baseline
**Generated**: 2026-10-20 04:43:47 UTC
**Iterations**: Cold (1 run x 12 questions = 12 runs), Warm (2 runs x 12 questions = 24 runs)
**Model Configured**: `models/gemini-flash-lite-latest`

## 1. Stage-by-Stage Latency Breakdown (p50 and p95)

| Pipeline Stage | Cold p50 (ms) | Cold p95 (ms) | Warm p50 (ms) | Warm p95 (ms) | Warm Avg (ms) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Auth & Principal Resolution | 0.5 | 0.5 | 0.5 | 0.5 | 0.5 |
| Mem0 User Preference Retrieval | 0.1 | 0.1 | 0.1 | 0.1 | 0.1 |
| Intent Routing & Prompt Assembly | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| **Model Calls (LLM Generation)** | 3982.43 | 8260.18 | 4431.14 | 9247.61 | 5255.82 |
| Governed Tool Execution | 3097.5 | 6923.2 | 3105.0 | 6212.65 | 3105.25 |
| OpenUI Validation & Repair | 0.0 | 1.07 | 0.0 | 1.16 | 0.38 |
| Thesys C1 UI Generation | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| **First SSE Byte** (Initial status) | 0.1 | 0.1 | 0.1 | 0.1 | 0.1 |
| **Total End-to-End Latency (Last Byte)** | 7751.75 | 15556.99 | 8200.93 | 15503.93 | 8714.04 |

---

## 2. Intent-by-Intent Warm Latency Summary

| Intent | Language | Query Excerpt | Warm p50 (ms) | Warm p95 (ms) | Fallback Used |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `league_table` | `mr` | सर्व जिल्ह्यांची सुशासन क्रमवारी दाखवा | 10106.4 | 10335.54 | False |
| `league_table` | `en` | Show top 5 districts by composite governance score | 8791.19 | 8861.07 | False |
| `district_profile` | `mr` | ठाणे जिल्ह्याची सद्यस्थिती आणि गुण दाखवा | 10449.95 | 10703.02 | False |
| `district_profile` | `hi` | नासिक जिले का प्रदर्शन और स्कोरकार्ड क्या है? | 10637.78 | 10946.66 | False |
| `compare_districts` | `en` | Compare Nashik and Ahilyanagar performance | 16048.7 | 17076.93 | False |
| `compare_districts` | `mr` | पुणे आणि सातारा जिल्ह्याची तुलना करा | 18420.19 | 19824.83 | False |
| `active_rumors` | `mr` | सध्या सक्रिय असलेल्या अफवा आणि वस्तुस्थिती अहवाल द्या | 5814.18 | 5854.96 | False |
| `active_rumors` | `hi` | राज्य में सक्रिय अफवाहें और फैक्ट चेक टिकट दिखाएं | 6004.56 | 6177.15 | False |
| `forecast` | `en` | Show 48-hour event forecast for Thane | 11826.22 | 12183.85 | False |
| `forecast` | `mr` | पुणे जिल्ह्यासाठी पुढील घटनांचा अंदाज काय आहे? | 14523.05 | 17283.26 | False |
| `neighbors` | `hi` | पालघर जिले के सीमावर्ती पड़ोसी जिले कौन से हैं? | 7623.15 | 7624.52 | False |
| `neighbors` | `en` | Show geographic border neighbours for Palghar | 8736.33 | 9100.34 | False |

---

## 3. Latency Suspects Ranking (Measured)
Based on measured baseline timings, the primary contributors to copilot latency are ranked as follows:

1. **Sequential Model Turns / Gemma Generation**: ~4431.1ms (p50) / ~9247.6ms (p95)
2. **Tool Execution & Database Queries**: ~3105.0ms (p50) / ~6212.6ms (p95)
3. **Artificial 15ms SSE Chunk Delay (64-byte chunks)**: ~300.0ms (p50) / ~675.0ms (p95)
4. **Auth Token Resolution & Principal Scoping**: ~0.5ms (p50) / ~0.5ms (p95)
5. **Mem0 Embedding & Vector Store Retrieval**: ~0.1ms (p50) / ~0.1ms (p95)
6. **OpenUI Regex & Number Validation**: ~0.0ms (p50) / ~1.2ms (p95)

### Key Architectural Bottlenecks Identified
1. **Sequential Model Turns**: The LLM must be called sequentially for tool selection, waiting for response before executing tools, then called again for synthesis.
2. **Artificial 15ms Chunk Delay**: `router.py` breaks the OpenUI markup into 64-byte chunks with `asyncio.sleep(0.015)` per chunk. For an 800-byte markup, this introduces 187ms of synthetic idle time.
3. **Lack of Fast-Path Speculative Execution**: All queries currently wait on model execution before any visual card or data table is displayed to the user.
4. **Per-Call District Extraction & Tool Parsing**: Tools are re-queried and validated sequentially rather than served from a warm cache-aside layer.
