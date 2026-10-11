# SAVI Intelligence: Browser Extension Guide

The **SAVI Browser Extension** brings the full analytical power of the SAVI Intelligence Platform directly into your web browser. When reading any news article or research piece, you can trigger deep structural verification, Open-Jev System 1 evaluation, and anomaly detection with a single click.

---

## 🚀 Features

1. **Floating On-Page Trigger ("⚡ SAVI Analyze"):**
   - Automatically detects news and article pages (Reuters, Bloomberg, BBC, NYT, Substack, etc.).
   - Injects a floating action button on the bottom-right of the page.
   - Clicking it triggers instant analysis and slides out an on-page Intelligence HUD drawer without navigating away.

2. **Highlighted Claim Audit:**
   - Select any claim or statement in an article text.
   - A floating "⚡ Verify Claim with SAVI" tooltip appears.
   - Audits that specific claim against the SAVI Knowledge Graph and Open JEV Formal Logic Engine ($p_{\text{entailment}}, p_{\text{contradiction}}$).

3. **Toolbar Extension Popup HUD:**
   - Click the extension icon in your browser toolbar to view the article overview, overall Trust Rating (0-100%), and SAVI Quad Metrics ($S, A, V, I$).
   - Displays Open-Jev System 1 Decision (`Choice`, `Noul`, `Score`) and Isolation Rainforest Anomaly boundaries (`PASS_ORGANIC`, `FLAG_ELEVATED`, `QUARANTINE`).

4. **VPS Server Switching:**
   - Toggle the settings drawer (⚙️) to connect to a local development server (`http://localhost:8000`) or a remote VPS instance (`https://savi.yourdomain.com`).

---

## 📦 How to Install (Chrome, Edge, Brave, Opera)

1. Open your Chromium browser and go to extensions management:
   - **Chrome:** `chrome://extensions/`
   - **Edge:** `edge://extensions/`
   - **Brave:** `brave://extensions/`
2. Enable **Developer mode** (toggle switch in the top-right corner).
3. Click the **Load unpacked** button.
4. Select the directory:
   ```text
   C:\Users\Priyanshu Patil\Documents\program01\savi\extension
   ```
5. The extension **"SAVI Intelligence: News Verification & Credibility"** will now appear in your browser toolbar!
6. Pin the extension to your toolbar for instant access.

---

## 🦊 How to Install (Firefox)

1. Open Firefox and navigate to `about:debugging#/runtime/this-firefox`.
2. Click **Load Temporary Add-on...**
3. Select `extension/manifest.json`.

---

## ⚙️ Configuration

1. Click the SAVI icon in the browser toolbar.
2. Click the ⚙️ gear icon in the top header.
3. Enter your SAVI VPS URL:
   - For local backend: `http://localhost:8000`
   - For VPS production server: `https://savi.your-vps-ip.nip.io` or `https://savi.yourdomain.com`
4. Click **Save**.
5. The status pill will immediately switch to 🟢 **VPS Online**.
