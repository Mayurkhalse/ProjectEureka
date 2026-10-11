/**
 * SAVI Intelligence Platform - Background Service Worker (Manifest V3)
 * Implements Google Chrome Extension Side Panel Framework (chrome.sidePanel)
 * Manages side panel behavior, context menus, and session storage dispatch.
 */

const DEFAULT_SERVER_URL = "http://localhost:8000";

// Configure side panel to open directly when clicking the extension action icon in the toolbar
if (chrome.sidePanel && chrome.sidePanel.setPanelBehavior) {
  chrome.sidePanel
    .setPanelBehavior({ openPanelOnActionClick: true })
    .catch((error) => console.warn("SAVI: sidePanel.setPanelBehavior error:", error));
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
      title: "⚡ Open SAVI Intelligence Side Panel",
      contexts: ["page", "action"]
    });

    chrome.contextMenus.create({
      id: "savi-verify-claim",
      title: "⚡ Verify Highlighted Claim with SAVI",
      contexts: ["selection"]
    });

    chrome.contextMenus.create({
      id: "savi-audit-page",
      title: "⚡ Audit Article with SAVI Knowledge Graph",
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

    // Open native Chrome Side Panel on the active tab
    if (chrome.sidePanel && chrome.sidePanel.open) {
      await chrome.sidePanel.open({ tabId: tab.id });
    }
  } else if (info.menuItemId === "savi-open-panel" || info.menuItemId === "savi-audit-page") {
    // Open native Chrome Side Panel
    if (chrome.sidePanel && chrome.sidePanel.open) {
      await chrome.sidePanel.open({ tabId: tab.id });
    }
  }
});

// Handle runtime messages from content scripts
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === "OPEN_SIDEPANEL") {
    (async () => {
      try {
        const tabId = sender.tab ? sender.tab.id : message.tabId;
        if (message.selectionText && chrome.storage && chrome.storage.session) {
          await chrome.storage.session.set({
            pendingClaim: {
              text: message.selectionText,
              autoAnalyze: message.autoAnalyze || false,
              timestamp: Date.now()
            }
          });
        }

        if (tabId && chrome.sidePanel && chrome.sidePanel.open) {
          await chrome.sidePanel.open({ tabId: tabId });
        }
        sendResponse({ success: true });
      } catch (err) {
        console.error("SAVI: failed to open side panel via message:", err);
        sendResponse({ success: false, error: err.message });
      }
    })();
    return true; // Keep message channel open for async response
  }
});

// Notify session storage when tab changes so sidepanel updates context
chrome.tabs.onActivated.addListener((activeInfo) => {
  if (chrome.storage && chrome.storage.session) {
    chrome.storage.session.set({ activeTabUpdated: Date.now() }).catch(() => {});
  }
});
