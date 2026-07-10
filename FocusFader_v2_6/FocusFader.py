"""FocusFader v2.0 - PreSonus FaderPort V2 control surface for Ableton Live.

  Fader   -> whichever parameter you last clicked (14-bit, motorised, touch-gated)
  Encoder -> Session Navigator: its function depends on the active MODE button
  Buttons -> transport, views, and the mode selector

The FaderPort must be in NATIVE ("Studio One") mode:
    hold NEXT while powering on, then press SOLO.

VERIFIED ON HARDWARE (Live 12.4.2, FaderPort V2):
  * Buttons send Note On 0x7F on press and a true Note Off (0x80) on release.
  * Fader is 14-bit pitch bend, channel 0, bidirectional.
  * Fader touch is note 0x68.
  * Encoder is CC 0x10 -- NOT 0x3C as the Owner's Manual 8.2.3 claims.
      B0 10 01 = +1 detent    B0 10 41 = -1 detent   (bit 6 = sign)

Live binds this script's port only because __init__.py declares
props=[SCRIPT, REMOTE]. Without it, forwarded MIDI never arrives.
"""
from __future__ import absolute_import, print_function, unicode_literals

import time

import Live

try:
    from _Framework.ControlSurface import ControlSurface
except ImportError:  # pragma: no cover
    from ableton.v2.control_surface import ControlSurface


# ===========================================================================
# CONFIGURATION
# ===========================================================================

DEBUG_MIDI = False

# 'off' | 'ch0' | 'all'   -- diagnostic MIDI forwarding. 'ch0'/'all' are inert.
PROMISCUOUS = 'off'

# Bind the fader through Live's MIDI-map engine (no undo spam, Live drives the
# motor). Falls back to Python read/write automatically if the binding fails.
USE_NATIVE_MAP = True

# Ignore deselects. Clicking the transport / empty space / browser no longer
# unbinds the fader. Use SHIFT+Link to freeze focus deliberately.
STICKY_FOCUS = True

# Fader targets. SHIFT+Link flips between them:
#   'focus'  - the last-clicked parameter (this script's whole point)
#   'volume' - the selected track's volume (stock FaderPort behaviour)
FADER_TARGET_FOCUS, FADER_TARGET_VOLUME = 'focus', 'volume'
DEFAULT_FADER_TARGET = FADER_TARGET_FOCUS

# A press longer than this many seconds counts as a long-press.
LONG_PRESS_S = 0.5

# Tempo nudge per encoder detent when holding Click (BPM).
TEMPO_STEP = 1.0

# Fallback mode only: ignore fader input for this long after commanding the
# motor, so the motor's own travel is not written back into the parameter.
MOTOR_SLEW_GATE_S = 0.30

# Rewind / Fast Forward hold-repeat.
SCRUB_BEATS = 1.0          # beats moved per repeat

# NOTE: song.count_in_duration is READ-ONLY in Live's Python API ("property of
# 'Song' object has no setter"), so no script can toggle the count-in. SHIFT+Click
# does Capture MIDI instead. Change this to any zero-argument Song method name.
SHIFT_CLICK_ACTION = 'capture_midi'

# One-shot: dump what Application.View and Song actually expose, to Log.txt.
# Use it to hunt for API calls (e.g. a real "maximise") rather than guessing.
DUMP_API = False
SCRUB_REPEAT_TICKS = 1     # 1 tick ~= 100 ms

ENCODER_SIGN_BIT = 0x40
ENCODER_STEP = 1 / 128.0   # fraction of full range per detent


# ===========================================================================
# FaderPort native-mode MIDI map (Owner's Manual 8.2, corrected)
# ===========================================================================

CH = 0
ENCODER_CC = 0x10          # verified; manual's 0x3C is wrong

# Channel strip
ARM, BYPASS, SOLO, MUTE = 0x00, 0x03, 0x08, 0x10
FADER_TOUCH, SHIFT = 0x68, 0x46

# Session Navigator
LINK, PAN, CHANNEL, SCROLL = 0x05, 0x2A, 0x36, 0x38
MASTER, CLICK, SECTION, MARKER = 0x3A, 0x3B, 0x3C, 0x3D
PREV, NEXT, PUSH_ENC = 0x2E, 0x2F, 0x20

