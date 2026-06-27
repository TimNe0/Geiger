# Geiger - all procedural rendering, factored into a mixin.
# Split out of app.py so each module compiles with a smaller peak memory
# footprint on the badge (a single big file ran the badge out of RAM at
# import: "Out of memory (app too big?)").
#
# RenderMixin is mixed into GeigerApp; every method here reads game state off
# `self` (self.pet, self.view, self.t, ...) and the logic helpers that stay in
# app.py (self._is_glowing(), self._prey_for_level(), ...).

import math
import random

from app_components import clear_background

try:
    from .consts import (PAPER, INK, GLOW, POOP, MAX_LEVEL, FIGHT_LEVEL,
                         KAIJU_LEVEL, MONUMENTS, POOP_SPOTS, TAU, now)
except (ImportError, ValueError):  # imported as a top-level module
    from consts import (PAPER, INK, GLOW, POOP, MAX_LEVEL, FIGHT_LEVEL,
                        KAIJU_LEVEL, MONUMENTS, POOP_SPOTS, TAU, now)


class RenderMixin:
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
        elif self.view == "play":
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
        ctx.arc(0, body * 0.3 + wob, body, 0, TAU, False)
        ctx.fill()
        ctx.begin_path()
        ctx.arc(0, -body * 0.7 + wob, body * 0.6, 0, TAU, False)
        ctx.fill()
        # eyes (paper-coloured dots)
        ctx.rgb(*PAPER)
        for ex in (-0.25, 0.25):
            ctx.begin_path()
            ctx.arc(ex * body, -body * 0.8 + wob, body * 0.12, 0, TAU, False)
            ctx.fill()
        ctx.restore()

    # ----- home / main + menu
    def _draw_home(self, ctx):
        pet = self.pet
        glowing = self._is_glowing()
        size = self.pet["size_stage"]

        # poop sits on the floor; draw it under the wandering spider
        self._draw_poop(ctx, pet.get("poop", 0))
        self._draw_spider(ctx, self.wander_x, self.wander_y,
                          0.8 + size * 0.25, glowing)

        # level readout in the upper-left arc
        self._text(ctx, "LV %d/%d" % (pet["level"], MAX_LEVEL), -62, -88, 18)
        self._text(ctx, pet["name"], 0, -64, 22)

        # prey icon + label for current tier
        _, prey_label, prey_draw = self._prey_for_level(pet["level"])
        getattr(self, "_icon_" + prey_draw)(ctx, 78, -78, 0.8)

        # stat bars
        self._stat_bar(ctx, "HUN", pet["hunger"], 70)
        self._stat_bar(ctx, "CLN", pet["clean"], 86)
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
        ctx.arc(0, 0, 40, 0, TAU, False)
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
        # the round screen IS the web: spokes + rings across the whole face
        self._draw_web_bg(ctx)
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
        # the steerable spider, anywhere on the web
        self._draw_spider(ctx, self.spider_x, self.spider_y, 0.65, self._is_glowing())
        self._text(ctx, "arrows steer  C pounce", 0, 104, 11)

    def _draw_web_bg(self, ctx):
        ctx.save()
        ctx.rgb(*INK)
        ctx.line_width = 1
        R = 112
        n = 12
        for i in range(n):
            a = i * TAU / n
            ctx.begin_path()
            ctx.move_to(0, 0)
            ctx.line_to(math.cos(a) * R, math.sin(a) * R)
            ctx.stroke()
        for rr in range(18, R, 20):
            ctx.begin_path()
            for i in range(n + 1):
                a = i * TAU / n
                px, py = math.cos(a) * rr, math.sin(a) * rr
                if i == 0:
                    ctx.move_to(px, py)
                else:
                    ctx.line_to(px, py)
            ctx.stroke()
        ctx.restore()

    # ----- play (dangle a thread on a web)
    def _draw_action(self, ctx, kind):
        self._draw_spider(ctx, 0, 24, 1.3, self._is_glowing())
        self._icon_web(ctx, 0, -48, 1.4)
        label = "shake to play!" if self._has_imu else "playing..."
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

    # ----- transient overlay text (lower band so it's easy to read)
    def _draw_overlays(self, ctx):
        if self.message and now() < self.message_until:
            y = -48
            ctx.save()
            ctx.rgb(*PAPER)
            ctx.rectangle(-104, y - 13, 208, 26).fill()
            ctx.rgb(*INK)
            ctx.line_width = 1
            ctx.begin_path(); ctx.move_to(-104, y - 13); ctx.line_to(104, y - 13); ctx.stroke()
            ctx.begin_path(); ctx.move_to(-104, y + 13); ctx.line_to(104, y + 13); ctx.stroke()
            ctx.restore()
            self._text(ctx, self.message, 0, y, 13, colour=(0.05, 0.4, 0.05))

    # ----- poop on the floor (the one brown thing), cleared by Clean
    def _draw_poop(self, ctx, count):
        if not count:
            return
        ctx.save()
        ctx.rgb(*POOP)
        for i in range(min(count, len(POOP_SPOTS))):
            x, y = POOP_SPOTS[i]
            self._ell(ctx, x, y + 2, 6, 3)      # coiled little pile
            self._ell(ctx, x, y - 1, 4.6, 2.6)
            self._ell(ctx, x, y - 3.5, 3, 2)
        ctx.restore()

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
        ctx.arc(0, 0, 1, 0, TAU, False)
        ctx.fill()
        ctx.restore()

    def _icon_fly(self, ctx, x, y, s):
        # vertical segmented body, two wings spread up-and-out, antennae
        ctx.save(); ctx.translate(x, y); ctx.scale(s, s); ctx.rgb(*INK)
        for sx in (-1, 1):                       # wings
            self._ell(ctx, sx * 7, -3, 6, 4)
        self._ell(ctx, 0, 3, 4, 8)               # abdomen
        ctx.begin_path(); ctx.arc(0, -7, 3.5, 0, TAU, False); ctx.fill()  # head
        ctx.line_width = 1.2                      # antennae
        for sx in (-1, 1):
            ctx.begin_path(); ctx.move_to(sx * 1.5, -10); ctx.line_to(sx * 4, -14); ctx.stroke()
        ctx.restore()

    def _icon_rat(self, ctx, x, y, s):
        # side profile: round body, ear, pointy snout right, long curly tail
        ctx.save(); ctx.translate(x, y); ctx.scale(s, s); ctx.rgb(*INK)
        self._ell(ctx, 0, 0, 10, 6)
        ctx.begin_path(); ctx.arc(8, -1, 4.5, 0, TAU, False); ctx.fill()    # head
        ctx.begin_path(); ctx.arc(7, -6, 2.6, 0, TAU, False); ctx.fill()    # ear
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
        ctx.begin_path(); ctx.arc(10, -5, 4.5, 0, TAU, False); ctx.fill()   # head
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
        ctx.begin_path(); ctx.arc(0, -13, 5, 0, TAU, False); ctx.fill()     # head
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

    def _icon_web(self, ctx, x, y, s):
        # circular spider web: radial spokes + concentric polygon rings
        ctx.save(); ctx.translate(x, y); ctx.scale(s, s); ctx.rgb(*INK); ctx.line_width = 1.2
        n = 8
        for i in range(n):
            a = i * TAU / n
            ctx.begin_path(); ctx.move_to(0, 0)
            ctx.line_to(math.cos(a) * 12, math.sin(a) * 12); ctx.stroke()
        for rr in (4, 8, 12):
            ctx.begin_path()
            for i in range(n + 1):
                a = i * TAU / n
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
        ctx.begin_path(); ctx.arc(0, 0, 1.6, 0, TAU, False); ctx.fill()
        for a in range(3):
            ang = a * TAU / 3 - math.pi / 2
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
        ctx.begin_path(); ctx.arc(0, -33, 3.5, 0, TAU, False); ctx.fill()        # head
        ctx.line_width = 1.2                                                          # crown spikes
        for a in (-0.9, -0.45, 0, 0.45, 0.9):
            ctx.begin_path(); ctx.move_to(0, -33)
            ctx.line_to(math.sin(a) * 9, -33 - math.cos(a) * 9); ctx.stroke()
        ctx.line_width = 2.5                                                          # torch arm
        ctx.begin_path(); ctx.move_to(3, -26); ctx.line_to(9, -40); ctx.stroke()
        ctx.begin_path(); ctx.arc(9, -42, 2.5, 0, TAU, False); ctx.fill()        # flame
        ctx.restore()

    def _mon_big_ben(self, ctx, x, y, s):
        # clock tower with face + hands and a pointed spire
        ctx.save(); ctx.translate(x, y); ctx.scale(s, s); ctx.rgb(*INK)
        ctx.rectangle(-6, -34, 12, 34).fill()
        ctx.begin_path(); ctx.move_to(-7, -34); ctx.line_to(0, -46); ctx.line_to(7, -34); ctx.fill()  # spire
        ctx.rgb(*PAPER); ctx.begin_path(); ctx.arc(0, -26, 3.5, 0, TAU, False); ctx.fill()       # face
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
        ctx.begin_path(); ctx.arc(11, -19, 5, 0, TAU, False); ctx.fill()       # sun
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