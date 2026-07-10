(function () {
    var board = document.getElementById("board");
    var dice = document.getElementById("dice");
    var form = document.getElementById("move-form");
    if (!board || !dice || !form) return;

    var sourceInput = document.getElementById("source");
    var dieInput = document.getElementById("die_value");

    var selected = null;

    board.addEventListener("click", function (event) {
        var el = event.target.closest("[data-source]");
        if (!el) return;
        if (selected) selected.el.classList.remove("ring-2", "ring-accent");
        selected = { source: el.dataset.source, el: el };
        el.classList.add("ring-2", "ring-accent");
    });

    dice.addEventListener("click", function (event) {
        var el = event.target.closest("[data-die]");
        if (!el || !selected) return;
        sourceInput.value = selected.source;
        dieInput.value = el.dataset.die;
        form.submit();
    });
})();
