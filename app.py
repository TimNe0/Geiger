# Geiger - a mutant-spider Tamagotchi for the EMF Tildagon badge
# =================================================================
# A pet spider that grows from a tiny hatchling into an apex predator.
# Feed it (every 10th feed is radioactive nuclear waste), water it and
# play with it to raise its level (1-50). From level 40 it fights humans;
# at level 50 it becomes a KAIJU and stomps the world's monuments.
#
# Config key : "geiger_spider"  (single JSON object via the settings module)
# Button map (standard Tildagon set, A-F clockwise from top):
#   A = UP      menu up
#   B = RIGHT   text entry: advance letter  / mini-game: steer right
#   C = CONFIRM select / "yes" / pounce / attack / stomp
#   D = DOWN    menu down
#   E = LEFT    text entry: move left        / mini-game: steer left
#   F = CANCEL  back / "no" / minimise
#
# Art direction: 1970s screen-print -- bold black "ink" on flat light-blue
# "paper". The one exception is the radioactive green glow.

import math
import time
import random

import app
import settings

from events.input import Buttons, BUTTON_TYPES
from app_components import clear_background, Notification, YesNoDialog, TextDialog

# Hardware is optional so the app still imports under bare simulators.
try:
    from tildagonos import tildagonos
    _HAS_LEDS = True
except Exception:  # pragma: no cover - depends on host
    tildagonos = None
    _HAS_LEDS = False

try:
    from system.patterndisplay.events import PatternDisable
    import eventbus
    _HAS_PATTERN = True
except Exception:  # pragma: no cover
    PatternDisable = None
    eventbus = None
    _HAS_PATTERN = False

try:
    import imu
    _HAS_IMU = True
except Exception:  # pragma: no cover
    imu = None
    _HAS_IMU = False


# --- Tunable constants (retune on site for the event) -----------------------
CONFIG_KEY = "geiger_spider"

FEED_COOLDOWN_S = 60.0      # soft cooldown between feeds -> ~1 level/minute
NUKE_EVERY = 10            # every Nth feed is nuclear waste
GLOW_S = 4.0               # how long the radioactive green glow lasts
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


