from django import template

register = template.Library()

# Curated so every pairing looks intentional; picked deterministically per
# username rather than randomly so a user's placeholder avatar is stable.
GRADIENTS = [
    "from-violet-500 to-fuchsia-500",
    "from-sky-500 to-indigo-500",
    "from-emerald-500 to-teal-500",
    "from-amber-500 to-orange-600",
    "from-rose-500 to-pink-600",
    "from-cyan-500 to-blue-600",
    "from-lime-500 to-emerald-600",
    "from-fuchsia-500 to-purple-600",
]


@register.filter
def avatar_gradient(username):
    index = sum(ord(char) for char in username) % len(GRADIENTS)
    return GRADIENTS[index]
