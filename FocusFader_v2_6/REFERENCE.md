# FocusFader — Developer Handoff & Reference

**Purpose of this file:** everything a future session needs to continue development
without re-deriving it. Hard-won facts, dead ends, sources, and the exact hardware
protocol as *verified on the device* (which differs from the manual in places).

Target: **PreSonus FaderPort V2** as an Ableton Live **11/12** control-surface
script. Developed and confirmed on **Live 12.4.2**, macOS, user "richardkhor".

---

## 1. What this script is, architecturally

A `_Framework.ControlSurface` subclass. It does **not** use the framework's
`ControlElement`/`Component` objects for its core job — it requests raw MIDI
forwarding in `build_midi_map()` and parses bytes directly in `receive_midi()`.
This was a deliberate pivot (see §5.2) after the element-registration path failed
to deliver any MIDI.

Core idea: observe `song.view.selected_parameter`; bind the fader (pitch bend) to
whatever it points at; drive the motor to mirror the value; parse buttons/encoder
for transport, navigation, view, and mode control.

Two ways the fader reaches a parameter:
- **Native map** (`USE_NATIVE_MAP=True`): `Live.MidiMap.map_midi_pitchbend()` binds
  pitch bend straight to the parameter inside Live's engine. No per-move Python, no
  undo spam, Live drives motor feedback. Preferred.
- **Python fallback**: read pitch bend in `receive_midi`, write `param.value`
  yourself, push motor position yourself, gate the motor echo with a timer.

---

## 2. THE HARDWARE PROTOCOL (verified, not guessed)

The FaderPort must be in **native / "Studio One" mode**: power off, hold **NEXT**,
power on, press **SOLO**. In this mode it speaks a documented native protocol — NOT
Mackie Control. Manual reference: *FaderPort V2 Owner's Manual, section 8.2*.

**⚠ The manual has errors. These are the values confirmed by live MIDI capture:**

| Element | Manual (§8.2) | **VERIFIED** | Notes |
| --- | --- | --- | --- |
| Fader | pitch bend ch 0 | ✅ pitch bend ch 0, 14-bit | `E0 lsb msb`, 0–16383, bidirectional |
| Fader touch | note 0x68 | ✅ 0x68 | Note On press, **real Note Off 0x80** release |
| Encoder | CC **0x3C** | ❌ **CC 0x10** | Manual is WRONG. `B0 10 xx` |
| Encoder delta | "bit 7 = dir" | ✅ **bit 6 (0x40) = sign** | `01`=+1, `41`=−1. Manual's bit-7 is 1-indexed |
| Buttons | Note On/Off ch 0 | ✅ | `90 id 7F` press, `80 id 00` release |

### Button / LED note IDs (all channel 0, confirmed working)

```
Channel strip:   ARM 0x00   BYPASS 0x03   SOLO 0x08   MUTE 0x10
Meta:            SHIFT 0x46   FADER_TOUCH 0x68
Session Nav:     LINK 0x05   PAN 0x2A   CHANNEL 0x36   SCROLL 0x38
                 MASTER 0x3A  CLICK 0x3B  SECTION 0x3C  MARKER 0x3D
                 PREV 0x2E   NEXT 0x2F   PUSH_ENC 0x20
Automation:      READ 0x4A   WRITE 0x4B   TOUCH 0x4D
Transport:       LOOP 0x56   REWIND 0x5B   FFWD 0x5C
                 STOP 0x5D   PLAY 0x5E   RECORD 0x5F   FOOTSWITCH 0x66
```

### LEDs

- **RGB LEDs** (Link, Pan, Channel, Scroll, Read, Write, Touch): set colour by
  sending three messages — `91 id r`, `92 id g`, `93 id b` (channels 1–3), then a
  note-on `90 id 7F` to enable. Full value 0–127 per channel. **Dimming works** by
  scaling the RGB values (script uses `DIM=0.12`).
- **Mono LEDs** (Arm, Bypass, Solo, Mute, transport, Prev/Next, Master, Click,
  Section, Marker): `90 id vv` where vv = `00` off, `7F` on, `01` flash. Colour is
  **fixed in hardware** — cannot be changed by MIDI. **Confirmed on-device:** Bypass
  responds to `0x01` with a genuine dim glow (→ `MONO_DIM = LED_FLASH`). So mono
  LEDs *can* dim via 0x01 even though the manual only lists on/off/flash.

### Unused / available for future mapping
`PAN`/other mode Prev-Next slots, `FOOTSWITCH 0x66`, `BYPASS`-as-something-else.
IDs above are all live; just add handlers.

---

## 3. LIVE-SIDE SETUP THAT IS MANDATORY (and non-obvious)

