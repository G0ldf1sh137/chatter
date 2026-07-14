(function () {
    var addButton = document.getElementById("add-poll-option");
    if (!addButton) return;

    addButton.addEventListener("click", function () {
        var hidden = document.querySelector("#poll-options [data-poll-option].hidden");
        if (!hidden) return;
        hidden.classList.remove("hidden");
        if (!document.querySelector("#poll-options [data-poll-option].hidden")) {
            addButton.classList.add("hidden");
        }
    });
})();
