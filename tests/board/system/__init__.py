"""The board's operating system, as tests read and set it."""

from dataclasses import dataclass

from board.system.clock import Clock
from board.system.memory import Memory
from board.system.soak import Soak
from board.system.timezone import Timezone


@dataclass
class System:
    """The board's operating system: its clock and time zone, its memory, and the kiosk-soak sampler.

    Attributes:
        clock: the clock and its time sync.
        timezone: the zone and the local time.
        memory: memory and the kernel's out-of-memory record.
        soak: the kiosk-soak sampler, its timer and its log.
    """

    clock: Clock
    timezone: Timezone
    memory: Memory
    soak: Soak
