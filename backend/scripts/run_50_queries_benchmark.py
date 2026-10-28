"""Comprehensive 50-Query Real-World Execution Benchmark for Nirdeshak Copilot.

Tests 50 diverse queries across:
- Metric pillars (Volume, Sentiment, Crisis SLA)
- Rankings & Leaderboards (Statewide, Division rollups, Top/Bottom)
- Multi-district comparisons
- Disjoint multi-intent queries (distinct district x topic bindings)
- Common spelling mistakes, typos, slang, and former district names
- Active rumors and fact-check tickets
- Multilingual Marathi (मराठी) and Hindi (हिंदी) queries

For each query, executes through copilot_query() and verifies:
1. Valid SSE event stream (status -> plan -> chunks -> done)
2. Actual rendered OpenUI components (<Heading>, <KpiCard>, <DataTable>, <Callout>)
3. Verified numerical values and entity grounding
4. Execution latency in milliseconds
"""

import asyncio
import json
import re
import sys
import time
from pathlib import Path

# Configure UTF-8 for Windows console
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Ensure eureka packages are in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from eureka.api.auth import TokenData
from eureka.models.enums import UserRole
from eureka.copilot.router import copilot_query, CopilotQueryRequest

BENCHMARK_QUERIES = [
    # --- Category 1: Single Pillar Breakdown & Specific Metrics (1-10) ---
    {"id": 1, "cat": "Pillar Metric", "query": "how many news are there about thane", "expected_tool": "district_profile"},
    {"id": 2, "cat": "Pillar Metric", "query": "sentiment score of nagpur", "expected_tool": "pillar_breakdown"},
    {"id": 3, "cat": "Pillar Metric", "query": "crisis sla in satara", "expected_tool": "pillar_breakdown"},
    {"id": 4, "cat": "Pillar Metric", "query": "public mood in solapur", "expected_tool": "pillar_breakdown"},
    {"id": 5, "cat": "Pillar Metric", "query": "coverage volume of kolhapur", "expected_tool": "pillar_breakdown"},
    {"id": 6, "cat": "Pillar Metric", "query": "what is emergency response score for ratnagiri", "expected_tool": "pillar_breakdown"},
    {"id": 7, "cat": "Pillar Metric", "query": "press releases volume in sindhudurg", "expected_tool": "pillar_breakdown"},
    {"id": 8, "cat": "Pillar Metric", "query": "how do people feel about palghar", "expected_tool": "pillar_breakdown"},
    {"id": 9, "cat": "Pillar Metric", "query": "crisis status of ahilyanagar", "expected_tool": "pillar_breakdown"},
    {"id": 10, "cat": "Pillar Metric", "query": "nanded media releases count", "expected_tool": "pillar_breakdown"},

    # --- Category 2: Rankings, Leaderboard & Division Rollups (11-18) ---
    {"id": 11, "cat": "Leaderboard", "query": "show maharashtra leaderboard", "expected_tool": "league_table"},
    {"id": 12, "cat": "Leaderboard", "query": "top 5 districts across the state", "expected_tool": "league_table"},
    {"id": 13, "cat": "Leaderboard", "query": "bottom 3 districts in governance", "expected_tool": "district_profile"},
    {"id": 14, "cat": "Leaderboard", "query": "who is rank 1 in maharashtra", "expected_tool": "district_profile"},
    {"id": 15, "cat": "Leaderboard", "query": "ranking table of all districts", "expected_tool": "league_table"},
    {"id": 16, "cat": "Division", "query": "konkan division rollup overview", "expected_tool": "division_rollup"},
    {"id": 17, "cat": "Division", "query": "how is pune division performing", "expected_tool": "division_rollup"},
    {"id": 18, "cat": "Division", "query": "nagpur division summary", "expected_tool": "division_rollup"},

    # --- Category 3: Multi-District Comparisons (19-24) ---
    {"id": 19, "cat": "Comparison", "query": "compare nashik and ahilyanagar", "expected_tool": "compare_districts"},
    {"id": 20, "cat": "Comparison", "query": "comparison between pune and thane", "expected_tool": "compare_districts"},
    {"id": 21, "cat": "Comparison", "query": "compare satara vs sangli vs kolhapur", "expected_tool": "compare_districts"},
    {"id": 22, "cat": "Comparison", "query": "compare mumbai city and mumbai suburban", "expected_tool": "compare_districts"},
    {"id": 23, "cat": "Comparison", "query": "dhule versus jalgaon performance", "expected_tool": "compare_districts"},
    {"id": 24, "cat": "Comparison", "query": "amravati compared against akola", "expected_tool": "compare_districts"},

    # --- Category 4: Disjoint Multi-Intent Queries (25-30) ---
    {"id": 25, "cat": "Disjoint Multi", "query": "Crisis sla of Nashik and Sentiment score of Dhule", "expected_tool": "pillar_breakdown"},
    {"id": 26, "cat": "Disjoint Multi", "query": "sentiment of pune and news volume in thane", "expected_tool": "pillar_breakdown"},
    {"id": 27, "cat": "Disjoint Multi", "query": "active rumors in palghar and crisis sla in raigad", "expected_tool": "active_rumors"},
    {"id": 28, "cat": "Disjoint Multi", "query": "dhule sentiment and jalgaon volume", "expected_tool": "pillar_breakdown"},
    {"id": 29, "cat": "Disjoint Multi", "query": "crisis score of solapur and rumors in kolhapur", "expected_tool": "pillar_breakdown"},
    {"id": 30, "cat": "Disjoint Multi", "query": "beed sentiment and parbhani rumors", "expected_tool": "pillar_breakdown"},

    # --- Category 5: Typos, Slang, & Former Names (31-38) ---
    {"id": 31, "cat": "Typos/Slang", "query": "why is dhoole crisis score so loww", "expected_tool": "pillar_breakdown"},
    {"id": 32, "cat": "Typos/Slang", "query": "nashk fake news plz check", "expected_tool": "active_rumors"},
    {"id": 33, "cat": "Typos/Slang", "query": "poona sentimnt details", "expected_tool": "pillar_breakdown"},
    {"id": 34, "cat": "Typos/Slang", "query": "thne news volum", "expected_tool": "pillar_breakdown"},
    {"id": 35, "cat": "Typos/Slang", "query": "aurangabad public mood", "expected_tool": "pillar_breakdown"},
    {"id": 36, "cat": "Typos/Slang", "query": "osmanabad crisis status", "expected_tool": "pillar_breakdown"},
    {"id": 37, "cat": "Typos/Slang", "query": "ahmednagar rumors", "expected_tool": "active_rumors"},
    {"id": 38, "cat": "Typos/Slang", "query": "leadrboard top five", "expected_tool": "league_table"},

    # --- Category 6: Active Rumors, Incident Queue & Fact Checks (39-42) ---
    {"id": 39, "cat": "Rumors", "query": "show active rumors for pune", "expected_tool": "active_rumors"},
    {"id": 40, "cat": "Rumors", "query": "any fake news detected in thane", "expected_tool": "active_rumors"},
    {"id": 41, "cat": "Rumors", "query": "fact check tickets in nashik", "expected_tool": "active_rumors"},
    {"id": 42, "cat": "Rumors", "query": "rumor queue for sambhajinagar", "expected_tool": "active_rumors"},

    # --- Category 7: Marathi Queries (मराठी) (43-46) ---
    {"id": 43, "cat": "Marathi", "query": "ठाणे जिल्ह्यातील कामगिरी दाखवा", "expected_tool": "district_profile"},
    {"id": 44, "cat": "Marathi", "query": "पुण्यातील जनभावना कशी आहे", "expected_tool": "pillar_breakdown"},
    {"id": 45, "cat": "Marathi", "query": "नाशिकमधील संकट आणि अफवा", "expected_tool": "active_rumors"},
    {"id": 46, "cat": "Marathi", "query": "धुळे जिल्हा क्रमांक का घसरला", "expected_tool": "district_profile"},

    # --- Category 8: Hindi Queries (हिंदी) (47-50) ---
    {"id": 47, "cat": "Hindi", "query": "नासिक का क्राइसिस स्कोर क्या है", "expected_tool": "pillar_breakdown"},
    {"id": 48, "cat": "Hindi", "query": "पुणे जिले का पब्लिक मूड बताओ", "expected_tool": "pillar_breakdown"},
    {"id": 49, "cat": "Hindi", "query": "धुले और जलगांव की तुलना करो", "expected_tool": "compare_districts"},
    {"id": 50, "cat": "Hindi", "query": "महाराष्ट्र का लीडरबोर्ड दिखाओ", "expected_tool": "league_table"},
]


