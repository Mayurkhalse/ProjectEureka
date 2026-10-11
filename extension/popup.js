/**
 * SAVI Intelligence Extension - Popup Controller
 * Connects active browser tab with SAVI VPS Backend (/api/v1/extension/analyze).
 */

const DEFAULT_SERVER_URL = "http://localhost:8000";

let currentArticleData = {
  url: "",
  title: "",
  raw_text: "",
  selected_text: "",
  author: "",
  domain: ""
};

document.addEventListener("DOMContentLoaded", async () => {
  const serverUrlInput = document.getElementById("serverUrlInput");
  const saveServerBtn = document.getElementById("saveServerBtn");
  const toggleSettingsBtn = document.getElementById("toggleSettingsBtn");
  const openSidePanelBtn = document.getElementById("openSidePanelBtn");
  const settingsDrawer = document.getElementById("settingsDrawer");
  const analyzeBtn = document.getElementById("analyzeBtn");
  const retryBtn = document.getElementById("retryBtn");

  if (openSidePanelBtn) {
    openSidePanelBtn.addEventListener("click", async () => {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (tab && chrome.sidePanel && chrome.sidePanel.open) {
        chrome.sidePanel.open({ tabId: tab.id });
        window.close();
      }
    });
  }

  // Load configured VPS server URL
  const stored = await chrome.storage.local.get(["saviServerUrl"]);
  const serverUrl = stored.saviServerUrl || DEFAULT_SERVER_URL;
  serverUrlInput.value = serverUrl;

  // Check VPS connection
  checkVpsHealth(serverUrl);

  // Toggle settings drawer
  toggleSettingsBtn.addEventListener("click", () => {
    settingsDrawer.classList.toggle("hidden");
  });

  // Save server URL
  saveServerBtn.addEventListener("click", async () => {
    let url = serverUrlInput.value.trim().replace(/\/+$/, "");
    if (!url.startsWith("http://") && !url.startsWith("https://")) {
      url = "http://" + url;
    }
    await chrome.storage.local.set({ saviServerUrl: url });
    settingsDrawer.classList.add("hidden");
    checkVpsHealth(url);
  });

  // Extract content from active tab
  await extractActiveTabContent();

  // Audit triggers
  analyzeBtn.addEventListener("click", () => triggerAnalysis(serverUrl));
  retryBtn.addEventListener("click", () => triggerAnalysis(serverUrl));
});

/**
 * Checks connection health to SAVI VPS backend.
 */
async function checkVpsHealth(serverUrl) {
  const pill = document.getElementById("vpsStatus");
  const text = document.getElementById("vpsStatusText");
  pill.className = "status-pill status-checking";
  text.textContent = "Connecting";

  try {
    const res = await fetch(`${serverUrl}/health`, { method: "GET" });
    if (res.ok) {
      const data = await res.json();
      pill.className = "status-pill status-online";
      text.textContent = "VPS Online";
      pill.title = `Connected to SAVI: ${data.service || "Online"} (Uptime: ${Math.round(data.uptime_seconds || 0)}s)`;
    } else {
      throw new Error(`HTTP ${res.status}`);
    }
  } catch (err) {
    pill.className = "status-pill status-offline";
    text.textContent = "VPS Offline";
    pill.title = `Cannot reach ${serverUrl}. Click ⚙️ to configure VPS host URL.`;
  }
}

/**
 * Extracts headline, domain, article body, and highlighted text from active tab.
 */
