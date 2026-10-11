# SAVI Intelligence: Browser Extension Guide

The **SAVI Browser Extension** brings the full analytical power of the SAVI Intelligence Platform directly into your web browser using Google's official **Manifest V3 Chrome Side Panel Framework** (`chrome.sidePanel` and `chrome.storage.session`).

When reading any news article, financial dispatch, or research piece, you can trigger deep structural verification, Open-Jev System 1 evaluation, and the **Nous Hermes Autonomous Agent (with Google Gemma 4 grounding)** with a single click while keeping the analytical panel persistently docked beside the reading view.

---

## 🚀 Architectural Features (Google Side Panel Framework)

1. **Persistent Chrome Side Panel (`chrome.sidePanel`):**
   - Built on Google's official `chrome-extensions-samples` architecture (`sample.sidepanel-dictionary`, `cookbook.sidepanel-open`, `ai.gemini-in-the-cloud`).
   - Automatically opens in Chrome's native docked Side Panel when clicking the extension toolbar icon (`chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true })`).
   - Stays open alongside the article as you scroll, read, and browse related tabs.

2. **Nous Hermes Autonomous Agent (Google Gemma 4 Grounding):**
   - Toggleable directly in the Side Panel header.
   - Executes multi-step ReAct autonomous loops (Search $\to$ Graph $\to$ Logic $\to$ Verify) to investigate breaking news and contentious claims.
   - Shows live investigative trajectories and step-by-step audit traces in the Side Panel.

3. **Context Menu & Highlighted Claim Auditing:**
   - Select any claim in an article, right-click, and select **"⚡ Verify Highlighted Claim with SAVI"**.
   - Background service worker leverages `chrome.storage.session` to transmit data instantly without disk I/O, auto-opening the Side Panel with the target claim loaded.

4. **Floating On-Page Trigger & Inline HUD:**
   - Detects news and article pages (Reuters, Bloomberg, BBC, NYT, Substack, etc.).
   - Provides a floating action button on the bottom-right of the page to toggle the side panel or open an on-page slide drawer.

5. **Full SAVI Intelligence Matrix:**
   - **Trust Score Gauge (0-100%):** Real-time composite credibility rating.
   - **SAVI Quad Matrix:** $S_{\text{dyn}}$ (Sentiment), $A_{\text{score}}$ (Factual Accuracy), $V_{\text{index}}$ (Logical Validation), $I_{\text{impact}}$ (News Impact).
   - **Open-Jev System 1 Head:** High-throughput discrete decision choice ($C_{\text{target}}$), astroturf manipulation probability ($Noul$), and evidentiary rigor score ($Score$).
   - **Isolation Rainforest:** Anomaly hyperplane detection ($s(x, n)$) with `PASS_ORGANIC`, `FLAG_ELEVATED`, or `QUARANTINE` actions.
   - **Knowledge Triplets:** Extracted entities and formal logic relationship audit.

6. **VPS Server Switching & Sub-10ms CQRS Querying:**
   - Configure the target VPS URL via the ⚙️ settings drawer (`http://localhost:8000` or production VPS `https://savi.yourdomain.com`).
   - Live health probe with status pill (🟢 VPS Online / 🔴 VPS Offline).

---

## 📦 How to Install (Google Chrome, Edge, Brave, Chromium)

1. Open your browser and navigate to extensions management:
   - **Google Chrome:** `chrome://extensions/`
   - **Microsoft Edge:** `edge://extensions/`
   - **Brave Browser:** `brave://extensions/`
2. Enable **Developer mode** (toggle in the top-right corner).
3. Click the **Load unpacked** button.
4. Select the directory:
   ```text
   c:\Users\Priyanshu Patil\Documents\program01\savi\extension
   ```
5. The extension **"SAVI Intelligence: News Verification & Credibility"** is now installed!
6. Pin the extension to your browser toolbar.
7. Click the extension icon on any news tab: the **SAVI Side Panel** will slide open on the right edge of your browser window.

---

## 🦊 How to Install (Firefox)

1. Open Firefox and navigate to `about:debugging#/runtime/this-firefox`.
2. Click **Load Temporary Add-on...**
3. Select `extension/manifest.json`.

---

## ⚙️ Configuration

1. Open the SAVI Side Panel or click the extension icon.
2. Click the ⚙️ gear icon in the top-right corner.
3. Enter your SAVI VPS URL:
   - Local development: `http://localhost:8000`
   - Remote production VPS: `https://savi.your-vps.com`
4. Click **Save**.
5. The status indicator will turn 🟢 **VPS Online**.
