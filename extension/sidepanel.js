/**
 * SAVI Intelligence Platform - Chrome Side Panel Controller (Manifest V3)
 * Built with Google Chrome Extension Samples Framework (chrome.sidePanel + chrome.storage.session)
 * Coordinates real-time active tab extraction, VPS health monitoring,
 * SAVI Quad-Agent matrix evaluation, Open-Jev System 1, Isolation Rainforest,
 * and Nous Hermes Autonomous Agent (Gemma-4 grounded) trajectories.
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

let currentServerUrl = DEFAULT_SERVER_URL;

document.addEventListener("DOMContentLoaded", async () => {
  // UI Element References
  const serverUrlInput = document.getElementById("serverUrlInput");
  const saveServerBtn = document.getElementById("saveServerBtn");
  const toggleSettingsBtn = document.getElementById("toggleSettingsBtn");
  const settingsDrawer = document.getElementById("settingsDrawer");
  const analyzeBtn = document.getElementById("analyzeBtn");
  const refreshContextBtn = document.getElementById("refreshContextBtn");
  const retryBtn = document.getElementById("retryBtn");

  // 1. Initialize Server Configuration from chrome.storage.local
  try {
    const stored = await chrome.storage.local.get(["saviServerUrl"]);
    if (stored.saviServerUrl) {
      currentServerUrl = stored.saviServerUrl;
    }
  } catch (e) {
    console.warn("Storage read error:", e);
  }
  serverUrlInput.value = currentServerUrl;

  // 2. Initial VPS Connection Health Check
  checkVpsHealth(currentServerUrl);

  // 3. Settings Drawer Toggles
  toggleSettingsBtn.addEventListener("click", () => {
    settingsDrawer.classList.toggle("hidden");
  });

  saveServerBtn.addEventListener("click", async () => {
    let url = serverUrlInput.value.trim().replace(/\/+$/, "");
    if (!url.startsWith("http://") && !url.startsWith("https://")) {
      url = "http://" + url;
    }
    currentServerUrl = url;
    await chrome.storage.local.set({ saviServerUrl: url });
    settingsDrawer.classList.add("hidden");
    checkVpsHealth(url);
  });

  // 4. Initial Active Tab Inspection & DOM Content Extraction
  await syncActiveTabContext();

  // 5. Check session storage for context menu triggers (from background.js)
  checkSessionStorageTriggers();

  // 6. Action Listeners
  analyzeBtn.addEventListener("click", () => triggerAnalysis(currentServerUrl));
  refreshContextBtn.addEventListener("click", () => syncActiveTabContext());
  retryBtn.addEventListener("click", () => triggerAnalysis(currentServerUrl));

  // 7. Reactive Storage Listener: update dynamically if session storage changes (e.g. user highlights text & clicks menu)
  if (chrome.storage && chrome.storage.session) {
    chrome.storage.session.onChanged.addListener((changes) => {
      if (changes.pendingClaim) {
        const claim = changes.pendingClaim.newValue;
        if (claim && claim.text) {
          applyPendingClaim(claim.text, claim.autoAnalyze);
        }
      }
      if (changes.activeTabUpdated) {
        syncActiveTabContext();
      }
    });
  }

  // 8. Tab Switch & Navigation Listeners to keep Side Panel in sync
  if (chrome.tabs) {
    chrome.tabs.onActivated.addListener(() => {
      syncActiveTabContext();
    });
    chrome.tabs.onUpdated.addListener((tabId, changeInfo) => {
      if (changeInfo.status === "complete") {
        syncActiveTabContext();
      }
    });
  }
});

/**
 * Checks connection health to SAVI VPS backend (/health endpoint).
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
 * Syncs the side panel context with the currently active Chrome tab.
 */
