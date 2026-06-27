(function () {
    const storageKey = "projectQrSidebarHidden";
    const app = document.querySelector(".app");
    const toggleButton = document.querySelector(".sidebar-toggle");
    let fallbackHidden = false;

    if (!app || !toggleButton) {
        return;
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

    toggleButton.addEventListener("click", () => {
        const isHidden = !app.classList.contains("sidebar-is-hidden");
        writeStoredState(isHidden);
        setSidebarState(isHidden);
    });
})();
