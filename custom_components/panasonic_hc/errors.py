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
