(function () {
    const themeKey = "personal-finance-theme";
    const root = document.documentElement;
    const toggleSelector = "[data-theme-toggle]";
    const themeColor = document.querySelector('meta[name="theme-color"]');

    function updateToggleButtons() {
        const isDark = root.dataset.theme === "dark";

        document.querySelectorAll(toggleSelector).forEach(function (button) {
            button.setAttribute("aria-pressed", String(isDark));
            button.setAttribute(
                "aria-label",
                isDark ? "Switch to light mode" : "Switch to dark mode"
            );
            button.textContent = isDark ? "Light mode" : "Dark mode";
            button.hidden = false;
        });

        if (themeColor) {
            themeColor.setAttribute("content", isDark ? "#111915" : "#f5f7f4");
        }
    }

    try {
        if (window.localStorage.getItem(themeKey) === "dark") {
            root.dataset.theme = "dark";
        }
    } catch (error) {
        // Keep the default theme if browser storage is unavailable.
    }

    document.addEventListener("DOMContentLoaded", updateToggleButtons);

    document.addEventListener("click", function (event) {
        if (!(event.target instanceof Element)) {
            return;
        }

        const toggle = event.target.closest(toggleSelector);
        if (!toggle) {
            return;
        }

        const isDark = root.dataset.theme !== "dark";
        if (isDark) {
            root.dataset.theme = "dark";
        } else {
            delete root.dataset.theme;
        }
        updateToggleButtons();

        try {
            window.localStorage.setItem(themeKey, isDark ? "dark" : "light");
        } catch (error) {
            // The selected theme still applies for the current page.
        }
    });
})();