# Automation
READ, WRITE, TOUCH = 0x4A, 0x4B, 0x4D

# Transport
LOOP, REWIND, FFWD = 0x56, 0x5B, 0x5C
STOP, PLAY, RECORD, FOOTSWITCH = 0x5D, 0x5E, 0x5F, 0x66

RGB_BUTTONS = frozenset((LINK, PAN, CHANNEL, SCROLL, READ, WRITE, TOUCH))

LED_OFF, LED_ON, LED_FLASH = 0x00, 0x7F, 0x01

# Single-colour LEDs (Bypass/Solo/Mute/Arm/transport) can't show RGB colour and
# usually can't dim -- MIDI only offers off / on / flashing. Some units treat a
# mid value as a dimmer state; set MONO_DIM to LED_FLASH (0x01) to try, or leave
# at LED_OFF so a "resting" mono button is simply dark.
MONO_DIM = LED_FLASH   # 0x01: confirmed on hardware to give a dim resting glow
NOTE_ON, NOTE_OFF, CC_STATUS, PITCH_BEND = 0x90, 0x80, 0xB0, 0xE0
RGB_RED, RGB_GREEN, RGB_BLUE = 0x91, 0x92, 0x93

GREEN, AMBER, BLUE, RED = (0, 127, 0), (127, 80, 0), (0, 0, 127), (127, 0, 0)

# Dim resting colours for dark-room navigation: same hue, low brightness.
DIM = 0.12
def _dim(colour):
    return tuple(int(c * DIM) for c in colour)
DIM_GREEN, DIM_AMBER, DIM_BLUE = _dim(GREEN), _dim(AMBER), _dim(BLUE)
OFF = (0, 0, 0)

# Which Live panel each button reflects. Its LED is lit while that panel is open.
V_DETAIL, V_BROWSER = 'Detail', 'Browser'
V_CLIP, V_DEVICE = 'Detail/Clip', 'Detail/DeviceChain'
V_SESSION, V_ARRANGER = 'Session', 'Arranger'
WATCHED_VIEWS = (V_DETAIL, V_BROWSER, V_CLIP, V_DEVICE, V_SESSION, V_ARRANGER)

# Encoder modes. Each is selected by its own button and owns the encoder,
# the Prev/Next buttons, and the encoder push.
MODES = (MASTER, PAN, CHANNEL, SCROLL, MARKER)
DEFAULT_MODE = SCROLL

# Loop acts as a held modifier: hold it and the encoder resizes the loop brace,
# Prev/Next nudge it by a bar. It only toggles the loop on release if the hold
# was never used for anything -- same trick as a shift key that is also a letter.
FLASH_TICKS = 2            # ~200 ms acknowledgement blink

ALL_NOTES = (
    ARM, BYPASS, SOLO, MUTE, FADER_TOUCH, SHIFT,
    LINK, PAN, CHANNEL, SCROLL, MASTER, CLICK, SECTION, MARKER,
    PREV, NEXT, PUSH_ENC, READ, WRITE, TOUCH,
    LOOP, REWIND, FFWD, STOP, PLAY, RECORD, FOOTSWITCH,
)


