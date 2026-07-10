(function () {
    var GRAVITY = 0.5;
    var DAMPING = 0.85;
    var RADIUS = 24;

    var x, y, vx, vy;
    var dragging;

    window.setup = function () {
        var canvas = createCanvas(500, 400);
        canvas.parent("sketch-container");
        x = width / 2;
        y = 40;
        vx = 3.5;
        vy = 0;
        dragging = false;
    };

    window.draw = function () {
        background(15, 23, 42);

        if (!dragging) {
            vy += GRAVITY;
            x += vx;
            y += vy;

            if (x < RADIUS) { x = RADIUS; vx *= -1; }
            if (x > width - RADIUS) { x = width - RADIUS; vx *= -1; }
            if (y > height - RADIUS) { y = height - RADIUS; vy *= -DAMPING; }
        }

        noStroke();
        fill(77, 127, 255);
        circle(x, y, RADIUS * 2);
    };

    window.mousePressed = function () {
        if (mouseX < 0 || mouseX > width || mouseY < 0 || mouseY > height) return;
        if (dist(mouseX, mouseY, x, y) < RADIUS * 1.5) dragging = true;
    };

    window.mouseDragged = function () {
        if (!dragging) return;
        x = constrain(mouseX, RADIUS, width - RADIUS);
        y = constrain(mouseY, RADIUS, height - RADIUS);
    };

    window.mouseReleased = function () {
        if (!dragging) return;
        vx = (mouseX - pmouseX) * 1.5;
        vy = (mouseY - pmouseY) * 1.5;
        dragging = false;
    };
})();
