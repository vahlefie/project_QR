(function () {
    const panelContainer = document.querySelector("[data-sidebar-panels]");
    if (!panelContainer) {
        return;
    }

    const panels = Array.from(panelContainer.querySelectorAll("[data-sidebar-panel]"));
    const openButtons = Array.from(panelContainer.querySelectorAll("[data-sidebar-open]"));
    const backButtons = Array.from(panelContainer.querySelectorAll("[data-sidebar-back]"));
    const disabledLinks = Array.from(panelContainer.querySelectorAll(".sidebar-disabled-link"));

    function getPanel(name) {
        return panels.find((panel) => panel.dataset.sidebarPanel === name);
    }

    function showPanel(name) {
        const targetPanel = getPanel(name);
        if (!targetPanel) {
            return;
        }

        panels.forEach((panel) => {
            const isTarget = panel === targetPanel;
            panel.classList.toggle("is-active", isTarget);
            panel.classList.remove("is-exiting");
            panel.setAttribute("aria-hidden", String(!isTarget));
        });
    }

    function openInitialActivePanel() {
        const activeLink = panelContainer.querySelector("[data-sidebar-panel]:not([data-sidebar-panel='main']) a.active");
        if (activeLink) {
            const activePanel = activeLink.closest("[data-sidebar-panel]");
            if (activePanel) {
                showPanel(activePanel.dataset.sidebarPanel);
            }
        }
    }

    openButtons.forEach((button) => {
        button.addEventListener("click", () => {
            showPanel(button.dataset.sidebarOpen);
        });
    });

    backButtons.forEach((button) => {
        button.addEventListener("click", () => {
            showPanel("main");
        });
    });

    disabledLinks.forEach((link) => {
        link.addEventListener("click", (event) => {
            event.preventDefault();
        });
    });

    openInitialActivePanel();
})();