### `get_capabilities()` in `__init__.py` — the thing that unblocked everything
```python
PORTS_KEY: [inport(props=[SCRIPT, REMOTE]), outport(props=[SCRIPT, REMOTE])]
```
- **`SCRIPT` prop is REQUIRED.** Without it, Live binds the port for Track/Remote
  but **never forwards MIDI to the script**. Symptom: output (motor/LEDs) works,
  input is dead, and MIDI only appears if you tick "Track" on the input port.
  This wasted the most time in development — see §5.3.
- **`CONTROLLER_ID_KEY` deliberately OMITTED.** Including it lets Live auto-detect
  the FaderPort and load its stock script — which is literally
  `return MackieControl(c_instance)` (confirmed by reading the decompiled stock
  `__init__.py`). That MCU script owns the fader and causes the classic
  "fader ignores you until you reselect the track" bug. Omitting the key means
  FocusFader only loads when picked by hand.

### Port checkboxes in Live's MIDI prefs
On both FocusFader Input and Output ports: **Track, Sync, Remote, MPE all OFF.**
- Ticking **Track on Output** closes a motor feedback loop → the fader whines.
- The script owns the port via the SCRIPT prop; it needs none of these.

### Folder naming
Folder must be a valid Python identifier — Live loads via `import <foldername>`.
`FocusFader v1` (with space) → `SyntaxError`, script silently never loads but still
shows in the dropdown. Must be `FocusFader`.

### Universal Control
Confirmed to **coexist fine** — can be left open.

---

## 4. LIVE API (LOM) FACTS ESTABLISHED

Sources: structure-void.com unofficial API docs (Live 10–12), the in-Live
`DUMP_API` introspection we ran (dumped `dir()` of `Application.View` and `Song`
on 12.4.2 to Log.txt), and adammurray.link LOM notes.

### Confirmed present on `Application.View` (Live 12.4.2, from our dump):
```
NavDirection, focus_view, hide_view, show_view, is_view_visible, scroll_view,
zoom_view, toggle_browse, available_main_views, focused_document_view,
browse_mode, add/remove_is_view_visible_listener, add/remove_view_focus_changed…
```
- **No maximise method exists.** "Maximise Clip View Panel Height" (Live 12,
  Cmd/Ctrl+Alt+E) is UI-only, unreachable from a script. `SHIFT+Write` does
  show+focus of `Detail/Clip` as the closest approximation.
- `scroll_view(NavDirection, view_name, bool)` moves the **viewport only** — it does
  NOT follow the selection. Long-standing Live limitation (bug reports back to
  Live 8). Attempting to keep the selected track on-screen by scrolling was
  **removed** — it caused navigation artifacts and jumped to Main at the
  return/send boundary. `song.visible_tracks` exists and *can* drive a
  feedback-scroll loop, but the UX wasn't worth it. Left out intentionally.

### `Song` facts:
- `count_in_duration` is **READ-ONLY** — `"property of 'Song' object has no setter"`.
  Listed as `int` in the LOM but cannot be set. Any count-in toggle is impossible
  from a script. (SHIFT+Click was repurposed to `capture_midi` because of this.)
- Working setters/methods used: `tempo`, `is_playing`, `record_mode`, `metronome`,
  `loop`, `loop_start`, `loop_length`, `punch_in`, `punch_out`, `back_to_arranger`,
  `current_song_time`, `signature_numerator/denominator`, `capture_midi()`,
  `continue_playing()`, `stop_playing()`, `undo()`, `redo()`,
  `jump_to_next_cue()/prev`, `set_or_delete_cue()`, `jump_by()`.
- `selected_parameter` matches Ableton device params and **Configured** VST/AU
  params only — NOT controls clicked inside a plugin's own GUI. This is a hard Live
  limitation; commercial products (Remotify) hit the same wall.
- `song.view.selected_track` is settable; changing it does NOT auto-scroll the view.

### `map_midi_pitchbend` arity
Signature varies across Live versions. Script probes 3/4/5-arg forms in a
try/except loop (`_try_native_map`). On 12.4.2 the 3-arg form
`(midi_map_handle, channel, parameter)` is the one that binds.

### Undo granularity
Recording a fader ride = ONE Live automation transaction = one Undo wipes the whole
pass. This is Live's model, below the script layer. Cannot be subdivided via API.

---

## 5. DEVELOPMENT HISTORY — dead ends and how they were resolved

Reading this saves you from repeating them.

### 5.1 Why not Max for Live?
Originally scoped as an M4L device (`live.dial` + `live.object set value`). Works,
but every `set value` is an undo entry (undo spam), and it needs takeover logic. The
remote-script route binds via Live's own MIDI-map engine → no undo spam, Live drives
the motor. Script won.

### 5.2 First script was DEAF — element registration
v1 built `ButtonElement`/`SliderElement` objects expecting the base
`build_midi_map()` to auto-register their forwarding. It didn't. Zero MIDI arrived.
**Fix:** override `build_midi_map()`, call `Live.MidiMap.forward_midi_note/cc/
pitchbend()` explicitly for every control, parse raw bytes in `receive_midi()`.
Don't rely on element auto-registration.

