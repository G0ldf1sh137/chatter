(function () {
    var COLS = 60;
    var ROWS = 40;
    var CELL_SIZE = 10;
    var UPDATE_EVERY = 10;
    var ALIVE_PROBABILITY = 0.25;

    var grid;
    var frame;
    var paused;

    function makeGrid() {
        var g = [];
        for (var r = 0; r < ROWS; r++) {
            var row = [];
            for (var c = 0; c < COLS; c++) {
                row.push(Math.random() < ALIVE_PROBABILITY ? 1 : 0);
            }
            g.push(row);
        }
        return g;
    }

    function countNeighbors(g, r, c) {
        var count = 0;
        for (var dr = -1; dr <= 1; dr++) {
            for (var dc = -1; dc <= 1; dc++) {
                if (dr === 0 && dc === 0) continue;
                var nr = (r + dr + ROWS) % ROWS;
                var nc = (c + dc + COLS) % COLS;
                count += g[nr][nc];
            }
        }
        return count;
    }

    function step(g) {
        var next = [];
        for (var r = 0; r < ROWS; r++) {
            var row = [];
            for (var c = 0; c < COLS; c++) {
                var alive = g[r][c] === 1;
                var neighbors = countNeighbors(g, r, c);
                var willLive = alive ? (neighbors === 2 || neighbors === 3) : neighbors === 3;
                row.push(willLive ? 1 : 0);
            }
            next.push(row);
        }
        return next;
    }

    window.setup = function () {
        var canvas = createCanvas(COLS * CELL_SIZE, ROWS * CELL_SIZE);
        canvas.parent("sketch-container");
        grid = makeGrid();
        frame = 0;
        paused = false;
    };

    window.draw = function () {
        background(15, 23, 42);

        noStroke();
        fill(96, 165, 250);
        for (var r = 0; r < ROWS; r++) {
            for (var c = 0; c < COLS; c++) {
                if (grid[r][c] === 1) {
                    rect(c * CELL_SIZE, r * CELL_SIZE, CELL_SIZE - 1, CELL_SIZE - 1);
                }
            }
        }

        frame++;
        if (!paused && frame % UPDATE_EVERY === 0) {
            grid = step(grid);
        }
    };

    window.mousePressed = function () {
        if (mouseX < 0 || mouseX > width || mouseY < 0 || mouseY > height) return;
        var c = Math.floor(mouseX / CELL_SIZE);
        var r = Math.floor(mouseY / CELL_SIZE);
        if (r >= 0 && r < ROWS && c >= 0 && c < COLS) {
            grid[r][c] = grid[r][c] === 1 ? 0 : 1;
        }
    };

    window.keyPressed = function () {
        if (key === " ") paused = !paused;
    };
})();
