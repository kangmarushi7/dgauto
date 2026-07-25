(function () {
  "use strict";

  for (const button of document.querySelectorAll("[data-resync-strategy]")) {
    button.addEventListener("click", async () => {
      const strategy = button.dataset.resyncStrategy;
      const status = document.getElementById("status");
      const originalText = button.textContent;
      button.disabled = true;
      button.textContent = "Resyncing…";
      if (status) status.textContent = "Replacing today's open bets…";

      try {
        const response = await fetch(
          `/api/bets/resync-today?strategy=${encodeURIComponent(strategy)}`,
          { method: "POST" }
        );
        const data = await response.json();
        if (!response.ok || data.success === false) {
          throw new Error(data.error || "Resync failed");
        }

        const deleted = Number(data.resync?.deleted_total || 0);
        const inserted = Number(data.resync?.inserted_total || 0);
        if (status) status.textContent = `Replaced ${deleted}, added ${inserted}. Reloading…`;
        window.location.reload();
      } catch (error) {
        if (status) status.textContent = `Resync failed: ${error.message || error}`;
        button.disabled = false;
        button.textContent = originalText;
      }
    });
  }
})();