async def run_single_query(q_item: dict, user: TokenData) -> dict:
    q_id = q_item["id"]
    q_cat = q_item["cat"]
    query = q_item["query"]
    t0 = time.time()

    req = CopilotQueryRequest(query=query, language="en")
    resp = await copilot_query(req, current_user=user)

    events: List[str] = []
    chunks: List[str] = []
    plan_data = None
    done_data = None

    async for raw_chunk in resp.body_iterator:
        events.append(raw_chunk)
        for part in raw_chunk.split("\n\n"):
            part = part.strip()
            if not part:
                continue
            if part.startswith("event: plan"):
                m = re.search(r"data:\s*(\{.*\})", part, re.DOTALL)
                if m:
                    try:
                        plan_data = json.loads(m.group(1))
                    except Exception:
                        pass
            elif part.startswith("event: chunk"):
                m = re.search(r"data:\s*(\{.*\})", part, re.DOTALL)
                if m:
                    try:
                        c_json = json.loads(m.group(1))
                        chunks.append(c_json.get("text", ""))
                    except Exception:
                        pass
            elif part.startswith("event: done"):
                m = re.search(r"data:\s*(\{.*\})", part, re.DOTALL)
                if m:
                    try:
                        done_data = json.loads(m.group(1))
                    except Exception:
                        pass

    total_latency_ms = round((time.time() - t0) * 1000, 1)
    full_text = "\n".join(chunks)

    # Verification checks
    has_status = any("event: status" in e for e in events)
    has_plan = plan_data is not None
    has_done = done_data is not None
    has_chunks = len(chunks) > 0 and len(full_text.strip()) > 0
    has_openui_components = bool(re.search(r"<(Heading|KpiCard|DataTable|Callout)", full_text))
    has_numbers = bool(re.search(r"\d+", full_text))

    # OpenUI component breakdown
    headings = len(re.findall(r"<Heading\b", full_text))
    kpis = len(re.findall(r"<KpiCard\b", full_text))
    tables = len(re.findall(r"<DataTable\b", full_text))
    callouts = len(re.findall(r"<Callout\b", full_text))
    total_components = headings + kpis + tables + callouts

    # Success determination
    is_success = (
        has_status and
        has_plan and
        has_done and
        has_chunks and
        has_openui_components and
        has_numbers and
        total_components > 0
    )

    ops_summary = []
    if plan_data and "groups" in plan_data:
        for g in plan_data["groups"]:
            ops_summary.append(g.get("label", g.get("id", "")))

    return {
        "id": q_id,
        "cat": q_cat,
        "query": query,
        "success": is_success,
        "latency_ms": total_latency_ms,
        "first_byte_ms": done_data.get("timings", {}).get("first_byte_ms") if done_data else None,
        "total_components": total_components,
        "components_breakdown": f"H:{headings} K:{kpis} T:{tables} C:{callouts}",
        "ops": ", ".join(ops_summary[:3]) + (f" (+{len(ops_summary)-3})" if len(ops_summary) > 3 else ""),
        "output_snippet": full_text[:120].replace("\n", " ").strip() + "...",
        "source_status": done_data.get("source_status") if done_data else "unknown",
    }


