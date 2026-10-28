import asyncio
import sys
from pathlib import Path

# Configure UTF-8 for Windows console
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from eureka.api.auth import TokenData
from eureka.models.enums import UserRole
from eureka.copilot.router import copilot_query, CopilotQueryRequest

async def main():
    user = TokenData(username="test_state_admin", role=UserRole.DG_STATE_ADMIN)
    test_queries = [
        "who i am",
        "asdfghjkl",
        "tell me a joke",
        "who are you",
    ]

    print("=" * 70)
    print("VERIFYING UNHANDLED / OUT-OF-DOMAIN QUERIES DO NOT RETURN LEADERBOARD")
    print("=" * 70)

    for q in test_queries:
        req = CopilotQueryRequest(query=q, language="en")
        resp = await copilot_query(req, current_user=user)
        chunks = []
        async for chunk in resp.body_iterator:
            if "event: chunk" in chunk:
                chunks.append(chunk.strip())

        print(f"\nQuery: '{q}'")
        has_leaderboard = any("League Table" in c or "DataTable" in c for c in chunks)
        print(f"Contains Leaderboard / Random Data: {has_leaderboard}")
        for c in chunks:
            print(f"Output Chunk: {c}")

if __name__ == "__main__":
    asyncio.run(main())
