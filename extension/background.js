/**
 * SAVI Intelligence Extension - Background Service Worker
 * Manages context menus, keyboard shortcuts, and extension lifecycle.
 */

const DEFAULT_SERVER_URL = "http://localhost:8000";

// On installation, initialize default storage and context menus
chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.local.get(["saviServerUrl"], (res) => {
    if (!res.saviServerUrl) {
      chrome.storage.local.set({ saviServerUrl: DEFAULT_SERVER_URL });
    }
  });

  // Create right-click context menu options
  chrome.contextMenus.create({
    id: "savi-analyze-page",
    title: "⚡ Analyze News Article with SAVI",
    contexts: ["page", "link"]
  });

  chrome.contextMenus.create({
    id: "savi-verify-claim",
    title: "⚡ Verify Claim with SAVI Logic Head",
    contexts: ["selection"]
  });
});

// Handle context menu clicks
chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (!tab || !tab.id) return;

  if (info.menuItemId === "savi-analyze-page" || info.menuItemId === "savi-verify-claim") {
    // Send message to content script to trigger analysis drawer
    chrome.tabs.sendMessage(tab.id, {
      action: "TRIGGER_SAVI_ANALYSIS",
      selectionText: info.selectionText || ""
    }, (res) => {
      // Fallback if content script not yet injected
      if (chrome.runtime.lastError) {
        chrome.scripting.executeScript({
          target: { tabId: tab.id },
          files: ["content.js"]
        }, () => {
          chrome.tabs.sendMessage(tab.id, { action: "TRIGGER_SAVI_ANALYSIS" });
        });
      }
    });
  }
});
