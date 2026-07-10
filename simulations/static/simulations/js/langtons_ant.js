(function () {
    var COLS = 100;
    var ROWS = 100;
    var CELL_SIZE = 5;
    var STEPS_PER_FRAME = 20;

    var grid;
    var antX, antY, antDir;
    var paused;

    window.setup = function () {
        var canvas = createCanvas(COLS * CELL_SIZE, ROWS * CELL_SIZE);
        canvas.parent("sketch-container");
        grid = [];
        for (var r = 0; r < ROWS; r++) {
            grid.push(new Array(COLS).fill(0));
        }
        antX = Math.floor(COLS / 2);
        antY = Math.floor(ROWS / 2);
        antDir = 0;
        paused = false;
    };

    function step() {
        var cell = grid[antY][antX];
        if (cell === 0) {
            antDir = (antDir + 1) % 4;
            grid[antY][antX] = 1;
        } else {
            antDir = (antDir + 3) % 4;
            grid[antY][antX] = 0;
        }

        if (antDir === 0) antY -= 1;
        else if (antDir === 1) antX += 1;
        else if (antDir === 2) antY += 1;
        else antX -= 1;

        antX = (antX + COLS) % COLS;
        antY = (antY + ROWS) % ROWS;
    }

    window.draw = function () {
        if (!paused) {
            for (var i = 0; i < STEPS_PER_FRAME; i++) step();
        }

        background(15, 23, 42);
        noStroke();
        fill(96, 165, 250);
        for (var r = 0; r < ROWS; r++) {
            for (var c = 0; c < COLS; c++) {
                if (grid[r][c] === 1) {
                    rect(c * CELL_SIZE, r * CELL_SIZE, CELL_SIZE, CELL_SIZE);
                }
            }
        }

        fill(250, 204, 21);
        rect(antX * CELL_SIZE, antY * CELL_SIZE, CELL_SIZE, CELL_SIZE);
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