async function syncActiveTabContext() {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !tab.url) {
      document.getElementById("articleTitle").textContent = "No active web page detected.";
      document.getElementById("articleDomain").textContent = "system";
      return;
    }

    // Do not attempt DOM inspection on restricted browser internal URLs
    if (tab.url.startsWith("chrome://") || tab.url.startsWith("edge://") || tab.url.startsWith("about:")) {
      document.getElementById("articleDomain").textContent = "chrome";
      document.getElementById("articleTitle").textContent = tab.title || "Browser Internal Page";
      document.getElementById("articleExcerpt").textContent = "SAVI audits live web articles, news publications, and social media links.";
      return;
    }

    currentArticleData.url = tab.url;
    currentArticleData.title = tab.title || "";
    try {
      currentArticleData.domain = new URL(tab.url).hostname.replace(/^www\./, "");
    } catch {
      currentArticleData.domain = "web";
    }

    document.getElementById("articleDomain").textContent = currentArticleData.domain;
    document.getElementById("articleTitle").textContent = currentArticleData.title || tab.url;

    // Inject content extraction script via chrome.scripting API
    const results = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => {
        const selection = window.getSelection() ? window.getSelection().toString().trim() : "";
        let articleBody = "";
        const articleEl = document.querySelector("article") || document.querySelector("main") || document.querySelector(".article-body") || document.querySelector("#article-content");
        if (articleEl) {
          articleBody = articleEl.innerText.trim();
        } else {
          const paragraphs = Array.from(document.querySelectorAll("p"))
            .map(p => p.innerText.trim())
            .filter(t => t.length > 35);
          articleBody = paragraphs.slice(0, 20).join("\n\n");
        }

        let author = "";
        const authorMeta = document.querySelector('meta[name="author"]') || 
                           document.querySelector('meta[property="article:author"]') ||
                           document.querySelector('meta[name="byl"]');
        if (authorMeta) author = authorMeta.content;

        return {
          selection,
          body: articleBody.slice(0, 4500),
          author
        };
      }
    });

    if (results && results[0] && results[0].result) {
      const res = results[0].result;
      currentArticleData.raw_text = res.body || "";
      currentArticleData.selected_text = res.selection || "";
      currentArticleData.author = res.author || "";

      if (res.selection && res.selection.length > 10) {
        document.getElementById("selectionNotice").classList.remove("hidden");
        document.getElementById("articleExcerpt").textContent = `Selected Claim: "${res.selection.slice(0, 140)}..."`;
        document.getElementById("btnText").textContent = "Audit Highlighted Claim";
      } else if (res.body) {
        document.getElementById("selectionNotice").classList.add("hidden");
        document.getElementById("articleExcerpt").textContent = res.body.slice(0, 160) + "...";
        document.getElementById("btnText").textContent = "Run Full SAVI Audit";
      }
    }
  } catch (err) {
    console.warn("Tab context inspection limited:", err);
  }
}

/**
 * Checks session storage for claims queued from background.js context menus.
 */
async function checkSessionStorageTriggers() {
  if (!chrome.storage || !chrome.storage.session) return;
  try {
    const data = await chrome.storage.session.get(["pendingClaim"]);
    if (data.pendingClaim && data.pendingClaim.text) {
      applyPendingClaim(data.pendingClaim.text, data.pendingClaim.autoAnalyze);
      // Clear pending claim once consumed
      await chrome.storage.session.remove(["pendingClaim"]);
    }
  } catch (e) {
    console.warn("Session storage trigger read error:", e);
  }
}

/**
 * Applies a highlighted claim and optionally launches analysis immediately.
 */
function applyPendingClaim(claimText, autoAnalyze = false) {
  currentArticleData.selected_text = claimText;
  document.getElementById("selectionNotice").classList.remove("hidden");
  document.getElementById("articleExcerpt").textContent = `Selected Claim: "${claimText.slice(0, 140)}..."`;
  document.getElementById("btnText").textContent = "Audit Highlighted Claim";

  if (autoAnalyze) {
    triggerAnalysis(currentServerUrl);
  }
}

/**
 * Sends audit request to SAVI VPS backend (/api/v1/extension/analyze).
 */