class FocusFader(ControlSurface):

    # ---------------------------------------------------------------- setup

    def __init__(self, c_instance, *a, **k):
        super(FocusFader, self).__init__(c_instance, *a, **k)
        self._param = None
        self._locked = False
        self._shift = False
        self._touching = False
        self._gate_until = 0.0
        self._natively_mapped = False
        self._mode = DEFAULT_MODE
        self._scrub_dir = 0
        self._loop_held = False
        self._loop_used = False
        self._click_held = False
        self._click_used = False
        self._fader_target = DEFAULT_FADER_TARGET
        self._press_time = {}
        self._song_listeners = []
        self._view_listeners = []
        self._track = None

        self._press = {
            ARM: self._arm, BYPASS: self._detail_view, SOLO: self._solo,
            MUTE: self._mute,
            LINK: self._link, PAN: self._mode_btn, CHANNEL: self._mode_btn,
            SCROLL: self._mode_btn, MASTER: self._mode_btn,
            SECTION: self._punch, MARKER: self._mode_btn,
            PREV: self._prev, NEXT: self._next, PUSH_ENC: self._push,
            READ: self._read, WRITE: self._write_btn, TOUCH: self._touch_btn,
            STOP: self._stop, PLAY: self._play, RECORD: self._record,
        }

        self._install_listeners()
        self._rebind(self.song().view.selected_parameter)
        self.request_rebuild_midi_map()
        self._refresh_leds()

        if DUMP_API:
            self._dump_api()
        self.log_message('FocusFader v2.6 loaded (native_map=%s)' % USE_NATIVE_MAP)
        self.show_message('FocusFader v2.6')

    def _install_listeners(self):
        view = self.song().view
        if hasattr(view, 'add_selected_parameter_listener'):
            view.add_selected_parameter_listener(self._on_selected_parameter)
            self.log_message('selected_parameter listener: OK')
        else:
            self.log_message('FATAL: no add_selected_parameter_listener')

        song = self.song()
        for name in ('is_playing', 'record_mode', 'metronome', 'loop',
                     'punch_in', 'punch_out'):
            try:
                getattr(song, 'add_%s_listener' % name)(self._refresh_leds)
                self._song_listeners.append(name)
            except Exception:
                pass

        # Panel open/closed -> LED. Live notifies per view name.
        app_view = self.application().view
        for name in WATCHED_VIEWS:
            try:
                app_view.add_is_view_visible_listener(name, self._refresh_leds)
                self._view_listeners.append(name)
            except Exception:
                pass

        # Solo/Mute/Arm follow the *selected* track, so rebind on selection change.
        try:
            view.add_selected_track_listener(self._on_selected_track)
        except Exception:
            self.log_message('no selected_track listener')
        self._on_selected_track()

    # ------------------------------------------------------------ midi plumbing

    def build_midi_map(self, midi_map_handle):
        script = self._c_instance.handle()

        if PROMISCUOUS in ('ch0', 'all'):
            for ch in (range(16) if PROMISCUOUS == 'all' else (CH,)):
                for n in range(128):
                    Live.MidiMap.forward_midi_note(script, midi_map_handle, ch, n)
                    Live.MidiMap.forward_midi_cc(script, midi_map_handle, ch, n)
                Live.MidiMap.forward_midi_pitchbend(script, midi_map_handle, ch)
            self.log_message('PROMISCUOUS=%s (observe only)' % PROMISCUOUS)
            self._natively_mapped = False
            return

        for note in ALL_NOTES:
            Live.MidiMap.forward_midi_note(script, midi_map_handle, CH, note)
        Live.MidiMap.forward_midi_cc(script, midi_map_handle, CH, ENCODER_CC)

        self._natively_mapped = False
        target = self._fader_param()
        if USE_NATIVE_MAP and target is not None:
            self._natively_mapped = self._try_native_map(midi_map_handle, target)
        if not self._natively_mapped:
            Live.MidiMap.forward_midi_pitchbend(script, midi_map_handle, CH)

        self.log_message('build_midi_map: fader=%s'
                         % ('native-map' if self._natively_mapped else 'forwarded'))

    def _try_native_map(self, midi_map_handle, target):
        for args in ((midi_map_handle, CH, target),
                     (midi_map_handle, CH, target, 0),
                     (midi_map_handle, CH, target, 0, False)):
            try:
                Live.MidiMap.map_midi_pitchbend(*args)
                return True
            except TypeError:
                continue
            except Exception as e:
                self.log_message('map_midi_pitchbend error: %r' % (e,))
                return False
        return False

    _TYPES = {0x80: 'NoteOff', 0x90: 'NoteOn', 0xB0: 'CC', 0xE0: 'PitchBend'}

    def receive_midi_chunk(self, midi_chunk):
        try:
            super(FocusFader, self).receive_midi_chunk(midi_chunk)
        except AttributeError:
            for m in midi_chunk:
                self.receive_midi(m)

    def receive_midi(self, midi_bytes):
        if DEBUG_MIDI and midi_bytes and midi_bytes[0] < 0xF0:
            self.log_message('MIDI in: %-10s ch%-2d %s' % (
                self._TYPES.get(midi_bytes[0] & 0xF0, '?'), midi_bytes[0] & 0x0F,
                ' '.join('%02X' % b for b in midi_bytes)))
        if PROMISCUOUS in ('ch0', 'all') or len(midi_bytes) < 3:
            return

        status, d1, d2 = midi_bytes[0] & 0xF0, midi_bytes[1], midi_bytes[2]
        if status == NOTE_ON:
            self._note(d1, d2 > 0)
        elif status == NOTE_OFF:
            self._note(d1, False)
        elif status == CC_STATUS and d1 == ENCODER_CC:
            self._encoder(d2)
        elif status == PITCH_BEND:
            self._fader(d1 | (d2 << 7))

    def _note(self, note, pressed):
        if note == FADER_TOUCH:
            self._touching = pressed
            if not pressed and not self._natively_mapped:
                self._push_motor()
            return
        if note == SHIFT:
            self._shift = pressed
            self._set_led(SHIFT, pressed)
            return
        if note in (REWIND, FFWD):
            self._scrub(note, pressed)
            return
        if note == LOOP:
            self._loop_btn(pressed)
            return
        if note == CLICK:
            self._click_btn(pressed)
            return
        if pressed:
            self._press_time[note] = time.time()
            if note in self._press:
                self._press[note](note)
        else:
            held = time.time() - self._press_time.get(note, time.time())
            if note == STOP and held >= LONG_PRESS_S:
                self._stop_long()

    # ------------------------------------------------------------- parameter

    def _on_selected_track(self):
        """Re-attach solo/mute/arm listeners to whichever track is now selected."""
        self._unbind_track()
        t = self.song().view.selected_track
        self._track = t
        for attr in ('solo', 'mute', 'arm'):
            try:
                getattr(t, 'add_%s_listener' % attr)(self._refresh_leds)
            except Exception:
                pass          # return/master tracks have no arm
        if self._fader_target == FADER_TARGET_VOLUME:
            self._rebind_fader_target()
        self._refresh_leds()

    def _unbind_track(self):
        t = self._track
        if t is None:
            return
        for attr in ('solo', 'mute', 'arm'):
            try:
                if getattr(t, '%s_has_listener' % attr)(self._refresh_leds):
                    getattr(t, 'remove_%s_listener' % attr)(self._refresh_leds)
            except Exception:
                pass
        self._track = None

    def _visible(self, name):
        try:
            return bool(self.application().view.is_view_visible(name))
        except Exception:
            return False

    def _param_alive(self):
        if self._param is None:
            return False
        try:
            self._param.value
            return True
        except (RuntimeError, AttributeError):
            return False

    def _on_selected_parameter(self):
        if self._locked:
            return
        p = self.song().view.selected_parameter
        if p is None and STICKY_FOCUS:
            if self._param_alive():
                return
            p = None
        self._rebind(p)
        self.request_rebuild_midi_map()

    def _rebind(self, param):
        old = self._param
        if old is not None:
            try:
                if old.value_has_listener(self._on_param_value):
                    old.remove_value_listener(self._on_param_value)
            except (RuntimeError, AttributeError):
                pass
        self._param = param
        if param is not None:
            param.add_value_listener(self._on_param_value)
            self.show_message('Focus: %s' % self._describe(param))
            if not self._natively_mapped:
                self._push_motor()

    def _on_param_value(self):
        if not self._natively_mapped:
            self._push_motor()

    def _describe(self, p):
        try:
            return '%s = %s' % (p.name, p.str_for_value(p.value))
        except Exception:
            return getattr(p, 'name', '?')

    def _norm(self, p):
        span = p.max - p.min
        return 0.0 if span == 0 else max(0.0, min(1.0, (p.value - p.min) / span))

    def _push_motor(self):
        if self._touching:
            return
        target = self._fader_param()
        if target is None:
            return
        try:
            v = int(self._norm(target) * 16383)
        except (RuntimeError, AttributeError):
            return
        self._gate_until = time.time() + MOTOR_SLEW_GATE_S
        self._send_midi((PITCH_BEND | CH, v & 0x7F, (v >> 7) & 0x7F))

    def _fader(self, value14):
        target = self._fader_param()
        if target is None:
            return
        try:
            if not target.is_enabled:
                return
        except (RuntimeError, AttributeError):
            return
        if not self._touching and time.time() < self._gate_until:
            return
        self._set_norm(target, value14 / 16383.0)

    def _set_norm(self, p, norm):
        norm = max(0.0, min(1.0, norm))
        val = p.min + norm * (p.max - p.min)
        p.value = round(val) if p.is_quantized else val

    # ------------------------------------------------------ encoder + modes

    def _encoder(self, raw):
        steps = raw & 0x3F
        if raw & ENCODER_SIGN_BIT:
            steps = -steps
        if steps == 0:
            return
        if self._loop_held:
            self._loop_used = True
            self._resize_loop(steps)
            return
        if self._click_held:
            self._click_used = True
            self._nudge_tempo(steps)
            return
        handler = {
            MASTER:  self._enc_master,
            PAN:     self._enc_pan,
            CHANNEL: self._enc_channel,
            SCROLL:  self._enc_scroll,
            MARKER:  self._enc_marker,
        }.get(self._mode)
        if handler:
            self._safe(handler, steps)

    def _enc_master(self, steps):
        p = self.song().master_track.mixer_device.volume
        self._set_norm(p, self._norm(p) + steps * ENCODER_STEP)
        self.show_message('Master: %s' % p.str_for_value(p.value))

    def _enc_pan(self, steps):
        p = self.song().view.selected_track.mixer_device.panning
        self._set_norm(p, self._norm(p) + steps * ENCODER_STEP)
        self.show_message('Pan: %s' % p.str_for_value(p.value))

    def _enc_channel(self, steps):
        self._step_track(1 if steps > 0 else -1)

    def _enc_scroll(self, steps):
        if self._shift:
            self._zoom(steps, horizontal=False)    # SHIFT+encoder = vertical zoom
        else:
            self._jump(steps * self._bar())

    def _enc_marker(self, steps):
        self._jump(steps * 4.0)

    def _bar(self):
        """Beats per bar from the actual time signature, not a hardcoded 4."""
        song = self.song()
        try:
            return song.signature_numerator * 4.0 / song.signature_denominator
        except Exception:
            return 4.0

    def _resize_loop(self, steps):
        song = self.song()
        bar = self._bar()
        try:
            song.loop_length = max(bar, song.loop_length + steps * bar)
            self.show_message('Loop length: %.0f bar(s)' % (song.loop_length / bar))
        except Exception as e:
            self.log_message('loop_length unsupported: %r' % (e,))

    def _move_loop(self, d):
        song = self.song()
        bar = self._bar()
        try:
            song.loop_start = max(0.0, song.loop_start + d * bar)
            self.show_message('Loop start: bar %.0f' % (song.loop_start / bar + 1))
        except Exception as e:
            self.log_message('loop_start unsupported: %r' % (e,))

    def _jump(self, beats):
        song = self.song()
        try:
            song.jump_by(beats)
        except Exception:
            song.current_song_time = max(0.0, song.current_song_time + beats)

    def _zoom(self, steps, horizontal):
        app_view = self.application().view
        nav = Live.Application.Application.View.NavDirection
        d = (nav.right if steps > 0 else nav.left) if horizontal \
            else (nav.down if steps > 0 else nav.up)
        for _ in range(abs(steps)):
            app_view.zoom_view(d, '', False)

    def _step_track(self, delta):
        song = self.song()
        tracks = list(song.tracks) + list(song.return_tracks) + [song.master_track]
        try:
            i = tracks.index(song.view.selected_track)
        except ValueError:
            return
        i = max(0, min(len(tracks) - 1, i + delta))
        song.view.selected_track = tracks[i]
        self.show_message('Track: %s' % tracks[i].name)


    def _mode_btn(self, note):
        self._mode = note
        self._refresh_leds()
        self.show_message('Encoder: %s' % {
            MASTER: 'Master', PAN: 'Pan', CHANNEL: 'Channel',
            SCROLL: 'Scroll/Zoom', SECTION: 'Section', MARKER: 'Marker',
        }.get(note, '?'))

    # --------------------------------------------------------------- buttons

    def _link(self, note):
        if self._shift:
            self._toggle_fader_target()
        else:
            self._locked = not self._locked
            self.show_message('Focus %s' % ('LOCKED' if self._locked else 'following'))
            if not self._locked:
                self._on_selected_parameter()
        self._refresh_leds()

    def _toggle_fader_target(self):
        self._fader_target = (FADER_TARGET_VOLUME
                              if self._fader_target == FADER_TARGET_FOCUS
                              else FADER_TARGET_FOCUS)
        self.show_message('Fader: %s' % ('selected track volume'
                          if self._fader_target == FADER_TARGET_VOLUME
                          else 'focused parameter'))
        self._rebind_fader_target()

    def _fader_param(self):
        """The parameter the fader currently drives, per the active target."""
        if self._fader_target == FADER_TARGET_VOLUME:
            try:
                return self.song().view.selected_track.mixer_device.volume
            except Exception:
                return None
        return self._param

    def _rebind_fader_target(self):
        """Re-point the motor and native map after a target or track change."""
        self.request_rebuild_midi_map()
        if not self._natively_mapped:
            self._push_motor()

    def _punch(self, note):
        """Section: punch-in; SHIFT+Section: punch-out. Flash only, no steady LED --
        one lamp cannot show two independent states."""
        song = self.song()
        if self._shift:
            self._safe(lambda: setattr(song, 'punch_out', not song.punch_out))
            self.show_message('Punch OUT %s' % self._onoff(song, 'punch_out'))
        else:
            self._safe(lambda: setattr(song, 'punch_in', not song.punch_in))
            self.show_message('Punch IN %s' % self._onoff(song, 'punch_in'))
        self._flash(SECTION)

    def _click_btn(self, pressed):
        """Held: encoder nudges tempo. Tapped: metronome (SHIFT: Capture MIDI)."""
        song = self.song()
        if pressed:
            self._click_held = True
            self._click_used = False
            return
        self._click_held = False
        if self._click_used:
            self._click_used = False
            return
        if self._shift:
            self._safe(getattr(song, SHIFT_CLICK_ACTION))
            self.show_message(SHIFT_CLICK_ACTION.replace('_', ' ').title())
            self._flash(CLICK)
        else:
            self._safe(lambda: setattr(song, 'metronome', not song.metronome))
            self.show_message('Metronome %s' % self._onoff(song, 'metronome'))
            self._refresh_leds()

    def _nudge_tempo(self, steps):
        song = self.song()
        try:
            song.tempo = max(20.0, min(999.0, song.tempo + steps * TEMPO_STEP))
            self.show_message('Tempo: %.2f BPM' % song.tempo)
        except Exception as e:
            self.log_message('tempo unsupported: %r' % (e,))

    def _onoff(self, obj, attr):
        try:
            return 'on' if getattr(obj, attr) else 'off'
        except Exception:
            return '?'

    def _loop_btn(self, pressed):
        """Held: encoder resizes the brace, Prev/Next move it. Tapped: toggles loop."""
        if pressed:
            self._loop_held = True
            self._loop_used = False
        else:
            self._loop_held = False
            if not self._loop_used:
                self.song().loop = not self.song().loop
            self._loop_used = False
            self._refresh_leds()

    def _prev(self, note):
        if self._loop_held:
            self._loop_used = True
            self._move_loop(-1)
        elif self._shift:
            self._safe(self.song().undo)
        else:
            self._nav(-1)

    def _next(self, note):
        if self._loop_held:
            self._loop_used = True
            self._move_loop(1)
        elif self._shift:
            self._safe(self.song().redo)
        else:
            self._nav(1)

    def _nav(self, d):
        if self._mode == MARKER:
            self._safe(self.song().jump_to_next_cue if d > 0
                       else self.song().jump_to_prev_cue)
        elif self._mode == SCROLL:
            self._safe(self._zoom, d, True)        # Prev/Next = horizontal zoom
        else:
            self._step_track(d)

    def _push(self, note):
        if self._mode == MASTER:
            self._safe(self._reset, self.song().master_track.mixer_device.volume)
        elif self._mode == PAN:
            self._safe(self._reset, self.song().view.selected_track.mixer_device.panning)
        elif self._mode == MARKER:
            self._safe(self.song().set_or_delete_cue)

    def _reset(self, p):
        p.value = p.default_value

    def _scrub(self, note, pressed):
        if pressed:
            self._scrub_dir = -1 if note == REWIND else 1
            self._do_scrub()
        else:
            self._scrub_dir = 0
        self._set_led(note, pressed)

    def _do_scrub(self):
        if self._scrub_dir == 0:
            return
        self._jump(self._scrub_dir * SCRUB_BEATS)
        try:
            self.schedule_message(SCRUB_REPEAT_TICKS, self._do_scrub)
        except Exception:
            pass                       # no repeat available; single step only

    def _arm(self, note):
        t = self.song().view.selected_track
        if t.can_be_armed:
            t.arm = not t.arm
        self._refresh_leds()

    def _solo(self, note):
        t = self.song().view.selected_track
        t.solo = not t.solo
        self._refresh_leds()

    def _mute(self, note):
        t = self.song().view.selected_track
        t.mute = not t.mute
        self._refresh_leds()

    def _detail_view(self, note):
        self._toggle_view(V_DETAIL)
        self._refresh_leds()

    def _touch_btn(self, note):
        self._toggle_view(V_BROWSER)
        self._refresh_leds()

    def _write_btn(self, note):
        v = self.application().view
        if self._shift:
            # "Maximise Clip View Panel Height" (Live 12, Cmd+Opt+E). Try the
            # dedicated API call if this build exposes one; otherwise fall back
            # to showing + focusing the clip detail. Check Log.txt API dump for
            # the exact method name on your version.
            self._safe(lambda: v.show_view(V_DETAIL))
            self._safe(lambda: v.show_view(V_CLIP))
            done = False
            for meth in ('toggle_maximized_clip_view', 'toggle_clip_view_maximized'):
                fn = getattr(v, meth, None)
                if fn is not None:
                    self._safe(fn)
                    done = True
                    break
            if not done:
                self._safe(lambda: v.focus_view(V_CLIP))
            self.show_message('Maximise clip view')
        else:
            self._safe(lambda: v.show_view(
                V_DEVICE if v.is_view_visible(V_CLIP) else V_CLIP))
        self._refresh_leds()

    def _read(self, note):
        if self._shift:
            song = self.song()
            self._safe(lambda: setattr(song, 'draw_mode', not song.draw_mode))
        else:
            v = self.application().view
            self._safe(lambda: v.show_view(
                V_SESSION if v.is_view_visible(V_ARRANGER) else V_ARRANGER))
        self._refresh_leds()

    def _toggle_view(self, name):
        v = self.application().view
        self._safe(lambda: v.hide_view(name) if v.is_view_visible(name)
                   else v.show_view(name))

    def _play(self, note):
        song = self.song()
        if self._shift:
            self._safe(song.continue_playing)     # resume from the pause point
        else:
            song.is_playing = not song.is_playing

    def _stop(self, note):
        # short press = stop (+ SHIFT: return to zero). Long press handled on release.
        self.song().stop_playing()
        if self._shift:
            self.song().current_song_time = 0.0

    def _stop_long(self):
        self._safe(lambda: setattr(self.song(), 'back_to_arranger', False))
        self._safe(lambda: self.application().view.show_view(V_ARRANGER))
        self.show_message('Back to Arrangement')

    def _record(self, note):
        self.song().record_mode = not self.song().record_mode

    # ------------------------------------------------------------------ LEDs

    def _set_led(self, ident, on, colour=GREEN):
        """Backwards-compatible on/off. For dim/bright control use _led_colour."""
        self._led_colour(ident, colour if on else OFF)

    def _led_colour(self, ident, colour):
        """Drive an LED to an explicit RGB colour. (0,0,0) is off; a low-value
        colour is a dim resting glow."""
        if ident in RGB_BUTTONS:
            r, g, b = colour
            self._send_midi((RGB_RED, ident, r & 0x7F))
            self._send_midi((RGB_GREEN, ident, g & 0x7F))
            self._send_midi((RGB_BLUE, ident, b & 0x7F))
            # For RGB buttons the note-on just enables the LED; colour does the work.
            self._send_midi((NOTE_ON | CH, ident, LED_ON if any(colour) else LED_OFF))
        else:
            # Mono LED: can't render hue. Full colour -> on; a dim colour (all
            # channels below the dim ceiling) -> MONO_DIM; nothing -> off.
            if not any(colour):
                level = LED_OFF
            elif max(colour) <= int(127 * DIM) + 1:
                level = MONO_DIM
            else:
                level = LED_ON
            self._send_midi((NOTE_ON | CH, ident, level))

    def _flash(self, ident, colour=AMBER):
        """Brief acknowledgement blink; steady state is restored afterwards."""
        self._set_led(ident, True, colour)
        try:
            self.schedule_message(FLASH_TICKS, self._refresh_leds)
        except Exception:
            self._set_led(ident, False)

    def _refresh_leds(self, *_):
        for m in MODES:
            self._set_led(m, m == self._mode, BLUE)
        # Link LED encodes both the fader mode (hue) and lock state (brightness):
        #   focus mode  -> green : dim = following, bright = locked
        #   volume mode -> blue  : dim = following, bright = locked
        if self._fader_target == FADER_TARGET_VOLUME:
            self._led_colour(LINK, BLUE if self._locked else DIM_BLUE)
        else:
            self._led_colour(LINK, GREEN if self._locked else DIM_GREEN)
        song = self.song()
        self._set_led(SECTION, False)      # flash-only; two states, one lamp

        for ident, attr, colour in ((PLAY, 'is_playing', GREEN),
                                    (RECORD, 'record_mode', RED),
                                    (LOOP, 'loop', AMBER),
                                    (CLICK, 'metronome', AMBER)):
            try:
                self._set_led(ident, bool(getattr(song, attr)), colour)
            except Exception:
                pass

        # Panel buttons: dim resting glow when closed, bright when open.
        for ident, name in ((BYPASS, V_DETAIL), (TOUCH, V_BROWSER),
                            (WRITE, V_CLIP), (READ, V_SESSION)):
            self._led_colour(ident, BLUE if self._visible(name) else DIM_BLUE)

        # Channel strip: solo=blue (matches Live), mute=amber, arm=red.
        t = self._track
        for ident, attr, colour in ((SOLO, 'solo', BLUE),
                                    (MUTE, 'mute', AMBER),
                                    (ARM, 'arm', RED)):
            try:
                self._led_colour(ident, colour if bool(getattr(t, attr)) else OFF)
            except Exception:
                self._led_colour(ident, OFF)

    def refresh_state(self):
        try:
            super(FocusFader, self).refresh_state()
        except AttributeError:
            pass
        self._refresh_leds()

    # -------------------------------------------------------------- plumbing

    def _dump_api(self):
        """One-shot introspection. Anything with 'max', 'zoom', 'view' or 'focus'
        in its name is a candidate for the maximise-editor hunt."""
        try:
            v = self.application().view
            self.log_message('API available_main_views: %r'
                             % (list(v.available_main_views()),))
            hits = [n for n in dir(v) if not n.startswith('_')]
            self.log_message('API Application.View: %s' % ', '.join(sorted(hits)))
        except Exception as e:
            self.log_message('API dump (view) failed: %r' % (e,))
        try:
            song = self.song()
            interesting = [n for n in dir(song)
                           if not n.startswith(('_', 'add_', 'remove_'))
                           and not n.endswith('_has_listener')]
            self.log_message('API Song: %s' % ', '.join(sorted(interesting)))
        except Exception as e:
            self.log_message('API dump (song) failed: %r' % (e,))

    def _safe(self, fn, *args):
        """Live's API surface varies by version. Never let one call kill a press."""
        try:
            fn(*args)
        except Exception as e:
            self.log_message('unsupported: %s%r -> %r'
                             % (getattr(fn, '__name__', fn), args, e))

    def disconnect(self):
        self._scrub_dir = 0
        self._loop_held = False
        song = self.song()
        for name in self._song_listeners:
            try:
                getattr(song, 'remove_%s_listener' % name)(self._refresh_leds)
            except Exception:
                pass
        self._unbind_track()
        try:
            app_view = self.application().view
            for name in self._view_listeners:
                if app_view.is_view_visible_has_listener(name, self._refresh_leds):
                    app_view.remove_is_view_visible_listener(name, self._refresh_leds)
        except Exception:
            pass
        try:
            if song.view.selected_track_has_listener(self._on_selected_track):
                song.view.remove_selected_track_listener(self._on_selected_track)
        except Exception:
            pass
        if self._param is not None:
            try:
                if self._param.value_has_listener(self._on_param_value):
                    self._param.remove_value_listener(self._on_param_value)
            except Exception:
                pass
        try:
            view = song.view
            if view.selected_parameter_has_listener(self._on_selected_parameter):
                view.remove_selected_parameter_listener(self._on_selected_parameter)
        except Exception:
            pass
        for ident in ALL_NOTES:
            self._set_led(ident, False)
        super(FocusFader, self).disconnect()