class GeigerApp(app.App):
    # ----------------------------------------------------------------- setup
    def __init__(self):
        super().__init__()
        self.button_states = Buttons(self)

        if _HAS_PATTERN:
            try:
                eventbus.emit(PatternDisable())
            except Exception:
                pass

        self.pet = self._load()

        # UI / view state machine.
        #   "hatching" "naming" "main" "menu" "feed" "fight" "kaiju" "confirm_reset"
        self.view = "main"
        self.menu_index = 0
        self.menu_items = []
        self.notification = None
        self.dialog = None
        self._dialog_open = False

        self.t = 0.0            # animation clock
        self.shake = 0.0        # screen-shake amount
        self.message = ""       # transient flavour text
        self.message_until = 0.0

        # mini-game scratch state
        self.spider_x = 0.0
        self.prey = []
        self.feed_is_nuke = False
        self.feed_caught = False
        self.action_t = 0.0      # water/play animation timer
        self.played_shake = False
        self.fight_phase = 0.0
        self.fight_ohno = ""
        self.monument_index = 0
        self.monument_state = "intact"   # "intact" | "smashing"
        self.monument_timer = 0.0
        self.debris = []

        self._apply_offline_decay()

        if self.pet.get("hatched"):
            self.view = "main"
        else:
            self.view = "hatching"
            self.hatch_t = 0.0

    # ------------------------------------------------------------- persistence
    def _defaults(self):
        return {
            "name": DEFAULT_NAME,
            "level": 1,
            "xp": 0,
            "hunger": 80,
            "thirst": 80,
            "happiness": 80,
            "size_stage": 1,
            "feed_count": 0,
            "last_feed": 0.0,
            "last_seen": now(),
            "glow_until": 0.0,
            "hatched": False,
            "monuments_destroyed": 0,
        }

    def _load(self):
        pet = self._defaults()
        try:
            saved = settings.get(CONFIG_KEY, None)
        except Exception:
            saved = None
        if isinstance(saved, dict):
            # merge saved over defaults so new fields survive old saves
            pet.update(saved)
        pet["size_stage"] = self._size_for_level(pet.get("level", 1))
        return pet

    def _save(self):
        self.pet["last_seen"] = now()
        try:
            settings.set(CONFIG_KEY, self.pet)
            settings.save()
        except Exception:
            pass

    # --------------------------------------------------------------- derived
    def _size_for_level(self, level):
        return clamp(1 + (level - 1) // 10, 1, 5)

    def _prey_for_level(self, level):
        prey = PREY_BANDS[0]
        for band in PREY_BANDS:
            if level >= band[0]:
                prey = band
        return prey  # (min_level, label, draw_name)

    def _feeds_until_nuke(self):
        return NUKE_EVERY - (self.pet["feed_count"] % NUKE_EVERY)

    def _next_feed_is_nuke(self):
        return (self.pet["feed_count"] % NUKE_EVERY) == (NUKE_EVERY - 1)

    def _is_glowing(self):
        return now() < self.pet.get("glow_until", 0.0)

    def _feed_ready_in(self):
        return clamp(FEED_COOLDOWN_S - (now() - self.pet.get("last_feed", 0.0)), 0, FEED_COOLDOWN_S)

    # ------------------------------------------------------------- offline decay
    def _apply_offline_decay(self):
        elapsed = now() - self.pet.get("last_seen", now())
        if elapsed <= 0:
            return
        loss = (elapsed / 60.0) * DECAY_PER_MIN
        if loss <= 0:
            return
        for stat in ("hunger", "thirst", "happiness"):
            self.pet[stat] = clamp(self.pet[stat] - loss, 0, 100)
        self.pet["last_seen"] = now()

    def _decay_live(self, delta):
        # gentle live decay so the spider gets needy while you watch
        loss = (delta / 60.0) * DECAY_PER_MIN * 0.5
        for stat in ("hunger", "thirst", "happiness"):
            self.pet[stat] = clamp(self.pet[stat] - loss, 0, 100)

    def _neediness(self):
        return (self.pet["hunger"] + self.pet["thirst"] + self.pet["happiness"]) / 3.0

    # ----------------------------------------------------------------- xp / level
    def _grant_xp(self, amount):
        # sluggish XP when neglected; it's awesome, it endures, just slower
        if self._neediness() < 30:
            amount = int(amount * 0.5)
        self.pet["xp"] += amount
        leveled = False
        milestone = False
        while self.pet["xp"] >= XP_PER_LEVEL and self.pet["level"] < MAX_LEVEL:
            self.pet["xp"] -= XP_PER_LEVEL
            self.pet["level"] += 1
            leveled = True
            new_size = self._size_for_level(self.pet["level"])
            if new_size != self.pet["size_stage"]:
                self.pet["size_stage"] = new_size
                milestone = True
        if self.pet["level"] >= MAX_LEVEL:
            self.pet["xp"] = 0
        if leveled:
            self._on_level_up(milestone)
        return leveled

    def _on_level_up(self, milestone):
        lvl = self.pet["level"]
        if lvl >= KAIJU_LEVEL:
            self._flash_message("APEX PREDATOR! LV 50")
        elif milestone:
            self._flash_message("GROWTH! LV %d" % lvl)
        else:
            self._flash_message("Level up! LV %d" % lvl)
        self._notify("Level %d" % lvl)
        self.shake = 6.0 if milestone else 3.0
        self._led_pulse(GLOW if milestone else (0.9, 0.9, 0.2))

    # ------------------------------------------------------------- notifications
    def _notify(self, text):
        try:
            self.notification = Notification(text)
        except Exception:
            self.notification = None

    def _flash_message(self, text, secs=2.5):
        self.message = text
        self.message_until = now() + secs

    # ----------------------------------------------------------------- leds
    def _led_all(self, colour):
        if not _HAS_LEDS:
            return
        r, g, b = (int(clamp(c, 0, 1) * 255) for c in colour)
        try:
            for i in range(1, 13):
                tildagonos.leds[i] = (r, g, b)
            tildagonos.leds.write()
        except Exception:
            pass

    def _led_pulse(self, colour):
        self._led_all(colour)

    def _update_leds(self):
        if not _HAS_LEDS:
            return
        if self._is_glowing():
            p = 0.5 + 0.5 * math.sin(self.t * 8)
            self._led_all((0.1 * p, 1.0 * p, 0.1 * p))
        elif self.view in ("fight", "kaiju"):
            p = 0.5 + 0.5 * math.sin(self.t * 10)
            self._led_all((1.0 * p, 1.0 * (1 - p), 0.05))
        else:
            # quiet ambient: dim ink-ish ring
            self._led_all((0.02, 0.06, 0.10))

    # ================================================================ UPDATE
    def update(self, delta):
        dt = delta / 1000.0 if delta > 1.5 else delta  # accept ms or seconds
        self.t += dt
        if self.shake > 0:
            self.shake = max(0.0, self.shake - dt * 12)

        self._decay_live(dt)
        self._update_leds()

        # Dialogs take over input while open.
        if self.dialog is not None:
            try:
                self.dialog.update(delta)
            except Exception:
                pass
            return

        if self.view == "hatching":
            self._update_hatching(dt)
        elif self.view == "naming":
            self._open_name_dialog()
        elif self.view in ("main", "menu"):
            self._update_main(dt)
        elif self.view == "feed":
            self._update_feed(dt)
        elif self.view == "water":
            self._update_action(dt, "water")
        elif self.view == "play":
            self._update_action(dt, "play")
        elif self.view == "fight":
            self._update_fight(dt)
        elif self.view == "kaiju":
            self._update_kaiju(dt)

    def background_update(self, delta):
        # keep the world turning while minimised
        dt = delta / 1000.0 if delta > 1.5 else delta
        self._decay_live(dt * 0.25)

    # ---------------------------------------------------------------- hatching
    def _update_hatching(self, dt):
        self.hatch_t += dt
        if self.button_states.get(BUTTON_TYPES["CONFIRM"]) or self.hatch_t > 4.0:
            self.button_states.clear()
            self.pet["hatched"] = True
            self.view = "naming"

    def _open_name_dialog(self):
        if self._dialog_open:
            return
        self._dialog_open = True
        try:
            self.dialog = TextDialog(
                "Name your spider", self,
                default_text=self.pet.get("name", DEFAULT_NAME),
                on_complete=self._name_complete,
                on_cancel=self._name_cancel,
            )
        except TypeError:
            # older signature without default_text
            self.dialog = TextDialog(
                "Name your spider", self,
                on_complete=self._name_complete,
                on_cancel=self._name_cancel,
            )
        except Exception:
            self.dialog = None
            self._name_cancel()

    def _name_complete(self):
        text = ""
        try:
            text = (self.dialog.text or "").strip()
        except Exception:
            text = ""
        self.pet["name"] = text if text else DEFAULT_NAME
        self._finish_naming()

    def _name_cancel(self):
        if not self.pet.get("name"):
            self.pet["name"] = DEFAULT_NAME
        self._finish_naming()

    def _finish_naming(self):
        self.dialog = None
        self._dialog_open = False
        self.view = "main"
        self._save()
        self._notify("Meet %s!" % self.pet["name"])

    # ----------------------------------------------------------------- main/menu
    def _build_menu(self):
        if self.pet["level"] >= KAIJU_LEVEL:
            return ["Rampage", "Rename", "Reset"]
        if self.pet["level"] >= FIGHT_LEVEL:
            return ["Fight", "Rename", "Reset"]
        return ["Feed", "Water", "Play", "Rename", "Reset"]

    def _update_main(self, dt):
        if self.view == "main":
            if self.button_states.get(BUTTON_TYPES["CONFIRM"]):
                self.button_states.clear()
                self.menu_items = self._build_menu()
                self.menu_index = 0
                self.view = "menu"
                return
            if self.button_states.get(BUTTON_TYPES["CANCEL"]):
                self.button_states.clear()
                self._save()
                self.minimise()
                return
            return

        # view == "menu"
        if self.button_states.get(BUTTON_TYPES["UP"]):
            self.button_states.clear()
            self.menu_index = (self.menu_index - 1) % len(self.menu_items)
        elif self.button_states.get(BUTTON_TYPES["DOWN"]):
            self.button_states.clear()
            self.menu_index = (self.menu_index + 1) % len(self.menu_items)
        elif self.button_states.get(BUTTON_TYPES["CANCEL"]):
            self.button_states.clear()
            self.view = "main"
        elif self.button_states.get(BUTTON_TYPES["CONFIRM"]):
            self.button_states.clear()
            self._activate_menu(self.menu_items[self.menu_index])

    def _activate_menu(self, item):
        if item == "Feed":
            self._start_feed()
        elif item == "Water":
            self._do_water()
        elif item == "Play":
            self._do_play()
        elif item == "Fight":
            self._start_fight()
        elif item == "Rampage":
            self._start_kaiju()
        elif item == "Rename":
            self.view = "naming"
            self._dialog_open = False
        elif item == "Reset":
            self._confirm_reset()

    # ---------------------------------------------------------------- water/play
    def _do_water(self):
        self.view = "water"
        self.action_t = 1.2

    def _do_play(self):
        self.view = "play"
        self.action_t = 1.2
        self.played_shake = False

    def _update_action(self, dt, kind):
        if self.button_states.get(BUTTON_TYPES["CANCEL"]):
            self.button_states.clear()
            self.action_t = 0.0
        if kind == "play" and _HAS_IMU and self._imu_magnitude() > 1.6:
            self.played_shake = True
        self.action_t -= dt
        if self.action_t <= 0:
            self._finish_action(kind)

    def _finish_action(self, kind):
        if kind == "water":
            self.pet["thirst"] = clamp(self.pet["thirst"] + 35, 0, 100)
            self._grant_xp(10)
            self._flash_message("Slurp! Thirst restored.")
            self._notify("Watered")
        else:
            boost = 45 if self.played_shake else 30
            self.pet["happiness"] = clamp(self.pet["happiness"] + boost, 0, 100)
            self._grant_xp(10)
            self.shake = 2.0
            self._flash_message("Wheee! Happy spider.")
            self._notify("Played")
        self._save()
        self.view = "main"

    def _imu_magnitude(self):
        try:
            x, y, z = imu.acc_read()
            return math.sqrt(x * x + y * y + z * z) / 9.81
        except Exception:
            return 1.0

    def _imu_tilt_x(self):
        try:
            x, y, z = imu.acc_read()
            return clamp(x / 9.81, -1, 1)
        except Exception:
            return 0.0

    # ------------------------------------------------------------------- feed
    def _start_feed(self):
        if self._feed_ready_in() > 0:
            self._flash_message("Not hungry yet (%ds)" % int(self._feed_ready_in()))
            self.view = "main"
            return
        self.feed_is_nuke = self._next_feed_is_nuke()
        self.feed_caught = False
        self.spider_x = 0.0
        self.prey = []
        # spawn a few prey targets moving across the screen
        n = 1 if self.feed_is_nuke else 3
        for _ in range(n):
            self.prey.append({
                "x": random.uniform(-90, 90),
                "y": random.uniform(-70, 70),
                "vx": random.uniform(-50, 50),
                "vy": random.uniform(-30, 30),
                "alive": True,
            })
        self.view = "feed"
        if self.feed_is_nuke:
            self._flash_message("RADIOACTIVE FEED READY")

    def _update_feed(self, dt):
        if self.button_states.get(BUTTON_TYPES["CANCEL"]):
            self.button_states.clear()
            self.view = "main"
            return

        # steer the spider: buttons or tilt
        steer = 0.0
        if self.button_states.get(BUTTON_TYPES["LEFT"]):
            steer -= 1.0
        if self.button_states.get(BUTTON_TYPES["RIGHT"]):
            steer += 1.0
        if steer == 0.0 and _HAS_IMU:
            steer = self._imu_tilt_x()
        self.spider_x = clamp(self.spider_x + steer * 160 * dt, -100, 100)

        # move prey
        for p in self.prey:
            if not p["alive"]:
                continue
            p["x"] += p["vx"] * dt
            p["y"] += p["vy"] * dt
            if abs(p["x"]) > 100:
                p["vx"] *= -1
            if abs(p["y"]) > 90:
                p["vy"] *= -1

        # pounce
        if self.button_states.get(BUTTON_TYPES["CONFIRM"]):
            self.button_states.clear()
            spider_y = 70
            for p in self.prey:
                if not p["alive"]:
                    continue
                if abs(p["x"] - self.spider_x) < 26 and abs(p["y"] - spider_y) < 70:
                    p["alive"] = False
                    self._on_catch()
                    return

    def _on_catch(self):
        self.feed_caught = True
        self.pet["feed_count"] += 1
        self.pet["last_feed"] = now()
        self.pet["hunger"] = clamp(self.pet["hunger"] + 40, 0, 100)
        if self.feed_is_nuke:
            self.pet["glow_until"] = now() + GLOW_S
            self._grant_xp(int(XP_PER_LEVEL * 2.5))  # upskill: ~2-3 levels
            self._led_pulse(GLOW)
            self._flash_message("UPSKILLED! Radioactive feast.")
            self._notify("Nuclear feed!")
            self.shake = 5.0
        else:
            self._grant_xp(XP_PER_LEVEL)  # ~one level per feed
            self._flash_message("Caught it! Yum.")
        self._save()
        self.view = "main"

    # ------------------------------------------------------------------- fight
    def _start_fight(self):
        self.view = "fight"
        self.fight_phase = 0.0
        self.fight_ohno = random.choice(OH_NO_LINES)

    def _update_fight(self, dt):
        if self.button_states.get(BUTTON_TYPES["CANCEL"]):
            self.button_states.clear()
            self.view = "main"
            return
        if self.fight_phase > 0:
            self.fight_phase = max(0.0, self.fight_phase - dt)
            if self.fight_phase == 0.0:
                self._win_fight()
            return
        if self.button_states.get(BUTTON_TYPES["CONFIRM"]):
            self.button_states.clear()
            self.fight_phase = 1.2   # play the (one-sided) animation
            self.fight_ohno = random.choice(OH_NO_LINES)
            self.shake = 4.0
            self._led_pulse((1.0, 0.1, 0.05))

    def _win_fight(self):
        self._grant_xp(XP_PER_LEVEL)
        self._flash_message(random.choice(FIGHT_FLAVOUR).format(name=self.pet["name"]))
        self._save()
        if self.pet["level"] >= KAIJU_LEVEL:
            self.view = "main"

    # ------------------------------------------------------------------- kaiju
    def _start_kaiju(self):
        self.view = "kaiju"
        self.monument_state = "intact"
        self.monument_timer = 0.0
        self.debris = []

    def _update_kaiju(self, dt):
        if self.button_states.get(BUTTON_TYPES["CANCEL"]):
            self.button_states.clear()
            self.view = "main"
            return
        if self.monument_state == "smashing":
            self.monument_timer -= dt
            for d in self.debris:
                d["x"] += d["vx"] * dt
                d["y"] += d["vy"] * dt
                d["vy"] += 200 * dt
            if self.monument_timer <= 0:
                self.monument_state = "intact"
                self.monument_index = (self.monument_index + 1) % len(MONUMENTS)
            return
        # auto-rampage on a timer, or on CONFIRM
        self.monument_timer += dt
        if self.button_states.get(BUTTON_TYPES["CONFIRM"]) or self.monument_timer > 3.0:
            self.button_states.clear()
            self._smash_monument()

    def _smash_monument(self):
        name, flavour = MONUMENTS[self.monument_index]
        self.pet["monuments_destroyed"] = self.pet.get("monuments_destroyed", 0) + 1
        self.monument_state = "smashing"
        self.monument_timer = 1.2
        self.shake = 7.0
        self._led_pulse((1.0, 0.2, 0.05))
        self.debris = [{
            "x": random.uniform(-15, 15), "y": 70,
            "vx": random.uniform(-80, 80), "vy": random.uniform(-120, -40),
        } for _ in range(14)]
        self._flash_message(flavour)
        self._save()

    # ------------------------------------------------------------------- reset
    def _confirm_reset(self):
        try:
            self.dialog = YesNoDialog(
                "Reset %s to a hatchling?" % self.pet["name"], self,
                on_yes=self._do_reset, on_no=self._cancel_dialog,
            )
        except Exception:
            self.dialog = None

    def _do_reset(self):
        name = self.pet.get("name", DEFAULT_NAME)
        self.pet = self._defaults()
        self.pet["name"] = name
        self.pet["hatched"] = True
        self.dialog = None
        self.view = "main"
        self._save()
        self._notify("Reset!")

    def _cancel_dialog(self):
        self.dialog = None
        self.view = "main"

    # ================================================================== DRAW
    def draw(self, ctx):
        clear_background(ctx)
        ctx.save()
        ctx.rgb(*PAPER)
        ctx.rectangle(-120, -120, 240, 240).fill()

        # screen shake
        if self.shake > 0:
            ctx.translate(random.uniform(-self.shake, self.shake),
                          random.uniform(-self.shake, self.shake))

        if self.view == "hatching":
            self._draw_hatching(ctx)
        elif self.view == "feed":
            self._draw_feed(ctx)
        elif self.view in ("water", "play"):
            self._draw_action(ctx, self.view)
        elif self.view == "fight":
            self._draw_fight(ctx)
        elif self.view == "kaiju":
            self._draw_kaiju(ctx)
        else:
            self._draw_home(ctx)

        self._draw_overlays(ctx)
        ctx.restore()

        if self.notification:
            try:
                self.notification.draw(ctx)
            except Exception:
                pass
        if self.dialog:
            try:
                self.dialog.draw(ctx)
            except Exception:
                pass

    # ----- text helper
    def _text(self, ctx, s, x, y, size=18, colour=INK, centre=True):
        ctx.save()
        ctx.rgb(*colour)
        ctx.font_size = size
        try:
            ctx.text_align = ctx.CENTER if centre else ctx.LEFT
            ctx.text_baseline = ctx.MIDDLE
        except Exception:
            pass
        ctx.move_to(x, y)
        ctx.text(s)
        ctx.restore()

    # ----- the spider, drawn procedurally in ink
    def _draw_spider(self, ctx, cx, cy, scale, glowing=False):
        ctx.save()
        ctx.translate(cx, cy)
        wob = math.sin(self.t * 3) * 2
        needy = self._neediness() < 30
        if needy:
            ctx.translate(0, 4)  # droop
        body = 14 * scale
        legspan = 26 * scale

        if glowing:
            ctx.rgb(*GLOW)
            ctx.line_width = 4 * scale
        else:
            ctx.rgb(*INK)
            ctx.line_width = 3 * scale

        # legs (4 per side)
        for side in (-1, 1):
            for i in range(4):
                ay = -8 * scale + i * 6 * scale
                lift = math.sin(self.t * 6 + i + (0 if side > 0 else 2)) * 3
                ctx.begin_path()
                ctx.move_to(side * body * 0.4, ay)
                ctx.line_to(side * (body + 6 * scale), ay - 6 * scale + lift)
                ctx.line_to(side * legspan, ay + 4 * scale + lift)
                ctx.stroke()
        # abdomen + head
        ctx.begin_path()
        ctx.arc(0, body * 0.3 + wob, body, 0, math.tau, False)
        ctx.fill()
        ctx.begin_path()
        ctx.arc(0, -body * 0.7 + wob, body * 0.6, 0, math.tau, False)
        ctx.fill()
        # eyes (paper-coloured dots)
        ctx.rgb(*PAPER)
        for ex in (-0.25, 0.25):
            ctx.begin_path()
            ctx.arc(ex * body, -body * 0.8 + wob, body * 0.12, 0, math.tau, False)
            ctx.fill()
        ctx.restore()

    # ----- home / main + menu
    def _draw_home(self, ctx):
        pet = self.pet
        glowing = self._is_glowing()
        size = self.pet["size_stage"]
        self._draw_spider(ctx, 0, 5, 0.8 + size * 0.25, glowing)

        # level readout in the upper-left arc
        self._text(ctx, "LV %d/%d" % (pet["level"], MAX_LEVEL), -62, -88, 18)
        self._text(ctx, pet["name"], 0, -64, 22)

        # prey icon + label for current tier
        _, prey_label, prey_draw = self._prey_for_level(pet["level"])
        getattr(self, "_icon_" + prey_draw)(ctx, 78, -78, 0.8)

        # stat bars
        self._stat_bar(ctx, "HUN", pet["hunger"], 70)
        self._stat_bar(ctx, "THI", pet["thirst"], 86)
        self._stat_bar(ctx, "HAP", pet["happiness"], 102)

        # feeds-until-nuke / apex banner
        if pet["level"] >= KAIJU_LEVEL:
            self._text(ctx, "APEX PREDATOR", 0, -100, 14)
        elif pet["level"] >= FIGHT_LEVEL:
            self._text(ctx, "FIGHT MODE", 0, -100, 14)
        else:
            self._text(ctx, "next %s: %d feeds" % (chr(0x2622), self._feeds_until_nuke()),
                       0, -100, 13)

        if self.view == "menu":
            self._draw_menu(ctx)
        else:
            self._text(ctx, "C: menu  F: exit", 0, 108, 12)

    def _stat_bar(self, ctx, label, value, y):
        x = -100
        w = 70
        self._text(ctx, label, x - 4, y, 11, centre=False)
        ctx.save()
        ctx.rgb(*INK)
        ctx.line_width = 1.5
        ctx.rectangle(x + 22, y - 5, w, 9).stroke()
        ctx.rectangle(x + 22, y - 5, w * (value / 100.0), 9).fill()
        ctx.restore()

    def _draw_menu(self, ctx):
        n = len(self.menu_items)
        ctx.save()
        ctx.rgb(*PAPER)
        ctx.rectangle(-60, 16, 120, 14 + n * 18).fill()
        ctx.rgb(*INK)
        ctx.line_width = 2
        ctx.rectangle(-60, 16, 120, 14 + n * 18).stroke()
        ctx.restore()
        for i, item in enumerate(self.menu_items):
            y = 30 + i * 18
            if i == self.menu_index:
                ctx.save()
                ctx.rgb(*INK)
                ctx.rectangle(-56, y - 9, 112, 17).fill()
                ctx.restore()
                self._text(ctx, item, 0, y, 15, colour=PAPER)
            else:
                self._text(ctx, item, 0, y, 15)

    # ----- hatching
    def _draw_hatching(self, ctx):
        crack = min(1.0, self.hatch_t / 3.0)
        ctx.save()
        ctx.rgb(*INK)
        ctx.line_width = 4
        ctx.begin_path()
        ctx.arc(0, 0, 40, 0, math.tau, False)
        ctx.stroke()
        # zig-zag crack widening
        ctx.line_width = 3
        ctx.begin_path()
        ctx.move_to(-40 * crack, -10)
        ctx.line_to(-8, 0)
        ctx.line_to(-16, 12)
        ctx.line_to(8, 6)
        ctx.line_to(40 * crack, -4)
        ctx.stroke()
        ctx.restore()
        if crack > 0.6:
            self._draw_spider(ctx, 0, 0, 0.5)
        self._text(ctx, "A spider hatches...", 0, 70, 16)
        self._text(ctx, "C to continue", 0, 92, 12)

    # ----- feed mini-game
    def _draw_feed(self, ctx):
        if self.feed_is_nuke:
            for p in self.prey:
                if p["alive"]:
                    self._icon_nuke(ctx, p["x"], p["y"], 1.0)
            self._text(ctx, "%s NUCLEAR WASTE %s" % (chr(0x2622), chr(0x2622)), 0, -98, 13, colour=(0.1, 0.5, 0.1))
        else:
            _, label, prey_draw = self._prey_for_level(self.pet["level"])
            for p in self.prey:
                if p["alive"]:
                    getattr(self, "_icon_" + prey_draw)(ctx, p["x"], p["y"], 0.9)
            self._text(ctx, "catch the %s!" % label, 0, -98, 14)
        # spider at the bottom, steerable
        self._draw_spider(ctx, self.spider_x, 70, 0.7, self._is_glowing())
        self._text(ctx, "E/B steer  C pounce  F back", 0, 104, 11)

    # ----- water / play
    def _draw_action(self, ctx, kind):
        self._draw_spider(ctx, 0, 24, 1.3, self._is_glowing())
        prog = 1.0 - clamp(self.action_t / 1.2, 0, 1)
        if kind == "water":
            self._icon_drop(ctx, 0, -56 + prog * 56, 1.3)
            self._text(ctx, "watering...", 0, -96, 15)
        else:
            self._icon_web(ctx, 0, -48, 1.4)
            label = "shake to play!" if _HAS_IMU else "playing..."
            self._text(ctx, label, 0, -96, 15)
            if self.played_shake:
                self._text(ctx, "wheee!", 0, 92, 14)
        self._text(ctx, "F: skip", 0, 110, 11)

    # ----- fight
    def _draw_fight(self, ctx):
        self._draw_spider(ctx, -30, 10, 1.6, self._is_glowing())
        if self.fight_phase > 0:
            # human being eaten, with an "oh no" bubble
            shrink = self.fight_phase / 1.2
            self._icon_adult(ctx, 40, 20, 0.6 + 0.4 * shrink)
            self._speech_bubble(ctx, 56, -16, self.fight_ohno)
        else:
            self._icon_adult(ctx, 50, 25, 1.0)
            self._text(ctx, "C: ATTACK", 0, 90, 16)
        self._text(ctx, "FIGHT  LV %d/%d" % (self.pet["level"], MAX_LEVEL), 0, -96, 15)
        self._text(ctx, "F: back", 0, 110, 11)

    def _speech_bubble(self, ctx, x, y, text):
        ctx.save()
        ctx.rgb(*PAPER)
        ctx.rectangle(x - 26, y - 12, 52, 22).fill()
        ctx.rgb(*INK)
        ctx.line_width = 1.5
        ctx.rectangle(x - 26, y - 12, 52, 22).stroke()
        ctx.begin_path()
        ctx.move_to(x - 4, y + 10)
        ctx.line_to(x - 12, y + 20)
        ctx.line_to(x + 4, y + 10)
        ctx.fill()
        ctx.restore()
        self._text(ctx, text, x, y - 1, 12)

    # ----- kaiju
    def _draw_kaiju(self, ctx):
        name, _ = MONUMENTS[self.monument_index]
        # giant spider fills most of the screen
        self._draw_spider(ctx, 0, -6, 3.4, self._is_glowing())
        if self.monument_state == "smashing":
            ctx.save()
            ctx.rgb(*INK)
            for d in self.debris:
                ctx.rectangle(d["x"], d["y"], 4, 4).fill()
            ctx.restore()
            self._text(ctx, "SMASH!", 0, 80, 22)
        else:
            # monument tiny at the spider's feet -> scale contrast
            getattr(self, "_mon_" + name.replace(" ", "_"), self._mon_skyscraper)(ctx, 70, 88, 0.45)
            self._text(ctx, "C: STOMP", 0, 70, 14)
        self._text(ctx, "APEX PREDATOR %s LV 50/50 %s UNDEFEATED" % (chr(0x00B7), chr(0x00B7)),
                   0, -104, 11)
        self._text(ctx, "Monuments destroyed: %d" % self.pet.get("monuments_destroyed", 0),
                   0, 106, 12)

    # ----- transient overlay text
    def _draw_overlays(self, ctx):
        if self.message and now() < self.message_until:
            ctx.save()
            ctx.rgb(*PAPER)
            ctx.rectangle(-118, 116, 236, 0)  # noop keep-state
            ctx.restore()
            self._text(ctx, self.message, 0, -118 + 10, 13, colour=(0.1, 0.4, 0.1))

    # ============================================================ icon drawing
    # Ink silhouettes matching the supplied geiger-icons.png sheet. Each takes
    # a centre (x, y) and a scale. Drawn with only the ctx primitives that are
    # reliably present on the badge firmware (arc / rectangle / line / fill).

    def _ell(self, ctx, x, y, rx, ry):
        # filled ellipse via a scaled unit circle (ctx.ellipse isn't portable)
        ctx.save()
        ctx.translate(x, y)
        ctx.scale(rx, ry)
        ctx.begin_path()
        ctx.arc(0, 0, 1, 0, math.tau, False)
        ctx.fill()
        ctx.restore()

    def _icon_fly(self, ctx, x, y, s):
        # vertical segmented body, two wings spread up-and-out, antennae
        ctx.save(); ctx.translate(x, y); ctx.scale(s, s); ctx.rgb(*INK)
        for sx in (-1, 1):                       # wings
            self._ell(ctx, sx * 7, -3, 6, 4)
        self._ell(ctx, 0, 3, 4, 8)               # abdomen
        ctx.begin_path(); ctx.arc(0, -7, 3.5, 0, math.tau, False); ctx.fill()  # head
        ctx.line_width = 1.2                      # antennae
        for sx in (-1, 1):
            ctx.begin_path(); ctx.move_to(sx * 1.5, -10); ctx.line_to(sx * 4, -14); ctx.stroke()
        ctx.restore()

    def _icon_rat(self, ctx, x, y, s):
        # side profile: round body, ear, pointy snout right, long curly tail
        ctx.save(); ctx.translate(x, y); ctx.scale(s, s); ctx.rgb(*INK)
        self._ell(ctx, 0, 0, 10, 6)
        ctx.begin_path(); ctx.arc(8, -1, 4.5, 0, math.tau, False); ctx.fill()    # head
        ctx.begin_path(); ctx.arc(7, -6, 2.6, 0, math.tau, False); ctx.fill()    # ear
        ctx.begin_path(); ctx.move_to(12, -1); ctx.line_to(15, 1); ctx.line_to(12, 3); ctx.fill()  # snout
        ctx.line_width = 1.6                                                     # tail
        ctx.begin_path(); ctx.move_to(-10, 1); ctx.line_to(-17, -2); ctx.line_to(-20, 4); ctx.stroke()
        ctx.line_width = 1.4                                                     # feet
        for fx in (-4, 4):
            ctx.begin_path(); ctx.move_to(fx, 5); ctx.line_to(fx, 8); ctx.stroke()
        ctx.restore()

    def _icon_dog(self, ctx, x, y, s):
        # side profile standing: rounded body, head + floppy ear, tail, 4 legs
        ctx.save(); ctx.translate(x, y); ctx.scale(s, s); ctx.rgb(*INK)
        self._ell(ctx, -2, -2, 11, 6)
        ctx.begin_path(); ctx.arc(10, -5, 4.5, 0, math.tau, False); ctx.fill()   # head
        ctx.begin_path(); ctx.move_to(13, -4); ctx.line_to(17, -3); ctx.line_to(13, -1); ctx.fill()  # snout
        ctx.begin_path(); ctx.move_to(8, -9); ctx.line_to(7, -3); ctx.line_to(11, -4); ctx.fill()    # ear
        ctx.line_width = 2.5                                                     # tail up
        ctx.begin_path(); ctx.move_to(-12, -4); ctx.line_to(-16, -10); ctx.stroke()
        ctx.line_width = 3                                                       # legs
        for lx in (-9, -4, 4, 8):
            ctx.begin_path(); ctx.move_to(lx, 3); ctx.line_to(lx, 10); ctx.stroke()
        ctx.restore()

    def _icon_child(self, ctx, x, y, s):
        self._icon_person(ctx, x, y, s * 0.72, stubby=True)

    def _icon_adult(self, ctx, x, y, s):
        self._icon_person(ctx, x, y, s, stubby=False)

    def _icon_person(self, ctx, x, y, s, stubby=False):
        # solid silhouette: round head, tapered torso, arms at sides, two legs
        ctx.save(); ctx.translate(x, y); ctx.scale(s, s); ctx.rgb(*INK)
        leg = 13 if stubby else 16
        ctx.begin_path(); ctx.arc(0, -13, 5, 0, math.tau, False); ctx.fill()     # head
        ctx.begin_path()                                                         # torso
        ctx.move_to(-5, -7); ctx.line_to(5, -7)
        ctx.line_to(6, 4); ctx.line_to(-6, 4); ctx.fill()
        ctx.line_width = 3                                                       # arms
        ctx.begin_path(); ctx.move_to(-5, -5); ctx.line_to(-9, 4); ctx.stroke()
        ctx.begin_path(); ctx.move_to(5, -5); ctx.line_to(9, 4); ctx.stroke()
        ctx.line_width = 3.5                                                     # legs
        ctx.begin_path(); ctx.move_to(-2, 4); ctx.line_to(-4, leg); ctx.stroke()
        ctx.begin_path(); ctx.move_to(2, 4); ctx.line_to(4, leg); ctx.stroke()
        ctx.restore()

    def _icon_drop(self, ctx, x, y, s):
        # teardrop: round bottom + pointed top, with a paper highlight
        ctx.save(); ctx.translate(x, y); ctx.scale(s, s); ctx.rgb(*INK)
        ctx.begin_path(); ctx.arc(0, 4, 8, 0, math.tau, False); ctx.fill()
        ctx.begin_path(); ctx.move_to(-6, 0); ctx.line_to(0, -13); ctx.line_to(6, 0); ctx.fill()
        ctx.rgb(*PAPER); ctx.begin_path(); ctx.arc(-3, 5, 2.2, 0, math.tau, False); ctx.fill()
        ctx.restore()

    def _icon_web(self, ctx, x, y, s):
        # circular spider web: radial spokes + concentric polygon rings
        ctx.save(); ctx.translate(x, y); ctx.scale(s, s); ctx.rgb(*INK); ctx.line_width = 1.2
        n = 8
        for i in range(n):
            a = i * math.tau / n
            ctx.begin_path(); ctx.move_to(0, 0)
            ctx.line_to(math.cos(a) * 12, math.sin(a) * 12); ctx.stroke()
        for rr in (4, 8, 12):
            ctx.begin_path()
            for i in range(n + 1):
                a = i * math.tau / n
                px, py = math.cos(a) * rr, math.sin(a) * rr
                if i == 0:
                    ctx.move_to(px, py)
                else:
                    ctx.line_to(px, py)
            ctx.stroke()
        ctx.restore()

    def _icon_nuke(self, ctx, x, y, s):
        # waste drum: elliptical top, rim bands, radiation trefoil
        ctx.save(); ctx.translate(x, y); ctx.scale(s, s)
        pulse = 0.5 + 0.5 * math.sin(self.t * 8)
        barrel = GLOW if (self._is_glowing() and pulse > 0.5) else INK
        ctx.rgb(*barrel)
        ctx.rectangle(-9, -9, 18, 19).fill()     # body
        self._ell(ctx, 0, -9, 9, 3)              # top
        ctx.rgb(*PAPER); ctx.line_width = 1.2     # rim bands
        ctx.begin_path(); ctx.move_to(-9, -3); ctx.line_to(9, -3); ctx.stroke()
        ctx.begin_path(); ctx.move_to(-9, 4); ctx.line_to(9, 4); ctx.stroke()
        ctx.rgb(*PAPER)                           # trefoil
        ctx.begin_path(); ctx.arc(0, 0, 1.6, 0, math.tau, False); ctx.fill()
        for a in range(3):
            ang = a * math.tau / 3 - math.pi / 2
            ctx.begin_path(); ctx.move_to(0, 0)
            ctx.arc(0, 0, 5.5, ang - 0.5, ang + 0.5, False)
            ctx.line_to(0, 0); ctx.fill()
        ctx.restore()

    # ============================================================ monuments
    def _mon_eiffel_tower(self, ctx, x, y, s):
        # curved splayed legs, two platforms, lattice braces, antenna point
        ctx.save(); ctx.translate(x, y); ctx.scale(s, s); ctx.rgb(*INK); ctx.line_width = 2
        ctx.begin_path(); ctx.move_to(-14, 0); ctx.line_to(-6, -18); ctx.line_to(-2, -40); ctx.stroke()
        ctx.begin_path(); ctx.move_to(14, 0); ctx.line_to(6, -18); ctx.line_to(2, -40); ctx.stroke()
        ctx.begin_path(); ctx.move_to(0, -40); ctx.line_to(0, -48); ctx.stroke()      # antenna
        ctx.begin_path(); ctx.move_to(-10, -16); ctx.line_to(10, -16); ctx.stroke()   # platforms
        ctx.begin_path(); ctx.move_to(-5, -28); ctx.line_to(5, -28); ctx.stroke()
        ctx.line_width = 1.2                                                          # lattice
        ctx.begin_path(); ctx.move_to(-9, -4); ctx.line_to(9, -12); ctx.stroke()
        ctx.begin_path(); ctx.move_to(9, -4); ctx.line_to(-9, -12); ctx.stroke()
        ctx.restore()

    def _mon_statue_of_liberty(self, ctx, x, y, s):
        # pedestal, robe, head with crown spikes, raised torch arm
        ctx.save(); ctx.translate(x, y); ctx.scale(s, s); ctx.rgb(*INK)
        ctx.rectangle(-8, -4, 16, 6).fill()      # pedestal base
        ctx.rectangle(-5, -10, 10, 6).fill()     # pedestal top
        ctx.begin_path(); ctx.move_to(-6, -10); ctx.line_to(0, -30); ctx.line_to(6, -10); ctx.fill()  # robe
        ctx.begin_path(); ctx.arc(0, -33, 3.5, 0, math.tau, False); ctx.fill()        # head
        ctx.line_width = 1.2                                                          # crown spikes
        for a in (-0.9, -0.45, 0, 0.45, 0.9):
            ctx.begin_path(); ctx.move_to(0, -33)
            ctx.line_to(math.sin(a) * 9, -33 - math.cos(a) * 9); ctx.stroke()
        ctx.line_width = 2.5                                                          # torch arm
        ctx.begin_path(); ctx.move_to(3, -26); ctx.line_to(9, -40); ctx.stroke()
        ctx.begin_path(); ctx.arc(9, -42, 2.5, 0, math.tau, False); ctx.fill()        # flame
        ctx.restore()

    def _mon_big_ben(self, ctx, x, y, s):
        # clock tower with face + hands and a pointed spire
        ctx.save(); ctx.translate(x, y); ctx.scale(s, s); ctx.rgb(*INK)
        ctx.rectangle(-6, -34, 12, 34).fill()
        ctx.begin_path(); ctx.move_to(-7, -34); ctx.line_to(0, -46); ctx.line_to(7, -34); ctx.fill()  # spire
        ctx.rgb(*PAPER); ctx.begin_path(); ctx.arc(0, -26, 3.5, 0, math.tau, False); ctx.fill()       # face
        ctx.rgb(*INK); ctx.line_width = 1
        ctx.begin_path(); ctx.move_to(0, -26); ctx.line_to(0, -28.5); ctx.stroke()
        ctx.begin_path(); ctx.move_to(0, -26); ctx.line_to(2, -26); ctx.stroke()
        ctx.restore()

    def _mon_white_house(self, ctx, x, y, s):
        # columned block, central pediment + flag, steps
        ctx.save(); ctx.translate(x, y); ctx.scale(s, s); ctx.rgb(*INK)
        ctx.rectangle(-16, -14, 32, 14).fill()
        ctx.begin_path(); ctx.move_to(-9, -14); ctx.line_to(0, -22); ctx.line_to(9, -14); ctx.fill()  # pediment
        ctx.line_width = 1                                                          # flagpole + flag
        ctx.begin_path(); ctx.move_to(0, -22); ctx.line_to(0, -27); ctx.stroke()
        ctx.rectangle(0, -27, 4, 2.5).fill()
        ctx.rgb(*PAPER)                                                            # columns
        for cx in range(-13, 14, 4):
            ctx.rectangle(cx, -12, 1.5, 10).fill()
        ctx.rgb(*INK); ctx.rectangle(-18, 0, 36, 2).fill()                         # steps
        ctx.restore()

    def _mon_pyramids(self, ctx, x, y, s):
        # two pyramids, a sun, and a desert ground line
        ctx.save(); ctx.translate(x, y); ctx.scale(s, s); ctx.rgb(*INK)
        ctx.begin_path(); ctx.arc(11, -19, 5, 0, math.tau, False); ctx.fill()       # sun
        ctx.begin_path(); ctx.move_to(-22, 0); ctx.line_to(-8, -20); ctx.line_to(6, 0); ctx.fill()
        ctx.begin_path(); ctx.move_to(0, 0); ctx.line_to(12, -14); ctx.line_to(24, 0); ctx.fill()
        ctx.line_width = 1.5
        ctx.begin_path(); ctx.move_to(-24, 0); ctx.line_to(26, 0); ctx.stroke()
        ctx.restore()

    def _mon_pisa(self, ctx, x, y, s):
        ctx.save(); ctx.translate(x, y); ctx.scale(s, s); ctx.rgb(*INK)
        ctx.rotate(0.18)
        ctx.rectangle(-6, -34, 12, 34).fill()
        ctx.rgb(*PAPER); ctx.line_width = 1
        for ry in range(-30, 0, 6):
            ctx.begin_path(); ctx.move_to(-6, ry); ctx.line_to(6, ry); ctx.stroke()
        ctx.restore()

    def _mon_skyscraper(self, ctx, x, y, s):
        ctx.save(); ctx.translate(x, y); ctx.scale(s, s); ctx.rgb(*INK)
        ctx.rectangle(-8, -40, 16, 40).fill()
        ctx.rgb(*PAPER)
        for wy in range(-36, -2, 6):
            for wx in (-5, 0, 4):
                ctx.rectangle(wx, wy, 2, 3).fill()
        ctx.restore()


__app_export__ = GeigerApp