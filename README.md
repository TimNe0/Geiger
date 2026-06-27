# ☢ Geiger — a mutant-spider Tamagotchi for the Tildagon badge

A pet **Tamagotchi spider** for the EMF Camp **Tildagon badge** (ESP32-S3,
MicroPython, round 240×240 screen). It starts as a tiny hatchling and grows
into an unstoppable apex predator. Feed it, clean up after it and play with it
to raise its **level (1–25)** — and every 10th feed is **nuclear waste** that
upskills it and makes it glow radioactive green.

Tuned for a 3-day event: progression is fast, roughly **one level per feed**,
with a 30-second feed cooldown.

## The life of a spider

The spider gains a size step and a new prey tier every **5 levels**:

| Level | What happens |
|-------|--------------|
| 1–5   | Hatchling. Hunts **flies**. |
| 6–10  | Bigger. Hunts **rats**. |
| 11–15 | Bigger still. Hunts **dogs**. |
| 16–20 | Hunts **children**. |
| 21–24 | **FIGHT MODE** — battles humans (and always wins). |
| 25    | **KAIJU MODE** — colossal. Rampages across the world's monuments. |

Every **10th feed** is a glowing **☢ nuclear-waste barrel** instead of normal
prey. Catching it grants a big XP boost and a few seconds of green glow (and
flashes the badge LEDs green).

The spider wanders the screen between actions, and **poops after eating** —
hit **Clean** to clear the mess and restore its cleanliness. It **can never
die**; neglect just makes it grumpy and sluggish.

## Art direction

1970s screen-print look: bold **black "ink"** on a flat **white "paper"**
background. Everything (spider, prey, monuments) is drawn procedurally with the
`ctx` canvas. The only colours that break the scheme are the radioactive green
glow and the one brown thing on screen.

## Controls (standard Tildagon button set)

| Button | Type | Role |
|--------|------|------|
| A | `UP` | Menu up |
| B | `RIGHT` | Text entry: advance letter / mini-game: steer right |
| C | `CONFIRM` | Select / yes / pounce / attack / stomp |
| D | `DOWN` | Menu down |
| E | `LEFT` | Text entry: move left / mini-game: steer left |
| F | `CANCEL` | Back / no / minimise the app |

- From the main screen: **C** opens the action menu, **F** exits.
- **Feed** turns the round screen into a spider **web** and launches a chase —
  steer the spider in any direction with the **arrow buttons** (or tilt the
  badge via the IMU) and **C** to pounce. The catch radius is tight.
- **Clean** clears any poop and restores cleanliness.
- **Play** boosts happiness; give the badge a **shake** for a bigger boost.
- **Rename** uses the badge's built-in text dialog.

## Hardware used

- **12 RGB LEDs** — green flash on nuclear feeds and while glowing,
  celebratory pulse on level-up, aggressive red/green during fights and stomps.
- **IMU** — optional tilt-to-steer in the feed chase and shake-to-play.

Both are optional; the app is fully playable on buttons alone and degrades
gracefully on simulators without the hardware.

## Install

Copy this folder into the `apps/` directory of your Tildagon badge (or sideload
via the emulator / simulator). The entry point is `app.py`, exporting
`GeigerApp`. State is persisted under the single settings key `geiger_spider`.

## Files

- `app.py` — game logic and the input/state machine; exports `GeigerApp`.
- `draw.py` — all procedural rendering (`RenderMixin`, mixed into `GeigerApp`).
- `consts.py` — constants, tunables, tables and tiny helpers.
- `tildagon.toml` — app metadata for the launcher.

The code is split across three small modules on purpose: a single large file
ran the badge out of RAM while compiling it on import ("app too big?"). The
badge compiles one module at a time, so smaller modules keep the peak memory
low. All artwork (spider, prey, monuments) is drawn procedurally with `ctx`;
there are no image assets to ship.

## Licence

MIT — see [LICENSE](LICENSE).