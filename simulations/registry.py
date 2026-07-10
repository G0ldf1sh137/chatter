# A static, curated list rather than a database model - these are seeded
# example sketches, not user-generated content, so there's no CRUD surface
# or migration needed for them.
SIMULATIONS = [
    {
        "slug": "bouncing-ball",
        "title": "Bouncing Ball",
        "description": "A ball falls under gravity and bounces off the floor and walls, losing a little energy on each bounce.",
        "js_file": "simulations/js/bouncing_ball.js",
    },
    {
        "slug": "orbital-gravity",
        "title": "Orbital Gravity",
        "description": "A planet orbits a fixed sun under simulated Newtonian gravity, tracing out its elliptical path.",
        "js_file": "simulations/js/orbital_gravity.js",
    },
]


def get_simulation(slug):
    return next((simulation for simulation in SIMULATIONS if simulation["slug"] == slug), None)
