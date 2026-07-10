(function () {
    var CANVAS_W = 320;
    var CANVAS_H = 480;
    var BIRD_SIZE = 24;
    var BIRD_X = 60;
    var GRAVITY = 0.5;
    var FLAP_VELOCITY = -8;
    var PIPE_WIDTH = 50;
    var PIPE_GAP = 130;
    var PIPE_SPACING = 180;
    var SCROLL_SPEED = 2.5;

    var canvas = document.getElementById("board");
    var ctx = canvas.getContext("2d");
    var scoreEl = document.getElementById("score");
    var messageEl = document.getElementById("game-message");
    var newGameBtn = document.getElementById("new-game");
    var finishUrl = canvas.dataset.finishUrl;
    var csrfToken = canvas.dataset.csrfToken;

    var bird, pipes, score, over, rafId;

    function randomGapY() {
        var margin = 60;
        return margin + Math.random() * (CANVAS_H - PIPE_GAP - margin * 2);
    }

    function newGame() {
        bird = { y: CANVAS_H / 2, vy: 0 };
        pipes = [];
        for (var x = CANVAS_W + 100; x < CANVAS_W + 100 + PIPE_SPACING * 4; x += PIPE_SPACING) {
            pipes.push({ x: x, gapY: randomGapY(), passed: false });
        }
        score = 0;
        over = false;
        messageEl.classList.add("hidden");
        if (rafId) cancelAnimationFrame(rafId);
        rafId = requestAnimationFrame(tick);
    }

    function flap() {
        if (over) return;
        bird.vy = FLAP_VELOCITY;
    }

    function update() {
        bird.vy += GRAVITY;
        bird.y += bird.vy;

        for (var i = 0; i < pipes.length; i++) {
            pipes[i].x -= SCROLL_SPEED;
        }
        pipes = pipes.filter(function (p) { return p.x > -PIPE_WIDTH; });
        var rightmost = pipes[pipes.length - 1];
        while (rightmost.x < CANVAS_W + 100 + PIPE_SPACING * 3) {
            var nextX = rightmost.x + PIPE_SPACING;
            rightmost = { x: nextX, gapY: randomGapY(), passed: false };
            pipes.push(rightmost);
        }

        for (var j = 0; j < pipes.length; j++) {
            var p = pipes[j];
            if (!p.passed && p.x + PIPE_WIDTH < BIRD_X) {
                p.passed = true;
                score += 1;
            }
            var overlapsX = BIRD_X + BIRD_SIZE > p.x && BIRD_X < p.x + PIPE_WIDTH;
            if (overlapsX && (bird.y < p.gapY || bird.y + BIRD_SIZE > p.gapY + PIPE_GAP)) {
                gameOver();
                return;
            }
        }

        if (bird.y < 0 || bird.y + BIRD_SIZE > CANVAS_H) {
            gameOver();
        }
    }

    function render() {
        ctx.clearRect(0, 0, CANVAS_W, CANVAS_H);
        var accent = getComputedStyle(document.documentElement).getPropertyValue("--accent").trim() || "#6d5ef8";
        var upvote = getComputedStyle(document.documentElement).getPropertyValue("--upvote").trim() || "#34c77b";

        ctx.fillStyle = upvote;
        for (var i = 0; i < pipes.length; i++) {
            var p = pipes[i];
            ctx.fillRect(p.x, 0, PIPE_WIDTH, p.gapY);
            ctx.fillRect(p.x, p.gapY + PIPE_GAP, PIPE_WIDTH, CANVAS_H - (p.gapY + PIPE_GAP));
        }

        ctx.fillStyle = accent;
        ctx.fillRect(BIRD_X, bird.y, BIRD_SIZE, BIRD_SIZE);

        scoreEl.textContent = score;
    }

    function tick() {
        if (over) return;
        update();
        if (over) return;
        render();
        rafId = requestAnimationFrame(tick);
    }

    function gameOver() {
        over = true;
        messageEl.textContent = "Game over! Score: " + score;
        messageEl.classList.remove("hidden");
        fetch(finishUrl, {
            method: "POST",
            headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
            body: JSON.stringify({ score: score }),
        });
    }

    document.addEventListener("keydown", function (event) {
        if (event.key === " " || event.key === "ArrowUp") {
            flap();
            event.preventDefault();
        }
    });
    canvas.addEventListener("mousedown", flap);
    canvas.addEventListener("touchstart", function (event) {
        flap();
        event.preventDefault();
    });

    newGameBtn.addEventListener("click", newGame);

    newGame();
})();
