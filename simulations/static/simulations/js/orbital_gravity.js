(function () {
    var G = 1;
    var SUN_MASS = 10000;
    var TRAIL_LENGTH = 200;

    var sun, planet, trail;

    window.setup = function () {
        var canvas = createCanvas(500, 500);
        canvas.parent("sketch-container");
        sun = { x: width / 2, y: height / 2 };
        planet = { x: width / 2 + 150, y: height / 2, vx: 0, vy: 7.5 };
        trail = [];
    };

    window.draw = function () {
        background(15, 23, 42);

        var dx = sun.x - planet.x;
        var dy = sun.y - planet.y;
        var distSq = dx * dx + dy * dy;
        var dist = Math.sqrt(distSq);
        var accel = (G * SUN_MASS) / distSq;
        planet.vx += (accel * dx) / dist;
        planet.vy += (accel * dy) / dist;
        planet.x += planet.vx;
        planet.y += planet.vy;

        trail.push({ x: planet.x, y: planet.y });
        if (trail.length > TRAIL_LENGTH) trail.shift();

        noStroke();
        fill(250, 204, 21);
        circle(sun.x, sun.y, 36);

        noFill();
        stroke(96, 165, 250, 120);
        strokeWeight(2);
        beginShape();
        for (var i = 0; i < trail.length; i++) vertex(trail[i].x, trail[i].y);
        endShape();

        noStroke();
        fill(96, 165, 250);
        circle(planet.x, planet.y, 16);
    };
})();
