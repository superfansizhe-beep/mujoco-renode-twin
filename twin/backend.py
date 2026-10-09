"""The demo app's own controllers: the chain-check drive + the mode factory.

The interface and the balance controller the exam firmware includes
live one level down in bot.backend; this module keeps what belongs to
the balance demo app -- the constant-duty drive check and the
make_backend() picker that maps a mode name to a controller.
"""
from bot.backend import BalanceController, Controller
from bot.mailbox import MotorFrame, SensorFrame


class DriveController(Controller):
    """Constant duty both sides -- the chain-check demo (+ = forward)."""

    def __init__(self, duty: int = 300, dt: float = 0.005) -> None:
        self.name = f"drive({duty:+d})"
        self.duty = duty
        self.dt = dt

    def reset(self) -> None:
        pass

    def step(self, s: SensorFrame) -> MotorFrame:
        return MotorFrame(duty_l=self.duty, duty_r=self.duty)


def make_backend(mode: str, dt: float, v_batt: float,
                 drive_duty: int = 300) -> Controller:
    if mode == "drive":
        return DriveController(duty=drive_duty, dt=dt)
    if mode == "balance":
        return BalanceController(dt=dt, v_batt=v_batt)
    raise ValueError(f"unknown mode {mode!r}")
