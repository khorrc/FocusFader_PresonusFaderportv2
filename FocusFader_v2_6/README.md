# FocusFader

A custom Ableton Live control-surface script for the **PreSonus FaderPort V2**.

Its headline trick: the motorised fader always controls **whichever parameter you
last clicked** in Live — native device parameters, rack macros, mixer controls,
and configured VST/AU parameters alike. Click a filter cutoff, the fader jumps to
it and rides it. Click a reverb mix, the fader follows. No banking, no mode-hunting,
no "which track is selected" surprises. The rest of the FaderPort becomes a compact
transport, navigation, and view controller.

Think of it as a telephone exchange: the hardware always rings the same number
(one fader, one encoder), and the script re-patches that line to whatever you just
touched with the mouse.

---

## Requirements

- Ableton Live 11 or 12 (developed and tested on **Live 12.4.2**).
- A **PreSonus FaderPort V2**, set to **native / "Studio One" mode** (see below).

---

## Installing the FaderPort in native mode

This is essential — the script speaks the FaderPort's native MIDI protocol, not
Mackie Control.

1. Power the unit **off**.
2. Hold the **NEXT** button and power it **on** while still holding.
3. When the operation-mode buttons light up, press **SOLO** (Studio One mode).

You can leave it in this mode permanently.

---

## Installing the script

### macOS

1. Find (or create) your Remote Scripts folder:
   ```
   ~/Music/Ableton/User Library/Remote Scripts/
   ```
2. Copy the **`FocusFader`** folder into it, so you end up with:
   ```
   ~/Music/Ableton/User Library/Remote Scripts/FocusFader/__init__.py
   ~/Music/Ableton/User Library/Remote Scripts/FocusFader/FocusFader.py
   ```
   The folder **must** be named `FocusFader` — no spaces, no version numbers.
   Live loads it by running `import FocusFader`, so the name has to be a valid
   Python identifier.

### Windows

1. Find (or create) your Remote Scripts folder:
   ```
   \Users\<you>\Documents\Ableton\User Library\Remote Scripts\
   ```
2. Copy the **`FocusFader`** folder into it, so you end up with:
   ```
   ...\User Library\Remote Scripts\FocusFader\__init__.py
   ...\User Library\Remote Scripts\FocusFader\FocusFader.py
   ```
   Same naming rule: the folder must be exactly `FocusFader`.

### Both platforms — enable it in Live

1. Restart Live.
2. **Settings → Link, Tempo & MIDI**.
3. In an empty **Control Surface** row, choose **FocusFader**.
4. Set both **Input** and **Output** to **PreSonus FP2**.
5. Make sure no *other* Control Surface row is using the FaderPort. If one has
   auto-grabbed it as "FaderPort", set that row to **None** — two scripts fighting
   over one fader will misbehave.

### MIDI port checkboxes

Below the Control Surface rows, Live lists the FaderPort's input and output ports.
Leave **Track, Sync, Remote and MPE all unticked** on both. The script owns the
port directly; ticking **Track** in particular creates a feedback loop that makes
the motorised fader whine.

> Note: Live's MIDI activity indicators (top-right) do **not** flash for
> control-surface traffic. That's normal — it doesn't mean nothing is happening.

Universal Control can stay open; it coexists fine with the script.

---

## Controls

### The fader

- Drives the **last-clicked parameter** (default), motorised so it always shows
  the true current value. Touch-sensitive: grab it and it stops fighting you.
- **SHIFT + Link** switches the fader between two targets:
  - **Focused parameter** (default) — the last-clicked parameter.
  - **Selected-track volume** — classic FaderPort behaviour, follows the
    selected track.

### The Session Navigator encoder

The encoder's job depends on the active **mode button**. The lit mode button shows
which is active.

| Mode button | Encoder does | Encoder push | Prev / Next |
| --- | --- | --- | --- |
| **Master** | Master volume | reset to 0 dB | scroll tracks |
| **Pan** | selected track pan | reset to centre | scroll tracks |
| **Channel** | scroll/select tracks | — | scroll tracks |
| **Scroll** (default) | move playhead (1 bar) | — | horizontal zoom |
| **Marker** | scrub timeline | set / delete cue | jump to prev / next cue |

- **SHIFT + encoder** in Scroll mode = vertical zoom.
- **SHIFT + Prev / Next** = **Undo / Redo** (in any mode).

### Modifier buttons (hold + encoder)

