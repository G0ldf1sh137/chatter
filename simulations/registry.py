# A static, curated list rather than a database model - these are seeded
# example sketches, not user-generated content, so there's no CRUD surface
# or migration needed for them.
SIMULATIONS = [
    {
        "slug": "bouncing-ball",
        "title": "Bouncing Ball",
        "description": "A ball falls under gravity and bounces off the floor and walls, losing a little energy on each bounce. Drag it and let go to fling it.",
        "js_file": "simulations/js/bouncing_ball.js",
    },
    {
        "slug": "orbital-gravity",
        "title": "Orbital Gravity",
        "description": "A planet orbits a fixed sun under simulated Newtonian gravity, tracing out its elliptical path. Drag the planet and let go to launch it on a new trajectory.",
        "js_file": "simulations/js/orbital_gravity.js",
    },
    {
        "slug": "boids",
        "title": "Boids",
        "description": "A flock of simple agents follows separation, alignment, and cohesion rules to produce emergent flocking behavior. Click to add boids, or hold the mouse down to draw the flock toward it.",
        "js_file": "simulations/js/boids.js",
    },
    {
        "slug": "game-of-life",
        "title": "Game of Life",
        "description": "A grid of cells lives, dies, and reproduces each generation according to Conway's classic four rules. Click a cell to toggle it, or press space to pause.",
        "js_file": "simulations/js/game_of_life.js",
    },
    {
        "slug": "double-pendulum",
        "title": "Double Pendulum",
        "description": "Two connected pendulums swing under gravity, tracing a chaotic path that never quite repeats. Grab either bob and let go to set it swinging from a new position.",
        "js_file": "simulations/js/double_pendulum.js",
    },
    {
        "slug": "flow-field",
        "title": "Flow Field",
        "description": "Hundreds of particles drift along a Perlin noise vector field, leaving faint trails as it slowly shifts. Hold the mouse down to blow them away from the cursor.",
        "js_file": "simulations/js/flow_field.js",
    },
    {
        "slug": "mandelbrot-zoom",
        "title": "Mandelbrot Zoom",
        "description": "A continuous zoom into the Mandelbrot set, recomputed pixel-by-pixel every frame around a fixed point. Click anywhere to recenter and zoom in on that spot.",
        "js_file": "simulations/js/mandelbrot_zoom.js",
    },
    {
        "slug": "langtons-ant",
        "title": "Langton Ant",
        "description": "A single ant flips cells and turns based on one simple rule, eventually building a repeating diagonal highway. Click to paint cells, or press space to pause.",
        "js_file": "simulations/js/langtons_ant.js",
    },
    {
        "slug": "cloth",
        "title": "Cloth Simulation",
        "description": "A pinned grid of points connected by constraints sways under gravity and wind, solved with Verlet integration. Drag any point to tug the cloth, or click a pinned anchor to cut it free.",
        "js_file": "simulations/js/cloth.js",
    },
    {
        "slug": "reaction-diffusion",
        "title": "Reaction-Diffusion",
        "description": "Two virtual chemicals diffuse and react across a grid, forming organic, coral-like Turing patterns. Click or drag to seed new growth wherever you like.",
        "js_file": "simulations/js/reaction_diffusion.js",
    },
    {
        "slug": "fireworks",
        "title": "Fireworks",
        "description": "Rockets launch, arc under gravity, and burst into fading, colorful particle showers. Click anywhere to launch one on demand.",
        "js_file": "simulations/js/fireworks.js",
    },
]


def get_simulation(slug):
    return next((simulation for simulation in SIMULATIONS if simulation["slug"] == slug), None)
