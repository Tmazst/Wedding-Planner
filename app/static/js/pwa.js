(() => {
  "use strict";

  const promptBox = document.getElementById("install-prompt");
  const installButton = document.getElementById("install-button");
  const closeButton = document.getElementById("install-close");
  const iosHelp = document.getElementById("ios-install-help");
  if (!promptBox || !installButton || !closeButton) return;

  const DISMISSED_KEY = "umshado-install-dismissed";
  const DISMISS_DAYS = 14;
  let installEvent = null;
  let delayFinished = false;
  const standalone = window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone === true;
  const isIos = /iphone|ipad|ipod/i.test(window.navigator.userAgent);

  function recentlyDismissed() {
    const dismissedAt = Number(localStorage.getItem(DISMISSED_KEY) || 0);
    return dismissedAt && Date.now() - dismissedAt < DISMISS_DAYS * 24 * 60 * 60 * 1000;
  }

  function showWhenEligible() {
    if (!delayFinished || standalone || recentlyDismissed()) return;
    if (installEvent) {
      promptBox.hidden = false;
    } else if (isIos) {
      promptBox.classList.add("ios-mode");
      iosHelp.hidden = false;
      promptBox.hidden = false;
    }
  }

  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    installEvent = event;
    showWhenEligible();
  });

  installButton.addEventListener("click", async () => {
    if (!installEvent) return;
    installEvent.prompt();
    await installEvent.userChoice;
    installEvent = null;
    promptBox.hidden = true;
  });

  closeButton.addEventListener("click", () => {
    localStorage.setItem(DISMISSED_KEY, String(Date.now()));
    promptBox.hidden = true;
  });

  window.addEventListener("appinstalled", () => {
    installEvent = null;
    promptBox.hidden = true;
    localStorage.removeItem(DISMISSED_KEY);
  });

  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => navigator.serviceWorker.register("/service-worker.js"));
  }

  window.setTimeout(() => {
    delayFinished = true;
    showWhenEligible();
  }, 60000);
})();
