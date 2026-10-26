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


4. **Cloudflare Backend Persistent Domain & Ingress Finalization**:
   - The Cloudflare Zero Trust named tunnel (eureka-backend, ID 9d8b1584-4581-49f6-ae5a-5ad8255868f3) is provisioned and connects via token authentication in scripts/run_cloudflare_tunnel.py and deploy/cloudflare/.
   - Pending action for future discussion: Associate a registered public Top-Level Domain (e.g., eureka-mcc.com, eureka.gov.in, or a free static domain) in Cloudflare Zero Trust > Tunnels > eureka-backend > Routes (currently mapped to pi.eureka-mcc).
   - Once a public domain is finalized, set BACKEND_URL=https://api.<domain> in Vercel project settings so Vercel edge routes route to the live backend permanently without manual URL rotation.