async function extractActiveTabContent() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab || !tab.url) {
    document.getElementById("articleTitle").textContent = "No active web page detected.";
    return;
  }

  currentArticleData.url = tab.url;
  currentArticleData.title = tab.title || "";
  try {
    currentArticleData.domain = new URL(tab.url).hostname.replace(/^www\./, "");
  } catch {
    currentArticleData.domain = "web";
  }

  // Update popup view
  document.getElementById("articleDomain").textContent = currentArticleData.domain;
  document.getElementById("articleTitle").textContent = currentArticleData.title || tab.url;

  // Run content script snippet to extract text & selection
  try {
    const results = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => {
        const selection = window.getSelection() ? window.getSelection().toString().trim() : "";
        let articleBody = "";
        const articleEl = document.querySelector("article") || document.querySelector("main") || document.querySelector(".article-body");
        if (articleEl) {
          articleBody = articleEl.innerText.trim();
        } else {
          const paragraphs = Array.from(document.querySelectorAll("p"))
            .map(p => p.innerText.trim())
            .filter(t => t.length > 40);
          articleBody = paragraphs.slice(0, 15).join("\n\n");
        }

        let author = "";
        const authorMeta = document.querySelector('meta[name="author"]') || document.querySelector('meta[property="article:author"]');
        if (authorMeta) author = authorMeta.content;

        return {
          selection,
          body: articleBody.slice(0, 4000),
          author
        };
      }
    });

    if (results && results[0] && results[0].result) {
      const res = results[0].result;
      currentArticleData.raw_text = res.body;
      currentArticleData.selected_text = res.selection;
      currentArticleData.author = res.author;

      if (res.selection && res.selection.length > 10) {
        document.getElementById("selectionNotice").classList.remove("hidden");
        document.getElementById("articleExcerpt").textContent = `Selected Claim: "${res.selection.slice(0, 120)}..."`;
        document.getElementById("btnText").textContent = "Audit Highlighted Claim";
      } else if (res.body) {
        document.getElementById("articleExcerpt").textContent = res.body.slice(0, 130) + "...";
      }
    }
  } catch (err) {
    console.warn("DOM extraction limited on this tab:", err);
  }
}

/**
 * Triggers analysis request to SAVI VPS backend.
 */
async function triggerAnalysis(serverUrl) {
  const loading = document.getElementById("loadingState");
  const errorBox = document.getElementById("errorState");
  const resultsPanel = document.getElementById("resultsPanel");
  const analyzeBtn = document.getElementById("analyzeBtn");

  loading.classList.remove("hidden");
  errorBox.classList.add("hidden");
  resultsPanel.classList.add("hidden");
  analyzeBtn.disabled = true;

  try {
    const response = await fetch(`${serverUrl}/api/v1/extension/analyze`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        url: currentArticleData.url,
        title: currentArticleData.title,
        raw_text: currentArticleData.raw_text,
        selected_text: currentArticleData.selected_text,
        author: currentArticleData.author,
        domain: currentArticleData.domain,
        use_hermes: document.getElementById("useHermesToggle") ? document.getElementById("useHermesToggle").checked : false,
      })
    });

    if (!response.ok) {
      const errDetail = await response.text();
      throw new Error(`API error ${response.status}: ${errDetail}`);
    }

    const data = await response.json();
    renderAnalysisResults(data);
  } catch (err) {
    console.error("SAVI analysis failed:", err);
    document.getElementById("errorMsg").textContent = `Analysis failed: ${err.message}`;
    errorBox.classList.remove("hidden");
  } finally {
    loading.classList.add("hidden");
    analyzeBtn.disabled = false;
  }
}

/**
 * Populates popup HUD with rich SAVI intelligence.
 */
