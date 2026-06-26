# ☢ Geiger — a mutant-spider Tamagotchi for the Tildagon badge

A pet **Tamagotchi spider** for the EMF Camp **Tildagon badge** (ESP32-S3,
MicroPython, round 240×240 screen). It starts as a tiny hatchling and grows
into an unstoppable apex predator. Feed it, water it and play with it to raise
its **level (1–50)** — and every 10th feed is **nuclear waste** that upskills
it and makes it glow radioactive green.

Tuned for a 3-day event: progression is fast, roughly **one level per feed**,
about a minute apart.

## The life of a spider

| Level | What happens |
|-------|--------------|
| 1–9   | Hatchling. Hunts **flies**. |
| 10–19 | Bigger. Hunts **rats**. |
| 20–29 | Bigger still. Hunts **dogs**. |
| 30–39 | Hunts **children**. |
| 40–49 | **FIGHT MODE** — stops eating, just battles humans (and always wins). |
| 50    | **KAIJU MODE** — colossal. Rampages across the world's monuments. |

Every **10th feed** is a glowing **☢ nuclear-waste barrel** instead of normal
prey (taken from the swap shop table). Catching it grants a big XP boost and a few seconds of green glow (and
flashes the badge LEDs green).

The spider **can never die** — neglect just makes it grumpy and sluggish.

## Art direction

1970s screen-print look: bold **black "ink"** on a flat **light-blue "paper"**
background. Everything (spider, prey, monuments) is drawn procedurally with the
`ctx` canvas. The only colour that breaks the scheme is the radioactive green
glow.

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
- **Feed** launches a short chase mini-game — steer the spider with **E/B**
  (or tilt the badge via the IMU) and **C** to pounce.
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

- `app.py` — the entire app (single self-contained MicroPython file).
- `tildagon.toml` — app metadata for the launcher.

All artwork (spider, prey, monuments) is drawn procedurally with `ctx`; there
are no image assets to ship.

## Licence

MIT — see [LICENSE](LICENSE).