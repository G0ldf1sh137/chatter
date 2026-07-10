(function () {
    var COLS = 10;
    var VISIBLE_ROWS = 20;
    var BUFFER_ROWS = 2;
    var TOTAL_ROWS = VISIBLE_ROWS + BUFFER_ROWS;
    var START_TICK_MS = 800;
    var MIN_TICK_MS = 120;
    var SPEED_STEP_MS = 60;
    var LINES_PER_LEVEL = 10;
    var LINE_SCORE = { 1: 100, 2: 300, 3: 500, 4: 800 };

    // Reference shape data (four rotation states each, as [row, col] offsets
    // in a 4x4 box) - this is universal, exactly-documented Tetris data, so
    // it's hardcoded rather than generated the way Nine Men's Morris'
    // adjacency table is, since a rotation-generating function would be more
    // complexity than the data it saves.
    var SHAPES = {
        I: [
            [[1, 0], [1, 1], [1, 2], [1, 3]],
            [[0, 2], [1, 2], [2, 2], [3, 2]],
            [[2, 0], [2, 1], [2, 2], [2, 3]],
            [[0, 1], [1, 1], [2, 1], [3, 1]],
        ],
        O: [
            [[0, 1], [0, 2], [1, 1], [1, 2]],
            [[0, 1], [0, 2], [1, 1], [1, 2]],
            [[0, 1], [0, 2], [1, 1], [1, 2]],
            [[0, 1], [0, 2], [1, 1], [1, 2]],
        ],
        T: [
            [[0, 1], [1, 0], [1, 1], [1, 2]],
            [[0, 1], [1, 1], [1, 2], [2, 1]],
            [[1, 0], [1, 1], [1, 2], [2, 1]],
            [[0, 1], [1, 0], [1, 1], [2, 1]],
        ],
        S: [
            [[0, 1], [0, 2], [1, 0], [1, 1]],
            [[0, 1], [1, 1], [1, 2], [2, 2]],
            [[1, 1], [1, 2], [2, 0], [2, 1]],
            [[0, 0], [1, 0], [1, 1], [2, 1]],
        ],
        Z: [
            [[0, 0], [0, 1], [1, 1], [1, 2]],
            [[0, 2], [1, 1], [1, 2], [2, 1]],
            [[1, 0], [1, 1], [2, 1], [2, 2]],
            [[0, 1], [1, 0], [1, 1], [2, 0]],
        ],
        J: [
            [[0, 0], [1, 0], [1, 1], [1, 2]],
            [[0, 1], [0, 2], [1, 1], [2, 1]],
            [[1, 0], [1, 1], [1, 2], [2, 2]],
            [[0, 1], [1, 1], [2, 0], [2, 1]],
        ],
        L: [
            [[0, 2], [1, 0], [1, 1], [1, 2]],
            [[0, 1], [1, 1], [2, 1], [2, 2]],
            [[1, 0], [1, 1], [1, 2], [2, 0]],
            [[0, 0], [0, 1], [1, 1], [2, 1]],
        ],
    };
    // Fixed per-piece colors, like Checkers'/Othello's literal black/white
    // pieces - these identify the piece, they're not theme UI chrome, so
    // they stay constant across the light/dark toggle.
    var COLORS = {
        I: "#22d3ee", O: "#facc15", T: "#a855f7", S: "#4ade80",
        Z: "#f87171", J: "#60a5fa", L: "#fb923c",
    };
    var TYPES = Object.keys(SHAPES);

    var board = document.getElementById("board");
    var nextEl = document.getElementById("next-piece");
    var holdEl = document.getElementById("hold-piece");
    var scoreEl = document.getElementById("score");
    var levelEl = document.getElementById("level");
    var messageEl = document.getElementById("game-message");
    var newGameBtn = document.getElementById("new-game");
    var finishUrl = board.dataset.finishUrl;
    var csrfToken = board.dataset.csrfToken;

    var grid, activePiece, nextType, heldType, canHold, score, linesCleared, level, tickMs, over, timeoutId, bag;

    // 7-bag randomizer: deal all 7 pieces in a shuffled order before
    // reshuffling a fresh bag, so every piece appears exactly once per 7
    // draws - avoids the long droughts/streaks a plain per-draw random pick
    // can produce.
    function nextFromBag() {
        if (bag.length === 0) {
            bag = TYPES.slice();
            for (var i = bag.length - 1; i > 0; i--) {
                var j = Math.floor(Math.random() * (i + 1));
                var tmp = bag[i]; bag[i] = bag[j]; bag[j] = tmp;
            }
        }
        return bag.pop();
    }

    function cellsFor(piece) {
        return SHAPES[piece.type][piece.rotation].map(function (offset) {
            return { r: piece.row + offset[0], c: piece.col + offset[1] };
        });
    }

    function collides(candidate) {
        return cellsFor(candidate).some(function (cell) {
            if (cell.c < 0 || cell.c >= COLS || cell.r >= TOTAL_ROWS) return true;
            if (cell.r < 0) return false;
            return grid[cell.r][cell.c] !== null;
        });
    }

    function emptyGrid() {
        var rows = [];
        for (var r = 0; r < TOTAL_ROWS; r++) rows.push(new Array(COLS).fill(null));
        return rows;
    }

    function spawnNext() {
        activePiece = { type: nextType, rotation: 0, row: 0, col: 3 };
        nextType = nextFromBag();
        if (collides(activePiece)) gameOver();
    }

    function newGame() {
        grid = emptyGrid();
        score = 0;
        linesCleared = 0;
        level = 1;
        tickMs = START_TICK_MS;
        over = false;
        heldType = null;
        canHold = true;
        bag = [];
        nextType = nextFromBag();
        spawnNext();
        messageEl.classList.add("hidden");
        render();
        if (timeoutId) clearTimeout(timeoutId);
        timeoutId = setTimeout(tick, tickMs);
    }

    function move(dr, dc) {
        var candidate = { type: activePiece.type, rotation: activePiece.rotation, row: activePiece.row + dr, col: activePiece.col + dc };
        if (collides(candidate)) return false;
        activePiece = candidate;
        return true;
    }

    function rotateCW() {
        var candidate = { type: activePiece.type, rotation: (activePiece.rotation + 1) % 4, row: activePiece.row, col: activePiece.col };
        if (!collides(candidate)) activePiece = candidate;
    }

    function rotateCCW() {
        var candidate = { type: activePiece.type, rotation: (activePiece.rotation + 3) % 4, row: activePiece.row, col: activePiece.col };
        if (!collides(candidate)) activePiece = candidate;
    }

    function holdPiece() {
        if (!canHold) return;
        if (heldType === null) {
            heldType = activePiece.type;
            spawnNext();
        } else {
            var swapType = activePiece.type;
            activePiece = { type: heldType, rotation: 0, row: 0, col: 3 };
            heldType = swapType;
            if (collides(activePiece)) gameOver();
        }
        canHold = false;
    }

    function clearLines() {
        var fullRows = [];
        for (var r = 0; r < TOTAL_ROWS; r++) {
            if (grid[r].every(function (cell) { return cell !== null; })) fullRows.push(r);
        }
        if (fullRows.length === 0) return;
        fullRows.forEach(function (r) { grid.splice(r, 1); });
        for (var i = 0; i < fullRows.length; i++) grid.unshift(new Array(COLS).fill(null));
        linesCleared += fullRows.length;
        score += (LINE_SCORE[fullRows.length] || LINE_SCORE[4]) * level;
        level = Math.floor(linesCleared / LINES_PER_LEVEL) + 1;
        tickMs = Math.max(MIN_TICK_MS, START_TICK_MS - (level - 1) * SPEED_STEP_MS);
    }

    function lockPiece() {
        cellsFor(activePiece).forEach(function (cell) {
            if (cell.r >= 0) grid[cell.r][cell.c] = COLORS[activePiece.type];
        });
        clearLines();
        spawnNext();
        canHold = true;
    }

    function hardDrop() {
        while (move(1, 0)) { /* keep dropping */ }
        lockPiece();
    }

    function render() {
        board.innerHTML = "";
        var activeCells = {};
        cellsFor(activePiece).forEach(function (cell) {
            activeCells[cell.r + "," + cell.c] = COLORS[activePiece.type];
        });
        for (var r = BUFFER_ROWS; r < TOTAL_ROWS; r++) {
            for (var c = 0; c < COLS; c++) {
                var cell = document.createElement("div");
                var color = activeCells[r + "," + c] || grid[r][c];
                cell.className = "aspect-square rounded-sm";
                cell.style.backgroundColor = color || "var(--color-surface-hover)";
                board.appendChild(cell);
            }
        }
        renderNextPreview();
        renderHoldPreview();
        scoreEl.textContent = score;
        levelEl.textContent = level;
    }

    function renderShapePreview(container, type) {
        container.innerHTML = "";
        var cells = {};
        if (type) {
            SHAPES[type][0].forEach(function (offset) { cells[offset[0] + "," + offset[1]] = true; });
        }
        for (var r = 0; r < 4; r++) {
            for (var c = 0; c < 4; c++) {
                var cell = document.createElement("div");
                cell.className = "aspect-square rounded-sm";
                cell.style.backgroundColor = cells[r + "," + c] ? COLORS[type] : "transparent";
                container.appendChild(cell);
            }
        }
    }

    function renderNextPreview() {
        renderShapePreview(nextEl, nextType);
    }

    function renderHoldPreview() {
        if (holdEl) renderShapePreview(holdEl, heldType);
    }

    function tick() {
        if (over) return;
        if (!move(1, 0)) lockPiece();
        render();
        if (!over) timeoutId = setTimeout(tick, tickMs);
    }

    function gameOver() {
        over = true;
        if (timeoutId) clearTimeout(timeoutId);
        messageEl.textContent = "Game over! Score: " + score;
        messageEl.classList.remove("hidden");
        fetch(finishUrl, {
            method: "POST",
            headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
            body: JSON.stringify({ score: score }),
        });
    }

    document.addEventListener("keydown", function (event) {
        if (over) return;
        if (event.key === "ArrowLeft") { move(0, -1); render(); event.preventDefault(); }
        else if (event.key === "ArrowRight") { move(0, 1); render(); event.preventDefault(); }
        else if (event.key === "ArrowDown") { if (!move(1, 0)) lockPiece(); render(); event.preventDefault(); }
        else if (event.key === "ArrowUp") { rotateCW(); render(); event.preventDefault(); }
        else if (event.key === "z" || event.key === "Z") { rotateCCW(); render(); event.preventDefault(); }
        else if (event.key === "x" || event.key === "X") { rotateCW(); render(); event.preventDefault(); }
        else if (event.key === "c" || event.key === "C") { holdPiece(); render(); event.preventDefault(); }
        else if (event.key === " ") { hardDrop(); render(); event.preventDefault(); }
    });

    var btnLeft = document.getElementById("btn-left");
    var btnRight = document.getElementById("btn-right");
    var btnDown = document.getElementById("btn-down");
    var btnRotate = document.getElementById("btn-rotate");
    var btnDrop = document.getElementById("btn-drop");
    var btnHold = document.getElementById("btn-hold");
    if (btnLeft) btnLeft.addEventListener("click", function () { if (!over) { move(0, -1); render(); } });
    if (btnRight) btnRight.addEventListener("click", function () { if (!over) { move(0, 1); render(); } });
    if (btnDown) btnDown.addEventListener("click", function () { if (!over) { if (!move(1, 0)) lockPiece(); render(); } });
    if (btnRotate) btnRotate.addEventListener("click", function () { if (!over) { rotateCW(); render(); } });
    if (btnDrop) btnDrop.addEventListener("click", function () { if (!over) { hardDrop(); render(); } });
    if (btnHold) btnHold.addEventListener("click", function () { if (!over) { holdPiece(); render(); } });

    newGameBtn.addEventListener("click", newGame);

    newGame();
})();
