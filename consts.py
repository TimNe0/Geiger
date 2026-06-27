# Geiger - shared constants, tunables and tiny helpers.
# Kept in its own small module so app.py and draw.py each compile with a low
# peak memory footprint on the badge (the firmware compiles one module at a
# time; a single large file can run the badge out of RAM at import).

import time

# MicroPython's math module only provides pi and e (no tau), so define our own.
TAU = 6.283185307179586

CONFIG_KEY = "geiger_spider"

# --- Tunable game timings (retune on site for the event) --------------------
FEED_COOLDOWN_S = 30.0     # soft cooldown between feeds
NUKE_EVERY = 5            # every Nth feed is nuclear waste (~one per 5 levels)
GLOW_S = 4.0              # how long the radioactive green glow lasts
DECAY_PER_MIN = 3.0       # stat points lost per minute while needy
XP_PER_LEVEL = 100        # xp needed to clear one level
MAX_LEVEL = 25
FIGHT_LEVEL = 21          # at/above this level: human combat mode
KAIJU_LEVEL = 25          # max: monument rampage
LEVELS_PER_STAGE = 5      # prey tier + a size step every 5 levels

# Neglect: a stat at/under STAT_LOW shows red; if the spider stays starved
# (average stat under STARVE_NEEDINESS) for STARVE_DROP_S it loses a level.
STAT_LOW = 25
STARVE_NEEDINESS = 20
STARVE_DROP_S = 25.0

# Play (shake-to-play): a real shake must exceed SHAKE_THRESHOLD g, and the
# session runs the full PLAY_DURATION_S so a tiny nudge can't end it.
SHAKE_THRESHOLD = 2.2
PLAY_DURATION_S = 3.0

DEFAULT_NAME = "Geiger"

# Palette. Background is white "paper"; everything else is black "ink".
PAPER = (1.0, 1.0, 1.0)
INK = (0.05, 0.07, 0.10)
GLOW = (0.30, 1.00, 0.25)
RED = (0.85, 0.16, 0.12)   # low-stat warning / level loss
POOP = (0.36, 0.24, 0.12)  # the one brown thing on screen

# Prey by level band: (min_level, label, draw_fn_name) -- one per 5 levels
PREY_BANDS = [
    (1, "flies", "fly"),
    (6, "rats", "rat"),
    (11, "dogs", "dog"),
    (16, "children", "child"),
    (21, "humans", "adult"),
]

# Fixed scatter of spots where poop lands on the floor around the spider
# (kept clear of the stat row along the bottom of the screen).
POOP_SPOTS = [
    (-44, 30), (40, 26), (-12, 44), (50, 36), (6, 34), (-54, 20),
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