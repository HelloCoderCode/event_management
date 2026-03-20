document.addEventListener("click", (event) => {
    const btn = event.target.closest("[data-qty-action]");
    if (!btn) return;
    const action = btn.dataset.qtyAction;
    const input = document.querySelector(btn.dataset.qtyTarget);
    if (!input) return;
    const current = parseInt(input.value || "1", 10);
    if (action === "inc") {
        input.value = current + 1;
    } else if (action === "dec") {
        input.value = Math.max(current - 1, 1);
    }
});
