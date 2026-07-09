(function () {
    var board = document.getElementById("board");
    var form = document.getElementById("move-form");
    if (!board || !form) return;

    var fromRow = document.getElementById("from_row");
    var fromCol = document.getElementById("from_col");
    var toRow = document.getElementById("to_row");
    var toCol = document.getElementById("to_col");

    var selected = null;

    board.addEventListener("click", function (event) {
        var square = event.target.closest("[data-row]");
        if (!square) return;
        var row = square.dataset.row;
        var col = square.dataset.col;

        if (selected && selected.row === row && selected.col === col) {
            selected.el.classList.remove("ring-2", "ring-accent");
            selected = null;
            return;
        }

        if (!selected) {
            selected = { row: row, col: col, el: square };
            square.classList.add("ring-2", "ring-accent");
            return;
        }

        fromRow.value = selected.row;
        fromCol.value = selected.col;
        toRow.value = row;
        toCol.value = col;
        form.submit();
    });
})();