function renderAnalysisResults(data) {
  const resultsPanel = document.getElementById("resultsPanel");

  // 1. Overall Trust Score & Verdict
  const trustVal = Math.round(data.trust_score || 0);
  document.getElementById("trustScoreVal").textContent = trustVal;
  document.getElementById("trustLabel").textContent = data.trust_label || "Analyzed";

  const verdictBadge = document.getElementById("verdictBadge");
  verdictBadge.textContent = data.overall_verdict || "VERIFIED";
  verdictBadge.className = "verdict-badge";

  if (data.overall_verdict === "VERIFIED_ORGANIC") {
    verdictBadge.classList.add("badge-verified");
  } else if (data.overall_verdict === "CAUTION_FLAGGED") {
    verdictBadge.classList.add("badge-caution");
  } else {
    verdictBadge.classList.add("badge-anomaly");
  }

  // 2. SAVI Quad Metrics
  const m = data.savi_metrics || {};
  document.getElementById("metricS").textContent = (m.sentiment_dynamics ?? 0).toFixed(2);
  document.getElementById("metricA").textContent = `${Math.round((m.factual_accuracy ?? 0) * 100)}%`;
  document.getElementById("metricV").textContent = `${Math.round((m.logical_validation ?? 0) * 100)}%`;
  document.getElementById("metricI").textContent = (m.news_impact_index ?? 0).toFixed(1);

  document.getElementById("barS").style.width = `${Math.min(100, Math.max(10, Math.abs((m.sentiment_dynamics ?? 0) * 100)))}%`;
  document.getElementById("barA").style.width = `${Math.min(100, Math.max(5, (m.factual_accuracy ?? 0) * 100))}%`;
  document.getElementById("barV").style.width = `${Math.min(100, Math.max(5, (m.logical_validation ?? 0) * 100))}%`;
  document.getElementById("barI").style.width = `${Math.min(100, Math.max(10, (m.news_impact_index ?? 0) * 20))}%`;

  // 3. Open-Jev System 1 Head
  const oj = data.open_jev || {};
  const ojEl = document.getElementById("openJevChoice");
  ojEl.textContent = (oj.credibility_choice || "CREDIBLE").replace(/_/g, " ");
  document.getElementById("openJevConfidence").textContent = `Conf: ${Math.round((oj.credibility_confidence || 0) * 100)}%`;
  document.getElementById("openJevReasoning").textContent = oj.reasoning || "System 1 evaluated discrete option distribution.";

  // 4. Rainforest Anomaly
  const an = data.anomaly_detection || {};
  const anEl = document.getElementById("anomalyAction");
  anEl.textContent = an.action || "PASS_ORGANIC";
  document.getElementById("anomalyScore").textContent = `Score: ${(an.anomaly_score ?? 0).toFixed(3)}`;

  if (an.action === "QUARANTINE") {
    anEl.className = "intel-val val-red";
  } else if (an.action === "FLAG_ELEVATED") {
    anEl.className = "intel-val val-amber";
  } else {
    anEl.className = "intel-val val-green";
  }

  // 5. Key Claims List
  const claimsList = document.getElementById("claimsList");
  claimsList.innerHTML = "";

  const claims = data.key_claims || [];
  if (claims.length === 0) {
    claimsList.innerHTML = '<span class="hint">No structured claims extracted.</span>';
  } else {
    claims.forEach(c => {
      const item = document.createElement("div");
      item.className = "claim-item";

      const text = document.createElement("div");
      text.className = "claim-text";
      text.innerHTML = `<strong>${escapeHtml(c.subject)}</strong> <em>${escapeHtml(c.predicate)}</em> ${escapeHtml(c.object)}`;

      const verdict = document.createElement("span");
      const vClass = (c.verdict || "Neutral").toLowerCase();
      verdict.className = `claim-verdict verdict-${vClass}`;
      verdict.textContent = c.verdict || "Verified";

      item.appendChild(text);
      item.appendChild(verdict);
      claimsList.appendChild(item);
    });
  }

  // 5.5. Nous Hermes Autonomous Investigation Trajectory
  const hermesCard = document.getElementById("hermesCard");
  if (data.hermes_investigation && hermesCard) {
    hermesCard.classList.remove("hidden");
    const h = data.hermes_investigation;
    const vElem = document.getElementById("hermesVerdict");
    if (vElem) vElem.textContent = `${h.verdict} (${Math.round((h.confidence_score || 0.85) * 100)}% Confidence)`;
    const sElem = document.getElementById("hermesSummaryText");
    if (sElem) sElem.textContent = h.executive_summary || "";

    const stepsList = document.getElementById("hermesStepsList");
    if (stepsList) {
      stepsList.innerHTML = "";
      if (h.trajectory && h.trajectory.steps) {
        h.trajectory.steps.forEach(st => {
          const item = document.createElement("div");
          item.className = "hermes-step-item";
          item.innerHTML = `<strong>Step ${st.step_index}:</strong> <span>${escapeHtml(st.observation || st.thought)}</span>`;
          stepsList.appendChild(item);
        });
      }
    }
  } else if (hermesCard) {
    hermesCard.classList.add("hidden");
  }

  // 6. Recommendation
  document.getElementById("recommendationText").textContent = data.recommendation || "Verified organic editorial publication.";

  // 7. Latency
  document.getElementById("latencyDisplay").textContent = `⚡ Analyzed in ${(data.processing_latency_ms || 0).toFixed(1)} ms`;

  // Reveal results
  resultsPanel.classList.remove("hidden");
}

function escapeHtml(str) {
  if (!str) return "";
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
