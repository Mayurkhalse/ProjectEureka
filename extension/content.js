/**
 * SAVI Intelligence Extension - Content Script
 * Injects on-page "⚡ SAVI Analyze" floating button and inline slide-out intelligence drawer
 * directly on news articles for frictionless zero-click-away analysis.
 */

(function () {
  // Prevent duplicate injection
  if (window.__savi_injected) return;
  window.__savi_injected = true;

  const DEFAULT_SERVER = "http://localhost:8000";

  // Check if current page looks like a readable article/news page
  function isArticlePage() {
    return (
      document.querySelector("article") !== null ||
      document.querySelector("main") !== null ||
      document.querySelector(".article-body") !== null ||
      document.querySelectorAll("p").length >= 3
    );
  }

  // Create and inject the floating trigger button on the page
  function createFloatingTrigger() {
    if (!isArticlePage()) return;
    if (document.getElementById("savi-floating-btn")) return;

    const btn = document.createElement("button");
    btn.id = "savi-floating-btn";
    btn.className = "savi-floating-trigger";
    btn.innerHTML = `
      <span class="savi-btn-icon">⚡</span>
      <span class="savi-btn-label">SAVI Analyze</span>
    `;
    btn.title = "Audit this news article with SAVI Intelligence Platform";
    btn.addEventListener("click", () => {
      openSaviDrawerAndAnalyze();
    });

    document.body.appendChild(btn);
  }

  // Create the on-page Slide-Out Intelligence Drawer
  function createSlideDrawer() {
    if (document.getElementById("savi-drawer")) return;

    const drawer = document.createElement("div");
    drawer.id = "savi-drawer";
    drawer.className = "savi-drawer savi-drawer-hidden";
    drawer.innerHTML = `
      <div class="savi-drawer-header">
        <div class="savi-drawer-brand">
          <span class="savi-drawer-logo">⚡</span>
          <div>
            <h3>SAVI INTELLIGENCE</h3>
            <span class="savi-drawer-sub">Autonomous News Verification</span>
          </div>
        </div>
        <button id="savi-drawer-close" class="savi-drawer-close-btn" title="Close">✕</button>
      </div>

      <div class="savi-drawer-body">
        <div id="savi-drawer-article-info" class="savi-article-info">
          <span id="savi-drawer-domain" class="savi-domain-tag"></span>
          <h4 id="savi-drawer-title"></h4>
        </div>

        <div id="savi-drawer-loading" class="savi-drawer-loading savi-hidden">
          <div class="savi-spinner"></div>
          <p>Auditing Knowledge Graph & Open-Jev System 1...</p>
        </div>

        <div id="savi-drawer-content" class="savi-drawer-content savi-hidden">
          <!-- Trust Gauge -->
          <div class="savi-card savi-trust-card">
            <div>
              <span class="savi-card-label">OVERALL TRUST RATING</span>
              <div class="savi-score-row">
                <span id="savi-drawer-score" class="savi-score-num">--</span>
                <span class="savi-score-pct">%</span>
              </div>
            </div>
            <div class="savi-verdict-box">
              <span id="savi-drawer-verdict" class="savi-verdict-pill">VERIFIED</span>
              <span id="savi-drawer-trust-label" class="savi-trust-label"></span>
            </div>
          </div>

          <!-- SAVI Metrics -->
          <div class="savi-card">
            <span class="savi-card-label">SAVI ANALYTICAL MATRIX</span>
            <div class="savi-metrics-grid">
              <div class="savi-metric-row">
                <span>Sentiment (S<sub>dyn</sub>):</span>
                <strong id="savi-m-s">--</strong>
              </div>
              <div class="savi-metric-row">
                <span>Factual Accuracy (A<sub>score</sub>):</span>
                <strong id="savi-m-a">--</strong>
              </div>
              <div class="savi-metric-row">
                <span>Logical Validation (V<sub>index</sub>):</span>
                <strong id="savi-m-v">--</strong>
              </div>
              <div class="savi-metric-row">
                <span>News Impact (I<sub>impact</sub>):</span>
                <strong id="savi-m-i">--</strong>
              </div>
            </div>
          </div>

          <!-- Open-Jev & Rainforest -->
          <div class="savi-card">
            <span class="savi-card-label">SYSTEM 1 HEAD & ANOMALY FILTER</span>
            <div class="savi-intel-split">
              <div>
                <small>Open-Jev Decision:</small>
                <div id="savi-drawer-oj" class="savi-tag-green">CREDIBLE</div>
              </div>
              <div>
                <small>Rainforest Boundary:</small>
                <div id="savi-drawer-rf" class="savi-tag-green">PASS_ORGANIC</div>
              </div>
            </div>
            <p id="savi-drawer-oj-reasoning" class="savi-quote-text"></p>
          </div>

          <!-- Key Claims List -->
          <div class="savi-card">
            <span class="savi-card-label">VERIFIED CLAIM TRIPLETS</span>
            <div id="savi-drawer-claims" class="savi-claims-box"></div>
          </div>

          <!-- Editorial Recommendation -->
          <div class="savi-card savi-rec-card">
            <span class="savi-card-label">🛡️ EDITORIAL RECOMMENDATION</span>
            <p id="savi-drawer-rec" class="savi-rec-text"></p>
          </div>
        </div>

        <div id="savi-drawer-error" class="savi-drawer-error savi-hidden">
          <p id="savi-drawer-err-msg"></p>
          <button id="savi-drawer-retry" class="savi-btn-small">Retry</button>
        </div>
      </div>

      <div class="savi-drawer-footer">
        <span id="savi-drawer-latency">⚡ Ready</span>
        <span>PostgreSQL CQRS Sub-10ms Serving</span>
      </div>
    `;

    document.body.appendChild(drawer);

    document.getElementById("savi-drawer-close").addEventListener("click", () => {
      drawer.classList.add("savi-drawer-hidden");
    });

    document.getElementById("savi-drawer-retry").addEventListener("click", () => {
      openSaviDrawerAndAnalyze();
    });
  }

  // Extract page content
  function extractArticleContent() {
    const url = window.location.href;
    const title = document.title || "";
    let domain = "";
    try {
      domain = window.location.hostname.replace(/^www\./, "");
    } catch {
      domain = "web";
    }

    const selection = window.getSelection() ? window.getSelection().toString().trim() : "";

    let body = "";
    const article = document.querySelector("article") || document.querySelector("main") || document.querySelector(".article-body");
    if (article) {
      body = article.innerText.trim();
    } else {
      const ps = Array.from(document.querySelectorAll("p"))
        .map(p => p.innerText.trim())
        .filter(t => t.length > 40);
      body = ps.slice(0, 15).join("\n\n");
    }

    let author = "";
    const authMeta = document.querySelector('meta[name="author"]') || document.querySelector('meta[property="article:author"]');
    if (authMeta) author = authMeta.content;

    return {
      url,
      title,
      domain,
      author,
      raw_text: body.slice(0, 4000),
      selected_text: selection
    };
  }

  // Execute analysis and display drawer
  async function openSaviDrawerAndAnalyze() {
    createSlideDrawer();
    const drawer = document.getElementById("savi-drawer");
    drawer.classList.remove("savi-drawer-hidden");

    const article = extractArticleContent();
    document.getElementById("savi-drawer-domain").textContent = article.domain;
    document.getElementById("savi-drawer-title").textContent = article.title || article.url;

    const loading = document.getElementById("savi-drawer-loading");
    const content = document.getElementById("savi-drawer-content");
    const errorBox = document.getElementById("savi-drawer-error");

    loading.classList.remove("savi-hidden");
    content.classList.add("savi-hidden");
    errorBox.classList.add("savi-hidden");

    // Fetch server URL from storage
    let serverUrl = DEFAULT_SERVER;
    try {
      if (chrome.storage && chrome.storage.local) {
        const stored = await chrome.storage.local.get(["saviServerUrl"]);
        if (stored.saviServerUrl) serverUrl = stored.saviServerUrl;
      }
    } catch {}

    try {
      const res = await fetch(`${serverUrl}/api/v1/extension/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(article)
      });

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${await res.text()}`);
      }

      const data = await res.json();
      renderDrawerData(data);
      loading.classList.add("savi-hidden");
      content.classList.remove("savi-hidden");
    } catch (err) {
      loading.classList.add("savi-hidden");
      errorBox.classList.remove("savi-hidden");
      document.getElementById("savi-drawer-err-msg").textContent = `Could not reach SAVI VPS (${serverUrl}): ${err.message}`;
    }
  }

  // Populate drawer
  function renderDrawerData(data) {
    document.getElementById("savi-drawer-score").textContent = Math.round(data.trust_score || 0);
    document.getElementById("savi-drawer-trust-label").textContent = data.trust_label || "";

    const vBadge = document.getElementById("savi-drawer-verdict");
    vBadge.textContent = data.overall_verdict || "VERIFIED";
    vBadge.className = "savi-verdict-pill";
    if (data.overall_verdict === "VERIFIED_ORGANIC") {
      vBadge.classList.add("savi-v-green");
    } else if (data.overall_verdict === "CAUTION_FLAGGED") {
      vBadge.classList.add("savi-v-amber");
    } else {
      vBadge.classList.add("savi-v-red");
    }

    const m = data.savi_metrics || {};
    document.getElementById("savi-m-s").textContent = (m.sentiment_dynamics ?? 0).toFixed(2);
    document.getElementById("savi-m-a").textContent = `${Math.round((m.factual_accuracy ?? 0) * 100)}%`;
    document.getElementById("savi-m-v").textContent = `${Math.round((m.logical_validation ?? 0) * 100)}%`;
    document.getElementById("savi-m-i").textContent = (m.news_impact_index ?? 0).toFixed(1);

    const oj = data.open_jev || {};
    document.getElementById("savi-drawer-oj").textContent = (oj.credibility_choice || "CREDIBLE").replace(/_/g, " ");
    document.getElementById("savi-drawer-oj-reasoning").textContent = oj.reasoning || "";

    const an = data.anomaly_detection || {};
    document.getElementById("savi-drawer-rf").textContent = an.action || "PASS_ORGANIC";

    // Claims
    const claimsBox = document.getElementById("savi-drawer-claims");
    claimsBox.innerHTML = "";
    (data.key_claims || []).forEach(c => {
      const el = document.createElement("div");
      el.className = "savi-claim-row";
      el.innerHTML = `
        <div class="savi-claim-txt"><strong>${escapeHtml(c.subject)}</strong> <em>${escapeHtml(c.predicate)}</em> ${escapeHtml(c.object)}</div>
        <span class="savi-claim-tag savi-tag-${(c.verdict || "neutral").toLowerCase()}">${c.verdict || "Verified"}</span>
      `;
      claimsBox.appendChild(el);
    });

    document.getElementById("savi-drawer-rec").textContent = data.recommendation || "";
    document.getElementById("savi-drawer-latency").textContent = `⚡ Analyzed in ${(data.processing_latency_ms || 0).toFixed(1)} ms`;
  }

  function escapeHtml(s) {
    if (!s) return "";
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  // Floating text selection trigger
  let selectionTooltip = null;

  function handleSelection() {
    const sel = window.getSelection();
    const text = sel ? sel.toString().trim() : "";

    if (text && text.length > 15 && text.length < 400) {
      if (!selectionTooltip) {
        selectionTooltip = document.createElement("div");
        selectionTooltip.id = "savi-selection-tooltip";
        selectionTooltip.className = "savi-selection-tooltip";
        selectionTooltip.innerHTML = `<span>⚡ Verify Claim with SAVI</span>`;
        selectionTooltip.addEventListener("click", () => {
          openSaviDrawerAndAnalyze();
          if (selectionTooltip) selectionTooltip.remove();
          selectionTooltip = null;
        });
        document.body.appendChild(selectionTooltip);
      }

      const range = sel.getRangeAt(0);
      const rect = range.getBoundingClientRect();
      selectionTooltip.style.top = `${window.scrollY + rect.top - 38}px`;
      selectionTooltip.style.left = `${window.scrollX + rect.left + (rect.width / 2) - 80}px`;
    } else {
      if (selectionTooltip) {
        selectionTooltip.remove();
        selectionTooltip = null;
      }
    }
  }

  document.addEventListener("mouseup", handleSelection);

  // Initialize
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      createFloatingTrigger();
      createSlideDrawer();
    });
  } else {
    createFloatingTrigger();
    createSlideDrawer();
  }

  // Listen for messages from background context menu
  if (chrome.runtime && chrome.runtime.onMessage) {
    chrome.runtime.onMessage.addListener((req, sender, sendResponse) => {
      if (req.action === "TRIGGER_SAVI_ANALYSIS") {
        openSaviDrawerAndAnalyze();
        sendResponse({ status: "opened" });
      }
    });
  }
})();
