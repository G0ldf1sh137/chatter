(function () {
    var SIZE = 150;
    var DISPLAY_SIZE = 450;
    var STEPS_PER_FRAME = 12;
    var DIFFUSION_A = 1.0;
    var DIFFUSION_B = 0.5;
    var FEED = 0.055;
    var KILL = 0.062;
    var DT = 1;

    var a, b, nextA, nextB;

    function index(x, y) {
        return ((y + SIZE) % SIZE) * SIZE + ((x + SIZE) % SIZE);
    }

    function seed() {
        a = new Float32Array(SIZE * SIZE).fill(1);
        b = new Float32Array(SIZE * SIZE).fill(0);
        nextA = new Float32Array(SIZE * SIZE);
        nextB = new Float32Array(SIZE * SIZE);

        var cx = SIZE / 2;
        var cy = SIZE / 2;
        var radius = 8;
        for (var y = 0; y < SIZE; y++) {
            for (var x = 0; x < SIZE; x++) {
                if ((x - cx) * (x - cx) + (y - cy) * (y - cy) < radius * radius) {
                    b[index(x, y)] = 1;
                }
            }
        }
    }

    function laplacian(field, x, y) {
        var sum = field[index(x, y)] * -1;
        sum += field[index(x - 1, y)] * 0.2;
        sum += field[index(x + 1, y)] * 0.2;
        sum += field[index(x, y - 1)] * 0.2;
        sum += field[index(x, y + 1)] * 0.2;
        sum += field[index(x - 1, y - 1)] * 0.05;
        sum += field[index(x + 1, y - 1)] * 0.05;
        sum += field[index(x - 1, y + 1)] * 0.05;
        sum += field[index(x + 1, y + 1)] * 0.05;
        return sum;
    }

    function step() {
        for (var y = 0; y < SIZE; y++) {
            for (var x = 0; x < SIZE; x++) {
                var i = index(x, y);
                var av = a[i];
                var bv = b[i];
                var reaction = av * bv * bv;
                var da = DIFFUSION_A * laplacian(a, x, y) - reaction + FEED * (1 - av);
                var db = DIFFUSION_B * laplacian(b, x, y) + reaction - (KILL + FEED) * bv;
                nextA[i] = av + da * DT;
                nextB[i] = bv + db * DT;
            }
        }
        var tmpA = a;
        a = nextA;
        nextA = tmpA;
        var tmpB = b;
        b = nextB;
        nextB = tmpB;
    }

    window.setup = function () {
        pixelDensity(1);
        var canvas = createCanvas(SIZE, SIZE);
        canvas.parent("sketch-container");
        canvas.elt.style.width = DISPLAY_SIZE + "px";
        canvas.elt.style.height = DISPLAY_SIZE + "px";
        seed();
    };

    window.draw = function () {
        for (var s = 0; s < STEPS_PER_FRAME; s++) step();

        loadPixels();
        for (var y = 0; y < SIZE; y++) {
            for (var x = 0; x < SIZE; x++) {
                var i = index(x, y);
                var concentration = a[i] - b[i];
                var t = Math.max(0, Math.min(1, concentration));
                var idx = (x + y * SIZE) * 4;
                pixels[idx] = Math.floor(15 + (96 - 15) * (1 - t));
                pixels[idx + 1] = Math.floor(23 + (165 - 23) * (1 - t));
                pixels[idx + 2] = Math.floor(42 + (250 - 42) * (1 - t));
                pixels[idx + 3] = 255;
            }
        }
        updatePixels();
    };

    function seedAt(gx, gy) {
        var radius = 4;
        for (var dy = -radius; dy <= radius; dy++) {
            for (var dx = -radius; dx <= radius; dx++) {
                if (dx * dx + dy * dy <= radius * radius) {
                    b[index(gx + dx, gy + dy)] = 1;
                }
            }
        }
    }

    window.mousePressed = function () {
        if (mouseX < 0 || mouseX > width || mouseY < 0 || mouseY > height) return;
        seedAt(Math.floor(mouseX), Math.floor(mouseY));
    };

    window.mouseDragged = function () {
        if (mouseX < 0 || mouseX > width || mouseY < 0 || mouseY > height) return;
        seedAt(Math.floor(mouseX), Math.floor(mouseY));
    };
})();