| Hold | + encoder | + Prev / Next |
| --- | --- | --- |
| **Loop** | resize the loop brace (± 1 bar) | move the loop ± 1 bar |
| **Click** | nudge tempo (± 1 BPM) | — |

Holding Loop or Click and using it as a modifier suppresses its normal tap action,
so you won't accidentally toggle the loop or metronome.

### Channel strip

| Button | Action |
| --- | --- |
| **Arm** | arm/disarm selected track |
| **Solo** | solo selected track |
| **Mute** | mute selected track |
| **Bypass** | show / hide the Detail panel |

### Transport

| Button | Press | SHIFT / Long |
| --- | --- | --- |
| **Play** | play from cursor | **SHIFT** = resume from pause point |
| **Stop** | stop | **SHIFT** = return to zero · **long-press** = Back to Arrangement |
| **Record** | toggle record | — |
| **Loop** | toggle loop | (hold = loop editing, above) |
| **Rewind / Fast-Forward** | hold to scrub the playhead | — |

### Views & automation row

| Button | Press | SHIFT |
| --- | --- | --- |
| **Touch** | show / hide Browser | — |
| **Write** | toggle Clip ⇄ Device view | maximise / focus the Clip (MIDI editor) view |
| **Read** | toggle Session ⇄ Arrangement | toggle Draw mode |
| **Click** | metronome on/off | Capture MIDI |
| **Section** | punch-in on/off | punch-out on/off |

---

## LED feedback

- **Panel buttons** (Bypass, Touch, Write, Read) sit at a **dim resting glow** and
  go **bright** when their panel/view is open — easy to read in a dark room.
- **Link** encodes fader mode and lock state:
  - dim green — focus mode, following clicks
  - bright green — focus mode, **locked** to one parameter
  - dim blue — volume mode, following the selected track
  - bright blue — volume mode, locked
- **Play** green, **Record** red, **Loop** amber, **Click** amber, and the active
  **encoder mode** button lit — all reflect real Live state, and update even when
  you change things with the mouse.
- **Solo / Mute / Arm** light with the selected track's state. These are
  single-colour LEDs on the FaderPort, so their colour is fixed by the hardware
  (the script can only turn them on/off, not recolour them).

---

## Locking to a parameter

- **Link** (tap) toggles **lock**: the fader freezes on the current parameter and
  ignores further clicks until you tap Link again. Handy for riding one control
  while you click around elsewhere.
- By default, clicking the transport, empty space, or the browser does **not**
  drop the focused parameter (sticky focus) — only clicking a *different*
  parameter moves it.

---

## Configuration

All options live at the top of `FocusFader.py`:

| Setting | Default | What it does |
| --- | --- | --- |
| `USE_NATIVE_MAP` | `True` | Bind the fader via Live's MIDI-map engine (no undo spam, Live drives the motor). Falls back automatically if unavailable. |
| `STICKY_FOCUS` | `True` | Ignore deselects; keep the last clicked parameter. |
| `DEFAULT_FADER_TARGET` | focus | Start in focused-parameter or selected-track-volume mode. |
| `DEFAULT_MODE` | Scroll | Encoder mode on startup. |
| `SHIFT_CLICK_ACTION` | `capture_midi` | What SHIFT+Click does (any zero-argument Song method). |
| `TEMPO_STEP` | `1.0` | BPM per encoder detent when holding Click. |
| `LONG_PRESS_S` | `0.5` | Seconds that count as a long-press (for Stop). |
| `DIM` | `0.12` | Brightness of the dim resting LED glow (0–1). |
| `MONO_DIM` | `LED_FLASH` | Dim value for single-colour LEDs (Bypass). |
| `DEBUG_MIDI` | `False` | Log every incoming MIDI message to Live's Log.txt. |

---

## Notes and limitations

- **Undo:** recording a fader ride is a single Live automation transaction, so one
  Undo clears the whole pass. That's Live's model, not the script — use Capture or
  takes if you want finer granularity.
- **Maximise Clip View** is a UI-only shortcut in Live (Cmd/Ctrl+Alt+E) with no
  scripting equivalent; SHIFT+Write does the closest available thing (show + focus
  the clip detail).
- The `_Framework` control-surface layer is undocumented and unsupported by
  Ableton; class names can shift between major Live versions. This script targets
  Live 11–12.

Enjoy — and after a decade, it's about time the fader followed your mouse.
