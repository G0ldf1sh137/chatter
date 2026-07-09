(function () {
    var SIZE = 4;
    var board = document.getElementById("board");
    var scoreEl = document.getElementById("score");
    var messageEl = document.getElementById("game-message");
    var newGameBtn = document.getElementById("new-game");
    var finishUrl = board.dataset.finishUrl;
    var csrfToken = board.dataset.csrfToken;

    var grid, score, over;

    function emptyGrid() {
        var g = [];
        for (var r = 0; r < SIZE; r++) g.push([0, 0, 0, 0]);
        return g;
    }

    function randomEmptyCell(g) {
        var empties = [];
        for (var r = 0; r < SIZE; r++) {
            for (var c = 0; c < SIZE; c++) {
                if (g[r][c] === 0) empties.push([r, c]);
            }
        }
        if (empties.length === 0) return null;
        return empties[Math.floor(Math.random() * empties.length)];
    }

    function spawnTile(g) {
        var cell = randomEmptyCell(g);
        if (!cell) return;
        g[cell[0]][cell[1]] = Math.random() < 0.9 ? 2 : 4;
    }

    function newGame() {
        grid = emptyGrid();
        score = 0;
        over = false;
        spawnTile(grid);
        spawnTile(grid);
        messageEl.classList.add("hidden");
        render();
    }

    function tileClass(value) {
        // Each power-of-two tier gets its own shade, cycling through the
        // theme's four accent colors (blue, amber, rose, green) rather than
        // inventing new hardcoded colors - solid tones at each family's
        // final tier, lighter opacity variants leading into it.
        if (value >= 4096) return "bg-accent text-accent-fg font-black";
        if (value >= 2048) return "bg-karma text-white font-black";
        if (value >= 1024) return "bg-karma/80 text-white font-black";
        if (value >= 512) return "bg-downvote text-white font-black";
        if (value >= 256) return "bg-downvote/70 text-white font-black";
        if (value >= 128) return "bg-upvote text-white font-black";
        if (value >= 64) return "bg-upvote/60 text-fg font-black";
        if (value >= 32) return "bg-accent/70 text-white font-black";
        if (value >= 16) return "bg-accent/45 text-fg font-black";
        if (value >= 8) return "bg-accent/25 text-fg font-black";
        if (value >= 4) return "bg-accent/10 text-fg";
        return "bg-surface text-fg border border-border";
    }

    function render() {
        board.innerHTML = "";
        for (var r = 0; r < SIZE; r++) {
            for (var c = 0; c < SIZE; c++) {
                var value = grid[r][c];
                var cell = document.createElement("div");
                cell.className = "flex aspect-square items-center justify-center rounded-lg text-lg font-bold " + tileClass(value);
                cell.textContent = value || "";
                board.appendChild(cell);
            }
        }
        scoreEl.textContent = score;
    }

    function slideRowLeft(row) {
        var nonZero = row.filter(function (v) { return v !== 0; });
        var merged = [];
        var gained = 0;
        for (var i = 0; i < nonZero.length; i++) {
            if (i + 1 < nonZero.length && nonZero[i] === nonZero[i + 1]) {
                var value = nonZero[i] * 2;
                merged.push(value);
                gained += value;
                i++;
            } else {
                merged.push(nonZero[i]);
            }
        }
        while (merged.length < SIZE) merged.push(0);
        return { row: merged, gained: gained };
    }

    function rotateClockwise(g) {
        var result = emptyGrid();
        for (var r = 0; r < SIZE; r++) {
            for (var c = 0; c < SIZE; c++) {
                result[c][SIZE - 1 - r] = g[r][c];
            }
        }
        return result;
    }

    function move(direction) {
        var rotations = { left: 0, down: 1, right: 2, up: 3 }[direction];

        var g = grid;
        for (var i = 0; i < rotations; i++) g = rotateClockwise(g);

        var moved = false;
        var gained = 0;
        var newGrid = g.map(function (row) {
            var result = slideRowLeft(row);
            if (result.row.join(",") !== row.join(",")) moved = true;
            gained += result.gained;
            return result.row;
        });

        var backRotations = (4 - rotations) % 4;
        for (var j = 0; j < backRotations; j++) newGrid = rotateClockwise(newGrid);

        if (moved) {
            grid = newGrid;
            score += gained;
            spawnTile(grid);
            render();
            checkGameOver();
        }
    }

    function canMove(g) {
        for (var r = 0; r < SIZE; r++) {
            for (var c = 0; c < SIZE; c++) {
                if (g[r][c] === 0) return true;
                if (c + 1 < SIZE && g[r][c] === g[r][c + 1]) return true;
                if (r + 1 < SIZE && g[r][c] === g[r + 1][c]) return true;
            }
        }
        return false;
    }

    function highestTile(g) {
        var max = 0;
        for (var r = 0; r < SIZE; r++) {
            for (var c = 0; c < SIZE; c++) {
                if (g[r][c] > max) max = g[r][c];
            }
        }
        return max;
    }

    function checkGameOver() {
        if (over || canMove(grid)) return;
        over = true;
        var highest = highestTile(grid);
        messageEl.textContent = "Game over! Final score: " + score;
        messageEl.classList.remove("hidden");
        fetch(finishUrl, {
            method: "POST",
            headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
            body: JSON.stringify({ score: score, highest_tile: highest }),
        });
    }

    document.addEventListener("keydown", function (event) {
        var map = { ArrowLeft: "left", ArrowRight: "right", ArrowUp: "up", ArrowDown: "down" };
        var direction = map[event.key];
        if (!direction || over) return;
        event.preventDefault();
        move(direction);
    });

    newGameBtn.addEventListener("click", newGame);

    newGame();
})();
