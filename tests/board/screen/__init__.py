"""The board's screen, as the panel shows it."""

from dataclasses import dataclass

from board.screen.captures import Captures
from board.screen.display import Display


@dataclass
class Screen:
    """The board's screen: the X server and its output, and screenshots of what the panel shows.

    Attributes:
        display: the X server and the output it drives.
        captures: screenshots of the panel's middle third.
    """

    display: Display
    captures: Captures
