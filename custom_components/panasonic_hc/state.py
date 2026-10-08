"""Merge partial measurements without inventing values or extending freshness."""

from dataclasses import dataclass, replace

from .protocol import StatusReport

CURRENT_TEMPERATURE_MAX_AGE = 600


@dataclass(frozen=True, slots=True)
class Status:
    power: bool
    mode: str
    powersave: bool | None
    curtemp: float | None
    settemp: float
    fanspeed: str


class ControllerState:
    """Clock-free state model; callers supply monotonic timestamps."""

    def __init__(self) -> None:
        self.status: Status | None = None
        self.temperature: float | None = None
        self.temperature_at: float | None = None
        self.status_at: float | None = None
        self.generation = 0
        self.rejected_temperatures = 0

    def current_temperature(self, now: float) -> float | None:
        if self.temperature_at is None or now - self.temperature_at >= CURRENT_TEMPERATURE_MAX_AGE:
            return None
        return self.temperature

    def apply(self, report: StatusReport, now: float) -> bool:
        """Return whether this report contained an accepted temperature sample."""
        value = report.curtemp
        accepted = (
            value is not None
            and -40 <= value <= 70
            and (self.temperature is None or abs(value - self.temperature) <= 20)
        )
        if accepted:
            self.temperature, self.temperature_at = value, now
        elif value is not None:
            self.rejected_temperatures += 1
        old = self.status
        self.status = Status(
            report.power,
            report.mode.name,
            report.powersave if report.powersave is not None else (old.powersave if old else None),
            self.current_temperature(now),
            report.temp,
            report.fanspeed.name,
        )
        self.status_at = now
        self.generation += 1
        return accepted

    def expire_temperature(self) -> None:
        # Keep the validation anchor so repeated corrupt readings cannot become
        # valid merely because the last good sample expired.
        self.temperature_at = None
        if self.status is not None:
            self.status = replace(self.status, curtemp=None)

    def disconnected(self) -> None:
        self.temperature = self.temperature_at = self.status_at = None
        if self.status is not None:
            # Optional eco state must not leak into a new session's short status.
            self.status = replace(self.status, curtemp=None, powersave=None)
