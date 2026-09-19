(function () {
  "use strict";

  function closeMenu(root) {
    const btn = root.querySelector(".log-export-menu__trigger");
    const panel = root.querySelector(".log-export-menu__panel");
    if (!btn || !panel) return;
    btn.setAttribute("aria-expanded", "false");
    panel.hidden = true;
    root.classList.remove("is-open");
  }

  function openMenu(root) {
    document.querySelectorAll("[data-log-export-menu].is-open").forEach((el) => {
      if (el !== root) closeMenu(el);
    });
    const btn = root.querySelector(".log-export-menu__trigger");
    const panel = root.querySelector(".log-export-menu__panel");
    if (!btn || !panel) return;
    btn.setAttribute("aria-expanded", "true");
    panel.hidden = false;
    root.classList.add("is-open");
  }

  function init(root) {
    const btn = root.querySelector(".log-export-menu__trigger");
    if (!btn) return;

    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      if (root.classList.contains("is-open")) closeMenu(root);
      else openMenu(root);
    });

    root.querySelectorAll(".log-export-menu__item").forEach((link) => {
      link.addEventListener("click", () => closeMenu(root));
    });
  }

  function boot() {
    document.querySelectorAll("[data-log-export-menu]").forEach(init);
    document.addEventListener("click", () => {
      document.querySelectorAll("[data-log-export-menu].is-open").forEach(closeMenu);
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        document.querySelectorAll("[data-log-export-menu].is-open").forEach(closeMenu);
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