async function triggerAnalysis(serverUrl) {
  const loading = document.getElementById("loadingState");
  const errorBox = document.getElementById("errorState");
  const resultsPanel = document.getElementById("resultsPanel");
  const analyzeBtn = document.getElementById("analyzeBtn");
  const useHermes = document.getElementById("useHermesToggle").checked;

  loading.classList.remove("hidden");
  errorBox.classList.add("hidden");
  resultsPanel.classList.add("hidden");
  analyzeBtn.disabled = true;

  const loadingMsg = document.getElementById("loadingMsg");
  if (useHermes) {
    loadingMsg.textContent = "Executing Nous Hermes Autonomous ReAct Agent with Google Gemma 4 grounding...";
  } else {
    loadingMsg.textContent = "Auditing structural knowledge graph & Open-Jev System 1...";
  }

  try {
    const payload = {
      url: currentArticleData.url,
      title: currentArticleData.title,
      raw_text: currentArticleData.raw_text,
      selected_text: currentArticleData.selected_text,
      author: currentArticleData.author,
      domain: currentArticleData.domain,
      use_hermes: useHermes
    };

    const response = await fetch(`${serverUrl}/api/v1/extension/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (!response.ok) {
      const errText = await response.text();
      throw new Error(`SAVI VPS Error ${response.status}: ${errText}`);
    }

    const data = await response.json();
    renderAnalysisResults(data);
  } catch (err) {
    console.error("SAVI audit failed:", err);
    document.getElementById("errorMsg").textContent = `Audit error: ${err.message}`;
    errorBox.classList.remove("hidden");
  } finally {
    loading.classList.add("hidden");
    analyzeBtn.disabled = false;
  }
}

/**
 * Renders complete SAVI multi-model evaluation into Side Panel HUD.
 */
function renderAnalysisResults(data) {
  const resultsPanel = document.getElementById("resultsPanel");

  // 1. Overall Trust Score & Verdict Badge
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

  // 2. SAVI Quad Metrics (S_dyn, A_score, V_index, I_impact)
  const m = data.savi_metrics || {};
  const sDyn = m.sentiment_dynamics ?? 0;
  const aScore = m.factual_accuracy ?? 0;
  const vIndex = m.logical_validation ?? 0;
  const iImpact = m.news_impact_index ?? 0;

  document.getElementById("metricS").textContent = sDyn.toFixed(2);
  document.getElementById("metricA").textContent = `${Math.round(aScore * 100)}%`;
  document.getElementById("metricV").textContent = `${Math.round(vIndex * 100)}%`;
  document.getElementById("metricI").textContent = iImpact.toFixed(1);

  document.getElementById("barS").style.width = `${Math.min(100, Math.max(10, Math.abs(sDyn * 100)))}%`;
  document.getElementById("barA").style.width = `${Math.min(100, Math.max(5, aScore * 100))}%`;
  document.getElementById("barV").style.width = `${Math.min(100, Math.max(5, vIndex * 100))}%`;
  document.getElementById("barI").style.width = `${Math.min(100, Math.max(10, iImpact * 20))}%`;

  // 3. Open-Jev System 1 Decision Head
  const oj = data.open_jev || {};
  const choiceEl = document.getElementById("openJevChoice");
  choiceEl.textContent = (oj.credibility_choice || "CREDIBLE").replace(/_/g, " ");
  document.getElementById("openJevConf").textContent = `Conf: ${Math.round((oj.credibility_confidence || 0.9) * 100)}%`;

  const noulProb = oj.astroturf_probability ?? 0.05;
  document.getElementById("openJevNoul").textContent = noulProb > 0.5 ? "MANIPULATED" : "ORGANIC";
  document.getElementById("openJevNoulProb").textContent = `P(manip): ${(noulProb * 100).toFixed(1)}%`;

  const evScore = oj.evidentiary_score ?? 4.8;
  document.getElementById("openJevScore").textContent = `${evScore.toFixed(1)} / 5.0`;
  document.getElementById("openJevReasoning").textContent = oj.reasoning || "System 1 verified structured information coherence.";

  // 4. Isolation Rainforest Anomaly Detection
  const an = data.anomaly_detection || {};
  const anEl = document.getElementById("anomalyAction");
  anEl.textContent = an.action || "PASS";
  document.getElementById("anomalyScore").textContent = `s(x,n): ${(an.anomaly_score ?? 0.12).toFixed(3)}`;

  if (an.action === "QUARANTINE") {
    anEl.className = "intel-val val-red";
  } else if (an.action === "FLAG_ELEVATED") {
    anEl.className = "intel-val val-amber";
  } else {
    anEl.className = "intel-val val-green";
  }

  // 5. Key Claims & Knowledge Triplets
  const claimsList = document.getElementById("claimsList");
  claimsList.innerHTML = "";
  const claims = data.key_claims || [];
  if (claims.length === 0) {
    claimsList.innerHTML = '<span class="hint">No structured claims extracted for this entity.</span>';
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

  // 6. Nous Hermes Autonomous Investigation Trajectory (Gemma 4)
  const hermesCard = document.getElementById("hermesCard");
  if (data.hermes_investigation && hermesCard) {
    hermesCard.classList.remove("hidden");
    const h = data.hermes_investigation;

    const vElem = document.getElementById("hermesVerdict");
    if (vElem) {
      vElem.textContent = `${h.verdict} (${Math.round((h.confidence_score || 0.88) * 100)}% Confidence)`;
    }

    const sElem = document.getElementById("hermesSummaryText");
    if (sElem) {
      sElem.textContent = h.executive_summary || "Autonomous investigation complete.";
    }

    const stepsList = document.getElementById("hermesStepsList");
    if (stepsList) {
      stepsList.innerHTML = "";
      if (h.trajectory && h.trajectory.steps && h.trajectory.steps.length > 0) {
        h.trajectory.steps.forEach(st => {
          const item = document.createElement("div");
          item.className = "hermes-step-item";
          item.innerHTML = `<strong>Step ${st.step_index} [${escapeHtml(st.action || 'THOUGHT')}]:</strong> <span>${escapeHtml(st.observation || st.thought)}</span>`;
          stepsList.appendChild(item);
        });
      }
    }
  } else if (hermesCard) {
    hermesCard.classList.add("hidden");
  }

  // 7. Editorial Recommendation
  document.getElementById("recommendationText").textContent = data.recommendation || "Verified organic editorial publication.";

  // 8. Processing Latency
  document.getElementById("latencyDisplay").textContent = `⚡ Analyzed in ${(data.processing_latency_ms || 0).toFixed(1)} ms`;

  // Reveal results panel
  resultsPanel.classList.remove("hidden");
}

function escapeHtml(str) {
  if (!str) return "";
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
