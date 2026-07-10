(function () {
    var W = 350;
    var H = 350;
    var MAX_ITER = 60;
    var CENTER_X = -0.743643887037151;
    var CENTER_Y = 0.13182590420533;
    var ZOOM_FACTOR = 1.02;
    var ZOOM_RESET_THRESHOLD = 1e6;

    var zoom;

    window.setup = function () {
        var canvas = createCanvas(W, H);
        canvas.parent("sketch-container");
        pixelDensity(1);
        zoom = 1;
    };

    function paletteColor(t) {
        return [Math.floor(9 + 246 * t), Math.floor(23 + 130 * (1 - t)), Math.floor(42 + 200 * t)];
    }

    window.draw = function () {
        loadPixels();
        var scale = 3.0 / zoom;

        for (var py = 0; py < H; py++) {
            for (var px = 0; px < W; px++) {
                var x0 = CENTER_X + ((px - W / 2) / W) * scale;
                var y0 = CENTER_Y + ((py - H / 2) / H) * scale;
                var x = 0;
                var y = 0;
                var iter = 0;
                while (x * x + y * y <= 4 && iter < MAX_ITER) {
                    var xTemp = x * x - y * y + x0;
                    y = 2 * x * y + y0;
                    x = xTemp;
                    iter++;
                }

                var idx = (px + py * W) * 4;
                if (iter === MAX_ITER) {
                    pixels[idx] = 15;
                    pixels[idx + 1] = 23;
                    pixels[idx + 2] = 42;
                } else {
                    var color = paletteColor(iter / MAX_ITER);
                    pixels[idx] = color[0];
                    pixels[idx + 1] = color[1];
                    pixels[idx + 2] = color[2];
                }
                pixels[idx + 3] = 255;
            }
        }
        updatePixels();

        zoom *= ZOOM_FACTOR;
        if (zoom > ZOOM_RESET_THRESHOLD) zoom = 1;
    };
})();
