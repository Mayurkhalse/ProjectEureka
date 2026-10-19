# Project EUREKA — Maha-Command Center (MCC) Frontend

The frontend for Project EUREKA is located in `frontend/MCC`.

### Overview
- **Framework**: Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS, Zustand
- **Design Standard**: GIGW 3.0 (Guidelines for Indian Government Websites) and UX4G compliance
- **Backend Bridge**: `frontend/MCC/src/lib/backendClient.ts` proxies live operational requests to the FastAPI backend (`http://127.0.0.1:8000`)
- **Authentication**: Role-Based Access Control (RBAC) with 12-hour TTL cryptographically signed JWT cookies and bearer tokens

### Getting Started
```bash
cd frontend/MCC
npm install
npm run build
npm start
```
