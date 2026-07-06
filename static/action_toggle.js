(function () {
    let openGroup = null;
    const actionMenuRegistry = new WeakMap();

    function getActionItems(group) {
        return Array.from(group.children).filter((child) => {
            return !child.classList.contains("action-toggle-button") && !child.classList.contains("action-menu-items");
        });
    }

    function getActionMenu(group) {
        return actionMenuRegistry.get(group) || document.getElementById(group.dataset.actionMenuId);
    }

    function positionActionMenu(group) {
        const toggleButton = group.querySelector(".action-toggle-button");
        const menuItems = getActionMenu(group);
        if (!toggleButton || !menuItems || menuItems.hidden) {
            return;
        }

        const viewportGap = 8;
        const buttonRect = toggleButton.getBoundingClientRect();

        menuItems.style.top = `${buttonRect.bottom + 6}px`;
        menuItems.style.left = `${buttonRect.left}px`;
        menuItems.style.maxHeight = `${Math.max(80, window.innerHeight - buttonRect.bottom - viewportGap - 6)}px`;

        const menuRect = menuItems.getBoundingClientRect();
        const hasEnoughBottomSpace = buttonRect.bottom + 6 + menuRect.height <= window.innerHeight - viewportGap;
        const safeTop = hasEnoughBottomSpace
            ? buttonRect.bottom + 6
            : Math.max(viewportGap, buttonRect.top - menuRect.height - 6);
        const safeLeft = Math.min(
            Math.max(viewportGap, buttonRect.left),
            Math.max(viewportGap, window.innerWidth - menuRect.width - viewportGap)
        );

        menuItems.style.top = `${safeTop}px`;
        menuItems.style.left = `${safeLeft}px`;
        const availableHeight = hasEnoughBottomSpace
            ? window.innerHeight - safeTop - viewportGap
            : buttonRect.top - viewportGap - 6;
        menuItems.style.maxHeight = `${Math.max(80, availableHeight)}px`;
    }

    function setActionMenuState(group, isOpen) {
        const toggleButton = group.querySelector(".action-toggle-button");
        const menuItems = getActionMenu(group);
        if (!toggleButton || !menuItems) {
            return;
        }

        if (isOpen && openGroup && openGroup !== group) {
            setActionMenuState(openGroup, false);
        }

        group.classList.toggle("is-open", isOpen);
        toggleButton.textContent = isOpen ? "Hide" : "Show";
        toggleButton.setAttribute("aria-expanded", String(isOpen));
        menuItems.hidden = !isOpen;

        if (isOpen) {
            openGroup = group;
            positionActionMenu(group);
        } else if (openGroup === group) {
            openGroup = null;
        }
    }

    document.querySelectorAll(".action-group").forEach((group, index) => {
        if (group.dataset.actionToggleReady === "true") {
            return;
        }

        const actionItems = getActionItems(group);
        const visibleActionItems = actionItems.filter((item) => {
            return !item.hidden && !item.classList.contains("is-hidden");
        });

        if (visibleActionItems.length <= 1) {
            return;
        }

        const menuId = `action-menu-items-${index + 1}`;
        const toggleButton = document.createElement("button");
        toggleButton.type = "button";
        toggleButton.className = "secondary-button table-action-button action-toggle-button";
        toggleButton.textContent = "Show";
        toggleButton.setAttribute("aria-expanded", "false");
        toggleButton.setAttribute("aria-controls", menuId);

        const menuItems = document.createElement("div");
        menuItems.id = menuId;
        menuItems.className = "action-menu-items";

        actionItems.forEach((item) => menuItems.appendChild(item));
        group.append(toggleButton);
        document.body.appendChild(menuItems);
        group.dataset.actionMenuId = menuId;
        actionMenuRegistry.set(group, menuItems);
        group.classList.add("is-collapsible");
        group.dataset.actionToggleReady = "true";

        setActionMenuState(group, false);

        toggleButton.addEventListener("click", (event) => {
            event.stopPropagation();
            setActionMenuState(group, !group.classList.contains("is-open"));
        });
    });

    document.addEventListener("click", (event) => {
        const openMenu = openGroup ? getActionMenu(openGroup) : null;
        if (!openGroup || openGroup.contains(event.target) || (openMenu && openMenu.contains(event.target))) {
            return;
        }

        setActionMenuState(openGroup, false);
    });

    window.addEventListener("resize", () => {
        if (openGroup) {
            positionActionMenu(openGroup);
        }
    });

    window.addEventListener(
        "scroll",
        () => {
            if (openGroup) {
                positionActionMenu(openGroup);
            }
        },
        true
    );
})();
