(function () {
    var GRAVITY = 0.5;
    var DAMPING = 0.85;
    var RADIUS = 24;

    var x, y, vx, vy;

    window.setup = function () {
        var canvas = createCanvas(500, 400);
        canvas.parent("sketch-container");
        x = width / 2;
        y = 40;
        vx = 3.5;
        vy = 0;
    };

    window.draw = function () {
        background(15, 23, 42);

        vy += GRAVITY;
        x += vx;
        y += vy;

        if (x < RADIUS) { x = RADIUS; vx *= -1; }
        if (x > width - RADIUS) { x = width - RADIUS; vx *= -1; }
        if (y > height - RADIUS) { y = height - RADIUS; vy *= -DAMPING; }

        noStroke();
        fill(77, 127, 255);
        circle(x, y, RADIUS * 2);
    };
})();
