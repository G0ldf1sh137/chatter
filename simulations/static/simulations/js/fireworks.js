(function () {
    var GRAVITY = 0.05;
    var LAUNCH_INTERVAL = 60;
    var PARTICLES_PER_EXPLOSION = 60;

    var rockets;
    var particles;
    var frameCounter;

    function makeRocket() {
        return {
            x: random(width * 0.2, width * 0.8),
            y: height,
            vx: random(-0.5, 0.5),
            vy: random(-9, -7),
            hue: random(360),
        };
    }

    function explode(rocket) {
        for (var i = 0; i < PARTICLES_PER_EXPLOSION; i++) {
            var angle = random(TWO_PI);
            var speed = random(1, 5);
            particles.push({
                x: rocket.x,
                y: rocket.y,
                vx: Math.cos(angle) * speed,
                vy: Math.sin(angle) * speed,
                hue: rocket.hue,
                life: 255,
            });
        }
    }

    window.setup = function () {
        var canvas = createCanvas(600, 500);
        canvas.parent("sketch-container");
        colorMode(HSB, 360, 100, 100, 255);
        rockets = [];
        particles = [];
        frameCounter = 0;
    };

    window.draw = function () {
        background(220, 60, 8, 60);

        frameCounter++;
        if (frameCounter % LAUNCH_INTERVAL === 0) {
            rockets.push(makeRocket());
        }

        noStroke();

        for (var i = rockets.length - 1; i >= 0; i--) {
            var r = rockets[i];
            r.vy += GRAVITY;
            r.x += r.vx;
            r.y += r.vy;

            fill(r.hue, 80, 100);
            circle(r.x, r.y, 4);

            if (r.vy >= 0) {
                explode(r);
                rockets.splice(i, 1);
            }
        }

        for (var j = particles.length - 1; j >= 0; j--) {
            var p = particles[j];
            p.vy += GRAVITY;
            p.vx *= 0.98;
            p.vy *= 0.98;
            p.x += p.vx;
            p.y += p.vy;
            p.life -= 4;

            if (p.life <= 0) {
                particles.splice(j, 1);
                continue;
            }

            fill(p.hue, 80, 100, p.life);
            circle(p.x, p.y, 3);
        }
    };
})();
