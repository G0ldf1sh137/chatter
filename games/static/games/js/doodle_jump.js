(function () {
    var CANVAS_W = 320;
    var CANVAS_H = 480;
    var PLAYER_W = 32;
    var PLAYER_H = 32;
    var PLATFORM_W = 60;
    var PLATFORM_H = 10;
    var GRAVITY = 0.35;
    var JUMP_VELOCITY = -9.5;
    var MOVE_SPEED = 4;
    var SCROLL_THRESHOLD = CANVAS_H * 0.4;
    var MIN_GAP = 60;
    var MAX_GAP = 100;

    var canvas = document.getElementById("board");
    var ctx = canvas.getContext("2d");
    var scoreEl = document.getElementById("score");
    var messageEl = document.getElementById("game-message");
    var newGameBtn = document.getElementById("new-game");
    var finishUrl = canvas.dataset.finishUrl;
    var csrfToken = canvas.dataset.csrfToken;

    var player, platforms, keys, height, over, rafId;

    function randomPlatform(y) {
        return { x: Math.random() * (CANVAS_W - PLATFORM_W), y: y, w: PLATFORM_W };
    }

    function newGame() {
        player = { x: CANVAS_W / 2 - PLAYER_W / 2, y: CANVAS_H - 80, vy: JUMP_VELOCITY };
        platforms = [];
        var y = CANVAS_H - 20;
        while (y > -20) {
            platforms.push(randomPlatform(y));
            y -= MIN_GAP + Math.random() * (MAX_GAP - MIN_GAP);
        }
        keys = { left: false, right: false };
        height = 0;
        over = false;
        messageEl.classList.add("hidden");
        if (rafId) cancelAnimationFrame(rafId);
        rafId = requestAnimationFrame(tick);
    }

    function update() {
        if (keys.left) player.x -= MOVE_SPEED;
        if (keys.right) player.x += MOVE_SPEED;
        if (player.x < -PLAYER_W) player.x = CANVAS_W;
        if (player.x > CANVAS_W) player.x = -PLAYER_W;

        player.vy += GRAVITY;
        player.y += player.vy;

        if (player.vy > 0) {
            for (var i = 0; i < platforms.length; i++) {
                var p = platforms[i];
                var footBefore = player.y - player.vy + PLAYER_H;
                var footAfter = player.y + PLAYER_H;
                var overlapsX = player.x + PLAYER_W > p.x && player.x < p.x + p.w;
                if (overlapsX && footBefore <= p.y && footAfter >= p.y) {
                    player.y = p.y - PLAYER_H;
                    player.vy = JUMP_VELOCITY;
                    break;
                }
            }
        }

        if (player.y < SCROLL_THRESHOLD) {
            var delta = SCROLL_THRESHOLD - player.y;
            player.y = SCROLL_THRESHOLD;
            height += delta;
            for (var j = 0; j < platforms.length; j++) platforms[j].y += delta;
        }

        var highestY = CANVAS_H;
        for (var k = 0; k < platforms.length; k++) {
            if (platforms[k].y < highestY) highestY = platforms[k].y;
        }
        platforms = platforms.filter(function (p) { return p.y < CANVAS_H; });
        while (platforms.length < 12) {
            highestY -= MIN_GAP + Math.random() * (MAX_GAP - MIN_GAP);
            platforms.push(randomPlatform(highestY));
        }

        if (player.y > CANVAS_H) {
            gameOver();
        }
    }

    function render() {
        ctx.clearRect(0, 0, CANVAS_W, CANVAS_H);
        var accent = getComputedStyle(document.documentElement).getPropertyValue("--accent").trim() || "#6d5ef8";
        var upvote = getComputedStyle(document.documentElement).getPropertyValue("--upvote").trim() || "#34c77b";

        ctx.fillStyle = upvote;
        for (var i = 0; i < platforms.length; i++) {
            var p = platforms[i];
            ctx.fillRect(p.x, p.y, p.w, PLATFORM_H);
        }

        ctx.fillStyle = accent;
        ctx.fillRect(player.x, player.y, PLAYER_W, PLAYER_H);

        scoreEl.textContent = Math.floor(height);
    }

    function tick() {
        if (over) return;
        update();
        render();
        rafId = requestAnimationFrame(tick);
    }

    function gameOver() {
        over = true;
        var score = Math.floor(height);
        messageEl.textContent = "Game over! Height: " + score;
        messageEl.classList.remove("hidden");
        fetch(finishUrl, {
            method: "POST",
            headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
            body: JSON.stringify({ score: score }),
        });
    }

    document.addEventListener("keydown", function (event) {
        if (event.key === "ArrowLeft") { keys.left = true; event.preventDefault(); }
        if (event.key === "ArrowRight") { keys.right = true; event.preventDefault(); }
    });
    document.addEventListener("keyup", function (event) {
        if (event.key === "ArrowLeft") keys.left = false;
        if (event.key === "ArrowRight") keys.right = false;
    });

    newGameBtn.addEventListener("click", newGame);

    newGame();
})();
