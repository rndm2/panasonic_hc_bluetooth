"""Shared controller failures and non-empty backend error descriptions."""


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


def is_authentication_error(error: BaseException) -> bool:
    """Recognize ATT security failures, including wrapped ESPHome errors."""
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        detail = getattr(current, "error", None)
        if getattr(detail, "error", None) in (5, 15):
            return True
        text = str(current).lower()
        if "insufficient authentication" in text or "insufficient encryption" in text:
            return True
        if getattr(current, "dbus_error", None) == "org.bluez.Error.NotAuthorized":
            return True
        current = current.__cause__ or current.__context__
    return False
