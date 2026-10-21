# Deployment Guide

## Required Environment Variables (Names Only)
- Frontend: `BACKEND_URL`, `JWT_SECRET`, `FASTAPI_JWT_SECRET`
- Backend: `DATABASE_URL`, `NEO4J_URI`, `NEO4J_PASSWORD`, `REDIS_URL`, `GROQ_API_KEY`, `JWT_SECRET_KEY`

## Run Locally
- Backend: `uv run uvicorn eureka.api.main:app --port 8000 --app-dir backend/src`
- Frontend: `cd frontend/MCC && npm run dev`

## Deploy Backend (Container)
1. Build: `docker build -f backend/Dockerfile -t eureka-backend:latest backend`
2. Run: `docker run -p 8000:8000 -e PORT=8000 --env-file backend/.env eureka-backend:latest`

## Deploy Frontend (Vercel)
- Deploy Next.js to Vercel and set `BACKEND_URL` to your container or tunnel URL.

## Demo Tunnel Option
- Expose local backend: `ngrok http 8000` or `cloudflared tunnel --url http://localhost:8000`
- Set Vercel `BACKEND_URL` to the HTTPS tunnel URL (`https://<subdomain>.ngrok-free.app`).
