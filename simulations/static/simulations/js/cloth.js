(function () {
    var COLS = 20;
    var ROWS = 14;
    var SPACING = 22;
    var GRAVITY = 0.4;
    var DAMPING = 0.98;
    var CONSTRAINT_ITERATIONS = 4;

    var points;
    var constraints;
    var frame;
    var draggedPoint;

    function makePoint(x, y, pinned) {
        return { x: x, y: y, oldX: x, oldY: y, pinned: pinned };
    }

    function index(r, c) {
        return r * COLS + c;
    }

    window.setup = function () {
        var canvas = createCanvas(COLS * SPACING + 40, ROWS * SPACING + 40);
        canvas.parent("sketch-container");

        points = [];
        constraints = [];
        frame = 0;
        draggedPoint = null;

        for (var r = 0; r < ROWS; r++) {
            for (var c = 0; c < COLS; c++) {
                var x = 20 + c * SPACING;
                var y = 20 + r * SPACING;
                var pinned = r === 0 && c % 3 === 0;
                points.push(makePoint(x, y, pinned));
            }
        }

        for (var r2 = 0; r2 < ROWS; r2++) {
            for (var c2 = 0; c2 < COLS; c2++) {
                if (c2 < COLS - 1) {
                    constraints.push({ a: index(r2, c2), b: index(r2, c2 + 1), length: SPACING });
                }
                if (r2 < ROWS - 1) {
                    constraints.push({ a: index(r2, c2), b: index(r2 + 1, c2), length: SPACING });
                }
            }
        }
    };

    function updatePoints() {
        var wind = Math.sin(frame * 0.02) * 0.3;
        for (var i = 0; i < points.length; i++) {
            var p = points[i];
            if (p.pinned || i === draggedPoint) continue;
            var vx = (p.x - p.oldX) * DAMPING;
            var vy = (p.y - p.oldY) * DAMPING;
            p.oldX = p.x;
            p.oldY = p.y;
            p.x += vx + wind;
            p.y += vy + GRAVITY;
        }
    }

    function satisfyConstraints() {
        for (var iter = 0; iter < CONSTRAINT_ITERATIONS; iter++) {
            for (var i = 0; i < constraints.length; i++) {
                var con = constraints[i];
                var a = points[con.a];
                var b = points[con.b];
                var dx = b.x - a.x;
                var dy = b.y - a.y;
                var dist = Math.sqrt(dx * dx + dy * dy) || 0.0001;
                var diff = (dist - con.length) / dist;
                var offsetX = dx * 0.5 * diff;
                var offsetY = dy * 0.5 * diff;

                if (!a.pinned && con.a !== draggedPoint) {
                    a.x += offsetX;
                    a.y += offsetY;
                }
                if (!b.pinned && con.b !== draggedPoint) {
                    b.x -= offsetX;
                    b.y -= offsetY;
                }
            }
        }
    }

    window.draw = function () {
        background(15, 23, 42);

        frame++;
        updatePoints();
        satisfyConstraints();

        stroke(96, 165, 250, 200);
        strokeWeight(1.5);
        for (var i = 0; i < constraints.length; i++) {
            var con = constraints[i];
            var a = points[con.a];
            var b = points[con.b];
            line(a.x, a.y, b.x, b.y);
        }

        noStroke();
        fill(250, 204, 21);
        for (var j = 0; j < points.length; j++) {
            if (points[j].pinned) circle(points[j].x, points[j].y, 6);
        }
    };

    function nearestPointIndex(mx, my) {
        var best = null;
        var bestDist = 15;
        for (var i = 0; i < points.length; i++) {
            var d = dist(mx, my, points[i].x, points[i].y);
            if (d < bestDist) {
                bestDist = d;
                best = i;
            }
        }
        return best;
    }

    window.mousePressed = function () {
        if (mouseX < 0 || mouseX > width || mouseY < 0 || mouseY > height) return;
        var idx = nearestPointIndex(mouseX, mouseY);
        if (idx === null) return;
        if (points[idx].pinned) {
            points[idx].pinned = false;
        } else {
            draggedPoint = idx;
        }
    };

    window.mouseDragged = function () {
        if (draggedPoint === null) return;
        points[draggedPoint].x = mouseX;
        points[draggedPoint].y = mouseY;
        points[draggedPoint].oldX = mouseX;
        points[draggedPoint].oldY = mouseY;
    };

    window.mouseReleased = function () {
        draggedPoint = null;
    };
})();
