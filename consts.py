# Geiger - shared constants, tunables and tiny helpers.
# Kept in its own small module so app.py and draw.py each compile with a low
# peak memory footprint on the badge (the firmware compiles one module at a
# time; a single large file can run the badge out of RAM at import).

import time

CONFIG_KEY = "geiger_spider"

# --- Tunable game timings (retune on site for the event) --------------------
FEED_COOLDOWN_S = 60.0     # soft cooldown between feeds -> ~1 level/minute
NUKE_EVERY = 10           # every Nth feed is nuclear waste
GLOW_S = 4.0              # how long the radioactive green glow lasts
DECAY_PER_MIN = 3.0       # stat points lost per minute while needy
XP_PER_LEVEL = 100        # xp needed to clear one level
MAX_LEVEL = 50
FIGHT_LEVEL = 40          # at/above this level: human combat mode
KAIJU_LEVEL = 50          # max: monument rampage

DEFAULT_NAME = "Geiger"

# Palette (tune on-badge). Paper is light blue; ink is near-black.
PAPER = (0.62, 0.82, 0.90)
INK = (0.05, 0.07, 0.10)
GLOW = (0.30, 1.00, 0.25)

# Prey by level band: (min_level, label, draw_fn_name)
PREY_BANDS = [
    (1, "flies", "fly"),
    (10, "rats", "rat"),
    (20, "dogs", "dog"),
    (30, "children", "child"),
    (40, "humans", "adult"),
]

MONUMENTS = [
    ("eiffel tower", "Paris falls."),
    ("statue of liberty", "Liberty crumbles."),
    ("big ben", "Time stops for Big Ben."),
    ("white house", "Geiger flattens the White House."),
    ("pyramids", "Another wonder of the world, gone."),
    ("pisa", "The leaning tower leans no more."),
    ("skyscraper", "The skyline is rubble."),
]

OH_NO_LINES = ["oh no", "not again", "eep", "help", "no..."]
FIGHT_FLAVOUR = [
    "{name} devours another challenger.",
    "The humans never stood a chance.",
    "{name} is unstoppable.",
    "Another one gone. {name} grins.",
]


def now():
    return time.time()


def clamp(v, lo, hi):
    return lo if v < lo else (hi if v > hi else v)