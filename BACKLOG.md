# EUREKA / DGIPR Command Center - Backlog & Environment Notes

### 12 Meeting Changes Status
All 12 meeting changes are **100% complete** on branch `feature/meeting-changes`. No items blocked.

### Environment & Integration Notes
1. **PostgreSQL Test Container (Port 5433)**:
   - Error in full suite: `psycopg2.OperationalError: connection to server at "127.0.0.1", port 5433 failed: Connection refused`.
   - Cause: 7 integration tests in `test_hermes_integration.py` specifically expect a live PostgreSQL 16 instance on port 5433.
   - Solution: Run `docker compose up -d db` when testing Hermes PG outbox pipeline. All 131 unit and demo tests pass cleanly on SQLite fallback.

2. **WebAuthn Biometric Domain Binding**:
   - WebAuthn specification strictly requires HTTPS or `localhost` and domain matching `WEBAUTHN_RP_ID`.
   - Vercel dynamic preview URLs change per commit. For end-to-end device face lock testing, use `localhost:3000` or set `WEBAUTHN_RP_ID` to the stable production domain.

3. **Gemini Live Audio Transcription**:
   - Uses `GEMINI_TRANSCRIBE_MODEL` (`gemini-2.0-flash`) and main `GEMINI_API_KEY`.
   - `DemoProvider` automatically takes over when no key is supplied, ensuring seamless offline functionality.
