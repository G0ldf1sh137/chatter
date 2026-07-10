(function () {
    var NUM_PARTICLES = 300;
    var NOISE_SCALE = 0.01;
    var SPEED = 2;
    var NOISE_Z_STEP = 0.003;
    var REPEL_RADIUS = 150;
    var REPEL_STRENGTH = 3;

    var particles;
    var zOffset;

    function makeParticle() {
        return { x: random(width), y: random(height) };
    }

    window.setup = function () {
        var canvas = createCanvas(600, 500);
        canvas.parent("sketch-container");
        background(15, 23, 42);
        particles = [];
        for (var i = 0; i < NUM_PARTICLES; i++) particles.push(makeParticle());
        zOffset = 0;
    };

    window.draw = function () {
        noStroke();
        fill(15, 23, 42, 15);
        rect(0, 0, width, height);

        stroke(96, 165, 250, 180);
        strokeWeight(1.5);

        for (var i = 0; i < particles.length; i++) {
            var p = particles[i];
            var angle = noise(p.x * NOISE_SCALE, p.y * NOISE_SCALE, zOffset) * Math.PI * 4;
            var vx = Math.cos(angle) * SPEED;
            var vy = Math.sin(angle) * SPEED;

            if (mouseIsPressed && mouseX >= 0 && mouseX <= width && mouseY >= 0 && mouseY <= height) {
                var dx = p.x - mouseX;
                var dy = p.y - mouseY;
                var d = Math.sqrt(dx * dx + dy * dy) || 1;
                if (d < REPEL_RADIUS) {
                    vx += (dx / d) * REPEL_STRENGTH;
                    vy += (dy / d) * REPEL_STRENGTH;
                }
            }

            var prevX = p.x;
            var prevY = p.y;
            p.x += vx;
            p.y += vy;

            if (p.x < 0 || p.x > width || p.y < 0 || p.y > height) {
                p.x = random(width);
                p.y = random(height);
                prevX = p.x;
                prevY = p.y;
            }

            line(prevX, prevY, p.x, p.y);
        }

        zOffset += NOISE_Z_STEP;
    };
})();
