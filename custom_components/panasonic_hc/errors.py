"""Shared controller failures and non-empty backend error descriptions."""

from collections.abc import Iterator

from bleak.exc import BleakError


class PanasonicHCException(Exception):
    """Controller communication or confirmation failed."""


class PanasonicAuthenticationError(PanasonicHCException):
    """The selected Bluetooth peer could not establish a protected session."""


def describe_error(error: BaseException) -> str:
    """Timeouts and some backends otherwise render as an empty string."""
    if message := str(error).strip():
        return message
    if isinstance(error, TimeoutError):
        return "operation timed out"
    return type(error).__name__


class PanasonicSourceUnavailable(BleakError):
    """No backend was allocated because the saved source is not ready yet."""


def _causes(error: BaseException) -> Iterator[BaseException]:
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def is_source_unavailable(error: BaseException) -> bool:
    return any(isinstance(cause, PanasonicSourceUnavailable) for cause in _causes(error))


def is_authentication_error(error: BaseException) -> bool:
    """Recognize ATT security failures, including wrapped ESPHome errors."""
    for current in _causes(error):
        detail = getattr(current, "error", None)
        if getattr(detail, "error", None) in (5, 15):
            return True
        text = str(current).lower()
        if "insufficient authentication" in text or "insufficient encryption" in text:
            return True
        if getattr(current, "dbus_error", None) == "org.bluez.Error.NotAuthorized":
            return True
    return False
