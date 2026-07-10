"""FocusFader - a "last-clicked parameter" control surface for the PreSonus FaderPort V2.

Install to:
    ~/Music/Ableton/User Library/Remote Scripts/FocusFader        (macOS)

Then select "FocusFader" as a Control Surface in Live's Settings > Link/MIDI,
with Input and Output both set to the FaderPort port.

WHY get_capabilities() LOOKS LIKE THIS
--------------------------------------
We declare PORTS_KEY but deliberately NOT CONTROLLER_ID_KEY.

  * PORTS_KEY with props=[SCRIPT, REMOTE] tells Live that this port carries
    control-surface traffic. Without it, Live may bind the port as REMOTE-only:
    MIDI mapping and Track input still work, but MIDI forwarding requested in
    build_midi_map() never reaches receive_midi(). The script goes deaf while
    the port still visibly passes MIDI to tracks.

  * CONTROLLER_ID_KEY is what lets Live auto-detect hardware and load a script
    for it unprompted. Live's stock "Faderport" script declares vendor 6479 /
    product 517 / "PreSonus FP2" and then does nothing but
    `return MackieControl(c_instance)`. That is the MCU script which owns the
    fader and causes it to ignore you until you reselect the track. We omit the
    key so FocusFader is only ever loaded when you pick it by hand.
"""
from __future__ import absolute_import, print_function, unicode_literals

from .FocusFader import FocusFader

try:
    from ableton.v2.control_surface.capabilities import (
        PORTS_KEY, REMOTE, SCRIPT, inport, outport)

    def get_capabilities():
        return {
            PORTS_KEY: [
                inport(props=[SCRIPT, REMOTE]),
                outport(props=[SCRIPT, REMOTE]),
            ],
        }
except ImportError:  # pragma: no cover - very old Live; omit capabilities
    pass


def create_instance(c_instance):
    return FocusFader(c_instance)
