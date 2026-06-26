# Geiger - a mutant-spider Tamagotchi for the EMF Tildagon badge
# =================================================================
# A pet spider that grows from a tiny hatchling into an apex predator.
# Feed it (every 10th feed is radioactive nuclear waste), water it and
# play with it to raise its level (1-50). From level 40 it fights humans;
# at level 50 it becomes a KAIJU and stomps the world's monuments.
#
# Split across three modules so each compiles within the badge's RAM
# (one big file caused "Out of memory (app too big?)" at import):
#   consts.py - constants, tunables, tables, tiny helpers
#   draw.py   - all procedural rendering (RenderMixin)
#   app.py    - game logic + state machine (this file)
#
# Config key : "geiger_spider"  (single JSON object via the settings module)
# Button map (standard Tildagon set, A-F clockwise from top):
#   A = UP      menu up
#   B = RIGHT   text entry: advance letter  / mini-game: steer right
#   C = CONFIRM select / "yes" / pounce / attack / stomp
#   D = DOWN    menu down
#   E = LEFT    text entry: move left        / mini-game: steer left
#   F = CANCEL  back / "no" / minimise

import math
import random
import gc

import app
import settings

from events.input import Buttons, BUTTON_TYPES
from app_components import Notification, YesNoDialog, TextDialog

# Constants, tables and tiny helpers live in their own small module.
try:
    from .consts import (
        CONFIG_KEY, FEED_COOLDOWN_S, NUKE_EVERY, GLOW_S, DECAY_PER_MIN,
        XP_PER_LEVEL, MAX_LEVEL, FIGHT_LEVEL, KAIJU_LEVEL, DEFAULT_NAME,
        GLOW, PREY_BANDS, MONUMENTS, OH_NO_LINES, FIGHT_FLAVOUR, now, clamp)
except (ImportError, ValueError):  # imported as a top-level module
    from consts import (
        CONFIG_KEY, FEED_COOLDOWN_S, NUKE_EVERY, GLOW_S, DECAY_PER_MIN,
        XP_PER_LEVEL, MAX_LEVEL, FIGHT_LEVEL, KAIJU_LEVEL, DEFAULT_NAME,
        GLOW, PREY_BANDS, MONUMENTS, OH_NO_LINES, FIGHT_FLAVOUR, now, clamp)

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

# Free the compiler's working memory before pulling in the rendering module.
gc.collect()
try:
    from .draw import RenderMixin
except (ImportError, ValueError):
    from draw import RenderMixin


class GeigerApp(RenderMixin, app.App):
    # ----------------------------------------------------------------- setup
    def __init__(self):
        super().__init__()
        self.button_states = Buttons(self)
        self._has_imu = _HAS_IMU

        if _HAS_PATTERN:
            try:
                eventbus.emit(PatternDisable())
            except Exception:
                pass

        self.pet = self._load()

        # UI / view state machine.
        #   "hatching" "naming" "main" "menu" "feed" "water" "play" "fight" "kaiju"
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

        gc.collect()

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


__app_export__ = GeigerApp