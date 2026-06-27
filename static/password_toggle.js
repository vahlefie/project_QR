(function () {
    function setToggleState(field, button, isVisible) {
        field.classList.toggle("is-visible", isVisible);
        button.setAttribute("aria-label", isVisible ? "Sembunyikan password" : "Tampilkan password");
        button.setAttribute("title", isVisible ? "Sembunyikan password" : "Tampilkan password");
    }

    document.addEventListener("click", (event) => {
        const button = event.target.closest(".password-toggle-button");
        if (!button) {
            return;
        }

        const field = button.closest(".password-field");
        const input = field ? field.querySelector("input") : null;
        if (!input) {
            return;
        }

        event.preventDefault();
        const isVisible = input.type !== "password";
        input.type = isVisible ? "password" : "text";
        setToggleState(field, button, !isVisible);
    });
})();
