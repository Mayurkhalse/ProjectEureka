# Project EUREKA — Persistent Cloudflare Tunnel Production Architecture

This guide establishes a permanent, production-ready Cloudflare Tunnel for Project EUREKA and SAVI. It replaces ephemeral quick tunnels (`*.trycloudflare.com`) with a persistent, named Zero Trust tunnel bound to a static subdomain (e.g. `api.yourdomain.com`).

---

## 1. Why a Persistent Named Tunnel?

| Aspect | Ephemeral Quick Tunnel (`trycloudflare.com`) | Persistent Named Tunnel (Zero Trust) |
| :--- | :--- | :--- |
| **URL Stability** | Random URL generated on every boot | **Fixed, unchanging custom domain** (e.g. `api.yourdomain.com`) |
| **Vercel Integration** | Breaks every restart; requires manual updating in Vercel settings | **Set `BACKEND_URL` once in Vercel**, works permanently |
| **Reconnection** | Generates a new URL upon network drop or machine reboot | **Automatically reconnects** and resumes traffic silently |
| **Access Control** | Open to public (anyone with the URL) | Can enforce Cloudflare Zero Trust Access policies (SSO, IP whitelisting) |
| **Cost** | Free | **100% Free** (included with any free Cloudflare account) |

---

## 2. Architecture Diagram

```
+----------------------------------------------------------------------------------------------------+
|                         PERSISTENT CLOUDFLARE TUNNEL ARCHITECTURE                                  |
+----------------------------------------------------------------------------------------------------+
|                                                                                                    |
|  [Vercel Serverless Edge Runtime]                                                                  |
|  • Frontend: https://project-eureka-pi.vercel.app                                                  |
|  • Reverse Proxy Route: /api/v1/copilot/[...path]                                                |
|  • Environment Variable: BACKEND_URL=https://api.yourdomain.com (FIXED FOREVER)                    |
|            │                                                                                       |
|            ▼ (Outbound HTTPS over TLS 1.3 to Fixed Hostname)                                      |
|  [Cloudflare Anycast Global Network]                                                               |
|  • Custom Hostname: https://api.yourdomain.com                                                     |
|  • DDoS Protection, WAF, Rate Limiting, HTTP/2 & HTTP/3 multiplexing                               |
|            │                                                                                       |
|            ▼ (Outbound-only Encrypted Tunnel / No Inbound Ports Required)                          |
|  [Local PC / VPS Host: Cloudflared Daemon]                                                         |
|  • Process: cloudflared tunnel run --token <TUNNEL_TOKEN>                                          |
|            │                                                                                       |
|            ▼ (Internal Loopback HTTP)                                                              |
|  [FastAPI Backend Application Engine]                                                              |
|  • Uvicorn: http://127.0.0.1:8000                                                                  |
|  • Endpoints: /api/v1/copilot, /api/v1/districts, /api/v1/health, etc.                             |
+----------------------------------------------------------------------------------------------------+
```

---

## 3. Step-by-Step Setup: Cloudflare Zero Trust Dashboard (Recommended)

This takes approximately **2 minutes** in the Cloudflare Dashboard and requires zero manual DNS editing.

### Step 1: Open Cloudflare Zero Trust
1. Log in to your [Cloudflare Dashboard](https://dash.cloudflare.com/).
2. On the left sidebar, click **Zero Trust**. (If prompted for a plan, select the **Free** tier).

### Step 2: Create a Cloudflare Tunnel
1. Inside the Zero Trust dashboard, go to **Networks** > **Tunnels**.
2. Click **Add a tunnel**.
3. Select **Cloudflared** as the connector type and click **Next**.
4. Name the tunnel: `eureka-backend-tunnel` and click **Save tunnel**.

### Step 3: Copy Your Tunnel Token
Under **Install and run a connector**, select your operating system (e.g., **Windows** or **Docker**). Cloudflare will present a command containing your token:
```text
cloudflared.exe service install eyJhIjoiYmE5...<your_unique_tunnel_token>...
```
Copy just the long token string starting with `eyJh...`.

### Step 4: Configure the Public Hostname
Click **Next** to navigate to the **Public Hostnames** tab:
* **Subdomain:** `api` (or `eureka-api`)
* **Domain:** Select your domain from the dropdown (e.g., `yourdomain.com`).
* **Path:** Leave empty.
* **Service Type:** `HTTP`
* **URL:** `127.0.0.1:8000` (or `localhost:8000`)

Under **Additional application settings** > **HTTP Settings**:
* Enable **HTTP2 origin** (improves SSE streaming throughput).
* Enable **No TLS Verify** (since local origin is plaintext HTTP).

Click **Save tunnel**.

---

## 4. Running the Tunnel

Once created, you can run the tunnel using any of the following methods:

### Method 1: Using the Repository Helper Script (Windows / macOS / Linux)

Add your token to `.env` or `backend/.env`:
```bash
CLOUDFLARE_TUNNEL_TOKEN=eyJhIjoiYmE5...your_token_here...
```

Run the launcher script:
```powershell
python scripts/run_cloudflare_tunnel.py
```
* The script automatically verifies that your local FastAPI backend on port 8000 is listening, detects `npx cloudflared` or installed `cloudflared`, and launches the tunnel.

### Method 2: Running Directly via NPX (Zero Installation)
```powershell
npx cloudflared tunnel --no-autoupdate run --token <YOUR_TUNNEL_TOKEN>
```

### Method 3: Running via Docker on a VPS (`docker-compose.tunnel.yml`)
If running on a VPS alongside Docker:
```bash
# 1. Export token in environment
export CLOUDFLARE_TUNNEL_TOKEN="eyJhIjoiYmE5...your_token..."

# 2. Launch the containerized tunnel
docker compose -f deploy/cloudflare/docker-compose.tunnel.yml up -d

# 3. View live tunnel status
docker compose -f deploy/cloudflare/docker-compose.tunnel.yml logs -f
```

### Method 4: Installing as a Background Windows Service (Auto-Start on Boot)
If running on a dedicated local server/PC:
```powershell
# Run from an Administrator PowerShell prompt:
npx cloudflared service install <YOUR_TUNNEL_TOKEN>
```
* Cloudflared registers as a native Windows service that starts automatically whenever Windows boots, with zero open console windows.

---

## 5. Connecting Frontend & Vercel Deployment

Once your tunnel is running on your domain (e.g. `https://api.yourdomain.com`):

### In Vercel Project Settings:
1. Open your project on Vercel (`https://vercel.com/dashboard`).
2. Go to **Settings** > **Environment Variables**.
3. Set or update:
   * **Key:** `BACKEND_URL`
   * **Value:** `https://api.yourdomain.com` (use your actual hostname, without trailing slash)
   * **Environments:** Production, Preview, Development.
4. Redeploy the latest commit or trigger a new build.

### In Local Frontend (`frontend/MCC/.env.local`):
```env
BACKEND_URL=https://api.yourdomain.com
# Or keep localhost for local debugging:
# BACKEND_URL=http://127.0.0.1:8000
```

---

## 6. Verification & Health Audits

1. **Verify Cloudflare Edge Connectivity:**
   ```powershell
   curl https://api.yourdomain.com/api/v1/health
   ```
   **Expected Response:**
   ```json
   {"status":"healthy","database":"healthy","timestamp":"2026-10-26T..."}
   ```

2. **Verify SSE Streaming Copilot:**
   ```powershell
   curl -N https://api.yourdomain.com/api/v1/copilot/query -X POST -H "Content-Type: application/json" -d '{"query":"Show Thane district score"}'
   ```
   Chunks will stream immediately over HTTP/2.
