(function () {
    const sidebar = document.querySelector(".sidebar");
    const toggle = document.querySelector("[data-mobile-nav-toggle]");
    const toggleIcon = document.querySelector("[data-mobile-nav-icon]");
    const backdrop = document.querySelector("[data-mobile-nav-backdrop]");
    const navigation = document.querySelector("#primary-nav");
    const workspace = document.querySelector(".workspace");

    if (
        !sidebar ||
        !toggle ||
        !toggleIcon ||
        !backdrop ||
        !navigation ||
        !workspace
    ) {
        return;
    }

    function setOpen(isOpen, returnFocus) {
        sidebar.classList.toggle("is-mobile-open", isOpen);
        backdrop.classList.toggle("is-visible", isOpen);
        backdrop.hidden = !isOpen;
        workspace.inert = isOpen;
        toggle.setAttribute("aria-expanded", String(isOpen));
        toggle.setAttribute(
            "aria-label",
            isOpen ? "Close navigation" : "Open navigation"
        );
        toggleIcon.textContent = isOpen ? "×" : "☰";

        if (returnFocus) {
            toggle.focus();
        }
    }

    toggle.addEventListener("click", function () {
        setOpen(toggle.getAttribute("aria-expanded") !== "true", false);
    });

    backdrop.addEventListener("click", function () {
        setOpen(false, true);
    });

    navigation.addEventListener("click", function (event) {
        if (event.target.closest("a")) {
            setOpen(false, false);
        }
    });

    document.addEventListener("keydown", function (event) {
        if (
            event.key === "Escape" &&
            toggle.getAttribute("aria-expanded") === "true"
        ) {
            setOpen(false, true);
        }
    });

    window.addEventListener("resize", function () {
        if (window.innerWidth > 760) {
            setOpen(false, false);
        }
    });
})();