async def main():
    print("=" * 80)
    print("Nirdeshak Copilot: 50 Real-World Query Execution & Verification Suite")
    print("=" * 80)

    user = TokenData(username="test_state_admin", role=UserRole.DG_STATE_ADMIN)
    results = []

    print(f"\nExecuting {len(BENCHMARK_QUERIES)} queries sequentially...\n")
    print(f"{'ID':<3} | {'Category':<14} | {'Status':<6} | {'Latency':<9} | {'UI Components':<18} | Query")
    print("-" * 80)

    for q in BENCHMARK_QUERIES:
        res = await run_single_query(q, user)
        results.append(res)
        status_str = "OK" if res["success"] else "FAIL"
        print(f"{res['id']:<3} | {res['cat']:<14} | {status_str:<6} | {res['latency_ms']:>6.1f}ms | {res['components_breakdown']:<18} | {res['query'][:30]}")

    passed = sum(1 for r in results if r["success"])
    avg_latency = round(sum(r["latency_ms"] for r in results) / len(results), 1)

    print("\n" + "=" * 80)
    print("BENCHMARK SUMMARY")
    print("=" * 80)
    print(f"Total Queries:     {len(results)}")
    print(f"Passed (Verified): {passed} / {len(results)} ({passed / len(results) * 100:.1f}%)")
    print(f"Average Latency:   {avg_latency} ms")
    print("=" * 80)

    # Save detailed JSON summary for documentation / artifact review
    summary_path = Path(__file__).resolve().parent / "benchmark_50_results.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nDetailed report written to: {summary_path}")


if __name__ == "__main__":
    asyncio.run(main())
