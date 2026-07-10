(function () {
    var G = 9.8;
    var M1 = 1;
    var M2 = 1;
    var L1 = 1;
    var L2 = 1;
    var PIXELS_PER_UNIT = 140;
    var DT = 0.02;
    var STEPS_PER_FRAME = 4;
    var TRAIL_LENGTH = 300;

    var theta1, theta2, omega1, omega2;
    var pivotX, pivotY;
    var trail;
    var draggingBob;

    window.setup = function () {
        var canvas = createCanvas(500, 500);
        canvas.parent("sketch-container");
        pivotX = width / 2;
        pivotY = height / 3;
        theta1 = Math.PI / 2;
        theta2 = Math.PI / 2 + 0.5;
        omega1 = 0;
        omega2 = 0;
        trail = [];
        draggingBob = null;
    };

    function bobPositions() {
        var x1 = pivotX + L1 * PIXELS_PER_UNIT * Math.sin(theta1);
        var y1 = pivotY + L1 * PIXELS_PER_UNIT * Math.cos(theta1);
        var x2 = x1 + L2 * PIXELS_PER_UNIT * Math.sin(theta2);
        var y2 = y1 + L2 * PIXELS_PER_UNIT * Math.cos(theta2);
        return { x1: x1, y1: y1, x2: x2, y2: y2 };
    }

    function step() {
        var num1 = -G * (2 * M1 + M2) * Math.sin(theta1);
        var num2 = -M2 * G * Math.sin(theta1 - 2 * theta2);
        var num3 = -2 * Math.sin(theta1 - theta2) * M2 * (omega2 * omega2 * L2 + omega1 * omega1 * L1 * Math.cos(theta1 - theta2));
        var den1 = L1 * (2 * M1 + M2 - M2 * Math.cos(2 * theta1 - 2 * theta2));
        var alpha1 = (num1 + num2 + num3) / den1;

        var num4 = 2 * Math.sin(theta1 - theta2);
        var num5 = omega1 * omega1 * L1 * (M1 + M2);
        var num6 = G * (M1 + M2) * Math.cos(theta1);
        var num7 = omega2 * omega2 * L2 * M2 * Math.cos(theta1 - theta2);
        var den2 = L2 * (2 * M1 + M2 - M2 * Math.cos(2 * theta1 - 2 * theta2));
        var alpha2 = (num4 * (num5 + num6 + num7)) / den2;

        omega1 += alpha1 * DT;
        omega2 += alpha2 * DT;
        theta1 += omega1 * DT;
        theta2 += omega2 * DT;
    }

    window.draw = function () {
        background(15, 23, 42);

        if (draggingBob === null) {
            for (var s = 0; s < STEPS_PER_FRAME; s++) step();
        }

        var pos = bobPositions();
        var x1 = pos.x1, y1 = pos.y1, x2 = pos.x2, y2 = pos.y2;

        trail.push({ x: x2, y: y2 });
        if (trail.length > TRAIL_LENGTH) trail.shift();

        noFill();
        stroke(96, 165, 250, 120);
        strokeWeight(2);
        beginShape();
        for (var i = 0; i < trail.length; i++) vertex(trail[i].x, trail[i].y);
        endShape();

        stroke(234, 241, 251);
        strokeWeight(2);
        line(pivotX, pivotY, x1, y1);
        line(x1, y1, x2, y2);

        noStroke();
        fill(250, 204, 21);
        circle(pivotX, pivotY, 8);
        fill(96, 165, 250);
        circle(x1, y1, 16);
        circle(x2, y2, 16);
    };

    window.mousePressed = function () {
        if (mouseX < 0 || mouseX > width || mouseY < 0 || mouseY > height) return;
        var pos = bobPositions();
        if (dist(mouseX, mouseY, pos.x2, pos.y2) < 20) {
            draggingBob = 2;
        } else if (dist(mouseX, mouseY, pos.x1, pos.y1) < 20) {
            draggingBob = 1;
        }
    };

    window.mouseDragged = function () {
        if (draggingBob === 1) {
            theta1 = Math.atan2(mouseX - pivotX, mouseY - pivotY);
            omega1 = 0;
        } else if (draggingBob === 2) {
            var pos = bobPositions();
            theta2 = Math.atan2(mouseX - pos.x1, mouseY - pos.y1);
            omega2 = 0;
        }
    };

    window.mouseReleased = function () {
        draggingBob = null;
    };
})();
