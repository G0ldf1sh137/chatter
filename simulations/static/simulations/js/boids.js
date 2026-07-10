(function () {
    var NUM_BOIDS = 80;
    var MAX_SPEED = 3;
    var MAX_FORCE = 0.1;
    var PERCEPTION_RADIUS = 50;
    var SEPARATION_RADIUS = 25;

    var boids;

    window.setup = function () {
        var canvas = createCanvas(600, 500);
        canvas.parent("sketch-container");
        boids = [];
        for (var i = 0; i < NUM_BOIDS; i++) {
            boids.push({
                x: random(width),
                y: random(height),
                vx: random(-MAX_SPEED, MAX_SPEED),
                vy: random(-MAX_SPEED, MAX_SPEED),
            });
        }
    };

    function limitVector(v, max) {
        var mag = Math.sqrt(v.x * v.x + v.y * v.y);
        if (mag > max) {
            v.x = (v.x / mag) * max;
            v.y = (v.y / mag) * max;
        }
        return v;
    }

    function computeSteering(boid) {
        var sepX = 0, sepY = 0, sepCount = 0;
        var aliX = 0, aliY = 0, aliCount = 0;
        var cohX = 0, cohY = 0, cohCount = 0;

        for (var i = 0; i < boids.length; i++) {
            var other = boids[i];
            if (other === boid) continue;
            var dx = other.x - boid.x;
            var dy = other.y - boid.y;
            var dist = Math.sqrt(dx * dx + dy * dy);

            if (dist < SEPARATION_RADIUS && dist > 0) {
                sepX -= dx / dist;
                sepY -= dy / dist;
                sepCount++;
            }
            if (dist < PERCEPTION_RADIUS) {
                aliX += other.vx;
                aliY += other.vy;
                aliCount++;
                cohX += other.x;
                cohY += other.y;
                cohCount++;
            }
        }

        var steer = { x: 0, y: 0 };

        if (sepCount > 0) {
            steer.x += (sepX / sepCount) * 1.5;
            steer.y += (sepY / sepCount) * 1.5;
        }
        if (aliCount > 0) {
            steer.x += (aliX / aliCount - boid.vx) * 0.1;
            steer.y += (aliY / aliCount - boid.vy) * 0.1;
        }
        if (cohCount > 0) {
            steer.x += (cohX / cohCount - boid.x) * 0.01;
            steer.y += (cohY / cohCount - boid.y) * 0.01;
        }

        return limitVector(steer, MAX_FORCE);
    }

    window.draw = function () {
        background(15, 23, 42);

        for (var i = 0; i < boids.length; i++) {
            var boid = boids[i];
            var steer = computeSteering(boid);
            boid.vx += steer.x;
            boid.vy += steer.y;

            var velocity = limitVector({ x: boid.vx, y: boid.vy }, MAX_SPEED);
            boid.vx = velocity.x;
            boid.vy = velocity.y;

            boid.x += boid.vx;
            boid.y += boid.vy;

            if (boid.x < 0) boid.x += width;
            if (boid.x > width) boid.x -= width;
            if (boid.y < 0) boid.y += height;
            if (boid.y > height) boid.y -= height;
        }

        noStroke();
        fill(96, 165, 250);
        for (var j = 0; j < boids.length; j++) {
            var b = boids[j];
            push();
            translate(b.x, b.y);
            rotate(Math.atan2(b.vy, b.vx));
            triangle(-6, -4, -6, 4, 8, 0);
            pop();
        }
    };
})();
