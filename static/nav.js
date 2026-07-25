(function () {
  "use strict";

  const MQ = window.matchMedia("(max-width: 1079px)");
  const OPEN_DELAY = 80;
  const CLOSE_DELAY = 160;

  function closePanel(dropdown) {
    const btn = dropdown.querySelector(".app-nav__trigger");
    const panel = dropdown.querySelector(".app-nav__panel");
    if (!btn || !panel) return;
    btn.setAttribute("aria-expanded", "false");
    panel.hidden = true;
    dropdown.classList.remove("is-open");
  }

  function openPanel(dropdown) {
    document.querySelectorAll("[data-nav-dropdown].is-open").forEach((d) => {
      if (d !== dropdown) closePanel(d);
    });
    const btn = dropdown.querySelector(".app-nav__trigger");
    const panel = dropdown.querySelector(".app-nav__panel");
    if (!btn || !panel) return;
    btn.setAttribute("aria-expanded", "true");
    panel.hidden = false;
    dropdown.classList.add("is-open");
  }

  function initDropdown(dropdown) {
    const btn = dropdown.querySelector(".app-nav__trigger");
    const panel = dropdown.querySelector(".app-nav__panel");
    if (!btn || !panel) return;

    let openTimer = null;
    let closeTimer = null;

    function clearTimers() {
      if (openTimer) clearTimeout(openTimer);
      if (closeTimer) clearTimeout(closeTimer);
      openTimer = null;
      closeTimer = null;
    }

    btn.addEventListener("click", (e) => {
      e.preventDefault();
      if (dropdown.classList.contains("is-open")) closePanel(dropdown);
      else openPanel(dropdown);
    });

    btn.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        if (dropdown.classList.contains("is-open")) closePanel(dropdown);
        else openPanel(dropdown);
      }
      if (e.key === "ArrowDown") {
        e.preventDefault();
        openPanel(dropdown);
        const first = panel.querySelector("a");
        if (first) first.focus();
      }
      if (e.key === "Escape") {
        closePanel(dropdown);
        btn.focus();
      }
    });

    panel.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        e.preventDefault();
        closePanel(dropdown);
        btn.focus();
      }
    });

    dropdown.addEventListener("mouseenter", () => {
      if (MQ.matches) return;
      clearTimers();
      openTimer = setTimeout(() => openPanel(dropdown), OPEN_DELAY);
    });

    dropdown.addEventListener("mouseleave", () => {
      if (MQ.matches) return;
      clearTimers();
      closeTimer = setTimeout(() => closePanel(dropdown), CLOSE_DELAY);
    });
  }

  function initNav(root) {
    const toggle = root.querySelector("#appNavToggle");
    const menu = root.querySelector("#appNavMenu");

    root.querySelectorAll("[data-nav-dropdown]").forEach(initDropdown);

    if (toggle && menu) {
      toggle.addEventListener("click", () => {
        const open = toggle.getAttribute("aria-expanded") === "true";
        toggle.setAttribute("aria-expanded", open ? "false" : "true");
        root.classList.toggle("is-menu-open", !open);
      });
    }

    document.addEventListener("keydown", (e) => {
      if (e.key !== "Escape") return;
      root.querySelectorAll("[data-nav-dropdown].is-open").forEach(closePanel);
      if (toggle) {
        toggle.setAttribute("aria-expanded", "false");
        root.classList.remove("is-menu-open");
      }
    });

    document.addEventListener("click", (e) => {
      if (root.contains(e.target)) return;
      root.querySelectorAll("[data-nav-dropdown].is-open").forEach(closePanel);
    });
  }

  document.querySelectorAll("[data-app-nav]").forEach(initNav);
})();
