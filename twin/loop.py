"""The balance demo's loop: BotLoop plus the app-side controller defaults.

BotLoop (bot/loop.py) carries the whole coupling discipline; this
subclass adds what belongs to the demo application -- the mode and
drive_duty defaults, the make_backend() default factory, and the
runtime set_mode() controller swap.
"""
from bot import motors
from bot.backend import Controller
from bot.loop import COUPLING_S, BotLoop

from .backend import make_backend


class TwinLoop(BotLoop):
    def __init__(self, mode: str = "balance", battery: str = "3s",
                 drive_duty: int = 300,
                 controller: Controller | None = None) -> None:
        super().__init__(
            battery=battery,
            controller=(controller if controller is not None else
                        make_backend(mode, COUPLING_S,
                                     motors.BATTERY_NOMINAL[battery],
                                     drive_duty)))

    def set_mode(self, mode: str, drive_duty: int = 300) -> None:
        """Swap the controller at runtime -- STUB backends only. A firmware
        backend is chosen at startup (--backend renode) and does not come
        back after a swap; the web "mode" button is a stub-land control."""
        self.controller = make_backend(mode, COUPLING_S, self.v_batt,
                                       drive_duty)
        self.controller.reset()
