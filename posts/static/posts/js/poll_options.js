(function () {
    var addButton = document.getElementById("add-poll-option");
    if (!addButton) return;

    function updateButtonVisibility() {
        var hasHidden = document.querySelector("#poll-options [data-poll-option].hidden");
        addButton.classList.toggle("hidden", !hasHidden);
    }

    addButton.addEventListener("click", function () {
        var hidden = document.querySelector("#poll-options [data-poll-option].hidden");
        if (!hidden) return;
        hidden.classList.remove("hidden");
        updateButtonVisibility();
    });

    updateButtonVisibility();
})();