### 5.3 STILL deaf — the SCRIPT port prop (the big one)
Even with explicit forwarding, no MIDI. Diagnosed via a key user observation: MIDI
only reached Live when **Track** was ticked on the input port. That proved the
cable/port/mode/device were all fine — Live simply wasn't routing the port to the
script. Root cause: `get_capabilities()` didn't declare `props=[SCRIPT, REMOTE]`.
Adding it fixed everything. **If input ever goes dead again, check this first.**

### 5.4 Diagnostic technique that worked
`PROMISCUOUS` mode: forward all 128 notes+CCs (optionally ×16 channels) and
`DEBUG_MIDI` to log every message decoded as `Type ch N xx xx`. This is how the
real encoder CC (0x10) and touch note were captured. NB: forwarding all 16 channels
= 4112 map entries, which may exceed Live's MIDI-map capacity and fail silently —
prefer channel-0-only (`'ch0'`, 257 entries). Flags still in the file, default off.

### 5.5 receive_midi_chunk
Live 11+ calls `receive_midi_chunk()`; base class fans out to `receive_midi()`.
Script overrides chunk to log and delegate, with a fallback loop if super() lacks it.

### 5.6 Listener hygiene
Every `add_*_listener` must be removed in `disconnect()` or Live throws on script
reload. Solo/Mute/Arm listeners must be **rebound on track selection change**
(they're per-track). View-visibility listeners are per-view-name. All handled; if
you add listeners, add the teardown.

---

## 6. SOURCES USED

- **FaderPort V2 Owner's Manual** — button/LED IDs, protocol §8.2. *Has errors*
  (encoder CC, bit numbering); trust captured MIDI over it.
- **structure-void.com** (Julien Bayle) — the only real `_Framework`/`ableton.v2`
  documentation. `midiremotescripts.structure-void.com` and the per-version LOM
  XML dumps (`PythonLiveAPI_documentation/Live*.xml`). Note: Live 12 (Python 3.11)
  can't be cleanly decompiled, so 12 docs are runtime-dumped, not source.
- **In-Live introspection** — our own `DUMP_API` dumping `dir()` to Log.txt. The
  ground truth for 12.4.2; prefer it over any web doc.
- **adammurray.link/max-for-live/js-in-live/live-api** — LOM concepts, Song props.
- **Ableton forums** — `scroll_view` selection-follow limitation (thread 246741,
  191021), Live 12 clip-view shortcuts (thread 249571), count_in read-only.
- **Ableton Live 12 manual** — Clip View / Live Concepts for shortcut ↔ API gaps.
- The user's uploaded **decompiled stock FaderPort `__init__.py`** — proved the
  factory script is just `MackieControl`.

---

## 7. FILE MAP

```
FocusFader/
  __init__.py     get_capabilities() [SCRIPT prop, no controller id]; create_instance
  FocusFader.py   the whole surface (single file, ~600 lines)
  README.md       user-facing controls + install
  REFERENCE.md    this file
```

### Config flags (top of FocusFader.py)
`DEBUG_MIDI`, `PROMISCUOUS` ('off'/'ch0'/'all'), `DUMP_API`, `USE_NATIVE_MAP`,
`STICKY_FOCUS`, `DEFAULT_FADER_TARGET`, `DEFAULT_MODE`, `SHIFT_CLICK_ACTION`,
`TEMPO_STEP`, `LONG_PRESS_S`, `DIM`, `MONO_DIM`, `ENCODER_SIGN_BIT`, `ENCODER_STEP`.
All diagnostics default off in shipped v2.6.

### Testing approach used
No hardware in the dev environment. Every change was verified by importing
`FocusFader.py` against a **stubbed Live API** (fake `Live.MidiMap`, `_Framework`,
Song/Track/View/Param objects) and replaying real captured MIDI bytes / simulating
listener fires. Stubs must model quirks that bit us: mutually-exclusive views
(Clip↔Device, Session↔Arranger), read-only `count_in_duration`, per-track listener
rebind, real Note-Off on release. When a stub "failed," it was often the stub, not
the script — model the real behaviour before trusting a red result.

---

## 8. KNOWN-OPEN / FUTURE IDEAS

- Fader `native-map` vs `forwarded`: confirm which is active in a real session
  (`DEBUG_MIDI` logs `fader=native-map|forwarded`). Undo behaviour differs.
- Footswitch (0x66) and second-function Prev/Next slots are unmapped and free.
- A true "maximise clip view" needs an OS-level keystroke tool; not script-reachable.
- Motor echo: this unit DOES echo motor movement as pitch bend (discovered via the
  whine). Native-map mode + Live's feedback handling suppresses it; the Python
  fallback uses `MOTOR_SLEW_GATE_S` timing. If you rework the fader path, keep one
  of those guards or the scrub/whine returns.
```
