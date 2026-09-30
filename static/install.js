"use strict";
// Installation support only; employee records are never cached for offline use.
let installPrompt = null;
const installButton = document.querySelector("#install-app");
const standaloneDisplay = matchMedia("(display-mode: standalone)");
function updateInstallButton() {
  installButton.hidden =
    standaloneDisplay.matches || navigator.standalone === true;
}
window.addEventListener("beforeinstallprompt", (event) => {
  event.preventDefault();
  installPrompt = event;
  updateInstallButton();
});
window.addEventListener("appinstalled", () => {
  installPrompt = null;
  installButton.hidden = true;
});
standaloneDisplay.addEventListener("change", updateInstallButton);
installButton.addEventListener("click", async () => {
  const prompt = installPrompt;
  if (prompt) {
    installPrompt = null;
    try {
      await prompt.prompt();
      const choice = await prompt.userChoice;
      if (choice.outcome === "accepted") installButton.hidden = true;
      return;
    } catch {
      /* Fall back to browser-specific instructions. */
    }
  }
  document.querySelector("#install-dialog").showModal();
});
updateInstallButton();
if ("serviceWorker" in navigator && window.isSecureContext) {
  navigator.serviceWorker.register("/sw.js").catch(() => {
    // A browser shortcut remains available when service workers are unsupported.
  });
}
