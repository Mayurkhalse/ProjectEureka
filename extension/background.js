/**
 * SAVI Intelligence Platform - Background Service Worker (Manifest V3)
 * Manages context menus, side panel coordination, and session storage dispatch.
 */

const DEFAULT_SERVER_URL = "http://localhost:8000";

/**
 * Safely opens the Chrome Side Panel across all Chromium versions (116+).
 */
async function openSidePanelSafely(tab) {
  if (!chrome.sidePanel || !chrome.sidePanel.open) return false;
  if (!tab) return false;

  // Strategy 1: Open using windowId (supported across Chrome 116+)
  if (tab.windowId) {
    try {
      await chrome.sidePanel.open({ windowId: tab.windowId });
      return true;
    } catch (e) {
      // Window strategy may fail if windowId is invalid
    }
  }

  // Strategy 2: Open using tabId (supported on Chrome 122+)
  if (tab.id) {
    try {
      await chrome.sidePanel.open({ tabId: tab.id });
      return true;
    } catch (e) {
      console.warn("SAVI: sidePanel.open with tabId error:", e);
    }
  }

  return false;
}

// On extension install or reload
chrome.runtime.onInstalled.addListener(() => {
  // Initialize default server URL in local storage
  chrome.storage.local.get(["saviServerUrl"], (res) => {
    if (!res.saviServerUrl) {
      chrome.storage.local.set({ saviServerUrl: DEFAULT_SERVER_URL });
    }
  });

  // Create context menus for instant verification
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: "savi-open-panel",
      title: "Open SAVI Intelligence Side Panel",
      contexts: ["page", "action"]
    });

    chrome.contextMenus.create({
      id: "savi-verify-claim",
      title: "Verify Highlighted Claim with SAVI",
      contexts: ["selection"]
    });

    chrome.contextMenus.create({
      id: "savi-audit-page",
      title: "Audit Article with SAVI Knowledge Graph",
      contexts: ["page", "link"]
    });
  });
});

// Handle Context Menu clicks
chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (!tab || !tab.id) return;

  if (info.menuItemId === "savi-verify-claim") {
    // Save highlighted text in session storage for the side panel to consume
    if (chrome.storage && chrome.storage.session) {
      await chrome.storage.session.set({
        pendingClaim: {
          text: info.selectionText || "",
          autoAnalyze: true,
          timestamp: Date.now()
        }
      });
    }

    await openSidePanelSafely(tab);
  } else if (info.menuItemId === "savi-open-panel" || info.menuItemId === "savi-audit-page") {
    await openSidePanelSafely(tab);
  }
});

// Handle runtime messages from content scripts
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === "OPEN_SIDEPANEL") {
    (async () => {
      try {
        const tab = sender.tab || (await chrome.tabs.query({ active: true, currentWindow: true }))[0];

        if (message.selectionText && chrome.storage && chrome.storage.session) {
          await chrome.storage.session.set({
            pendingClaim: {
              text: message.selectionText,
              autoAnalyze: message.autoAnalyze || false,
              timestamp: Date.now()
            }
          });
        }

        const opened = await openSidePanelSafely(tab);
        sendResponse({ success: opened });
      } catch (err) {
        console.error("SAVI: failed to open side panel via message:", err);
        sendResponse({ success: false, error: err.message });
      }
    })();
    return true; // Keep message channel open for async response
  }
});

// Notify session storage when tab changes so sidepanel updates context
if (chrome.tabs && chrome.tabs.onActivated) {
  chrome.tabs.onActivated.addListener(() => {
    if (chrome.storage && chrome.storage.session) {
      chrome.storage.session.set({ activeTabUpdated: Date.now() }).catch(() => {});
    }
  });
}
