(function () {
    const storageKey = "projectQrSidebarHidden";
    const mobileAutoHideKey = "projectQrMobileSidebarAutoHide";
    const app = document.querySelector(".app");
    const toggleButton = document.querySelector(".sidebar-toggle");
    const sidebar = document.querySelector(".sidebar");
    let fallbackHidden = false;

    if (!app || !toggleButton) {
        return;
    }

    function isMobileSidebar() {
        return window.matchMedia("(max-width: 760px)").matches;
    }

    function readStoredState() {
        try {
            return localStorage.getItem(storageKey) === "true";
        } catch (error) {
            return fallbackHidden;
        }
    }

    function writeStoredState(isHidden) {
        fallbackHidden = isHidden;
        try {
            localStorage.setItem(storageKey, String(isHidden));
        } catch (error) {
            // The button should still work even when browser storage is blocked.
        }
    }

    function setSidebarState(isHidden) {
        app.classList.toggle("sidebar-is-hidden", isHidden);
        toggleButton.setAttribute("aria-expanded", String(!isHidden));
        toggleButton.setAttribute(
            "aria-label",
            isHidden ? "Tampilkan sidebar" : "Sembunyikan sidebar"
        );
        toggleButton.title = isHidden ? "Tampilkan sidebar" : "Sembunyikan sidebar";
    }

    setSidebarState(readStoredState());

    try {
        if (isMobileSidebar() && sessionStorage.getItem(mobileAutoHideKey) === "true") {
            sessionStorage.removeItem(mobileAutoHideKey);
            setSidebarState(true);
        }
    } catch (error) {
        // The normal persisted sidebar state is still enough when session storage is blocked.
    }

    toggleButton.addEventListener("click", () => {
        const isHidden = !app.classList.contains("sidebar-is-hidden");
        writeStoredState(isHidden);
        setSidebarState(isHidden);
    });

    if (sidebar) {
        sidebar.querySelectorAll("a[href]").forEach((link) => {
            link.addEventListener("click", () => {
                if (!isMobileSidebar()) {
                    return;
                }

                const href = link.getAttribute("href") || "";
                if (link.classList.contains("sidebar-disabled-link") || href === "#" || href.startsWith("javascript:")) {
                    return;
                }

                try {
                    sessionStorage.setItem(mobileAutoHideKey, "true");
                } catch (error) {
                    writeStoredState(true);
                }
            });
        });
    }
})();
