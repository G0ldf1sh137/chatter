(function () {
    var GRID_SIZE = 20;
    var START_TICK_MS = 150;
    var MIN_TICK_MS = 60;
    var TICK_DECREASE_MS = 3;

    var board = document.getElementById("board");
    var scoreEl = document.getElementById("score");
    var messageEl = document.getElementById("game-message");
    var newGameBtn = document.getElementById("new-game");
    var finishUrl = board.dataset.finishUrl;
    var csrfToken = board.dataset.csrfToken;

    var REVERSE = { up: "down", down: "up", left: "right", right: "left" };
    var DELTA = {
        up: { r: -1, c: 0 },
        down: { r: 1, c: 0 },
        left: { r: 0, c: -1 },
        right: { r: 0, c: 1 },
    };

    var snake, direction, nextDirection, food, score, tickMs, over, timeoutId;

    function randomEmptyCell(occupied) {
        var empties = [];
        for (var r = 0; r < GRID_SIZE; r++) {
            for (var c = 0; c < GRID_SIZE; c++) {
                if (!occupied.has(r + "," + c)) empties.push({ r: r, c: c });
            }
        }
        if (empties.length === 0) return null;
        return empties[Math.floor(Math.random() * empties.length)];
    }

    function snakeCellSet() {
        var set = new Set();
        for (var i = 0; i < snake.length; i++) set.add(snake[i].r + "," + snake[i].c);
        return set;
    }

    function newGame() {
        snake = [{ r: 10, c: 10 }, { r: 10, c: 9 }, { r: 10, c: 8 }];
        direction = "right";
        nextDirection = "right";
        score = 0;
        tickMs = START_TICK_MS;
        over = false;
        food = randomEmptyCell(snakeCellSet());
        messageEl.classList.add("hidden");
        render();
        if (timeoutId) clearTimeout(timeoutId);
        timeoutId = setTimeout(tick, tickMs);
    }

    function render() {
        board.innerHTML = "";
        var cells = snakeCellSet();
        for (var r = 0; r < GRID_SIZE; r++) {
            for (var c = 0; c < GRID_SIZE; c++) {
                var cell = document.createElement("div");
                var isHead = snake[0].r === r && snake[0].c === c;
                var isFood = food && food.r === r && food.c === c;
                var className = "aspect-square rounded-sm ";
                if (isHead) className += "bg-accent";
                else if (cells.has(r + "," + c)) className += "bg-upvote";
                else if (isFood) className += "bg-downvote";
                else className += "bg-surface-hover";
                cell.className = className;
                board.appendChild(cell);
            }
        }
        scoreEl.textContent = score;
    }

    function tick() {
        direction = nextDirection;
        var delta = DELTA[direction];
        var head = snake[0];
        var newHead = { r: head.r + delta.r, c: head.c + delta.c };

        if (newHead.r < 0 || newHead.r >= GRID_SIZE || newHead.c < 0 || newHead.c >= GRID_SIZE) {
            return gameOver();
        }
        var eating = food && newHead.r === food.r && newHead.c === food.c;
        // The tail cell vacates this tick unless we're eating (snake grows
        // and keeps its tail), so moving into it is only a collision when eating.
        var checkSegments = eating ? snake : snake.slice(0, -1);
        var collidesWithSelf = checkSegments.some(function (s) {
            return s.r === newHead.r && s.c === newHead.c;
        });
        if (collidesWithSelf) {
            return gameOver();
        }

        snake.unshift(newHead);
        if (eating) {
            score++;
            tickMs = Math.max(MIN_TICK_MS, tickMs - TICK_DECREASE_MS);
            food = randomEmptyCell(snakeCellSet());
        } else {
            snake.pop();
        }

        render();
        timeoutId = setTimeout(tick, tickMs);
    }

    function gameOver() {
        over = true;
        messageEl.textContent = "Game over! Final score: " + score;
        messageEl.classList.remove("hidden");
        fetch(finishUrl, {
            method: "POST",
            headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
            body: JSON.stringify({ score: score }),
        });
    }

    document.addEventListener("keydown", function (event) {
        var map = { ArrowLeft: "left", ArrowRight: "right", ArrowUp: "up", ArrowDown: "down" };
        var proposed = map[event.key];
        if (!proposed || over) return;
        event.preventDefault();
        if (REVERSE[proposed] === direction) return;
        nextDirection = proposed;
    });

    newGameBtn.addEventListener("click", newGame);

    newGame();
})();
