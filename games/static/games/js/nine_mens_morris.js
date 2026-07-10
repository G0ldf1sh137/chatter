(function () {
    var board = document.getElementById("board");
    var form = document.getElementById("move-form");
    if (!board || !form) return;

    var fromPoint = document.getElementById("from_point");
    var toPoint = document.getElementById("to_point");

    var selected = null;

    board.addEventListener("click", function (event) {
        var point = event.target.closest("[data-point]");
        if (!point) return;
        var id = point.dataset.point;

        if (selected && selected.id === id) {
            selected.el.classList.remove("ring-2", "ring-accent");
            selected = null;
            return;
        }

        if (!selected) {
            selected = { id: id, el: point };
            point.classList.add("ring-2", "ring-accent");
            return;
        }

        fromPoint.value = selected.id;
        toPoint.value = id;
        form.submit();
    });
})();
