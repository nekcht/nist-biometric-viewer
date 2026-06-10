"""Domain-specific exceptions."""


class NistComparatorError(Exception):
    """Base error for expected application failures."""


class NistParseError(NistComparatorError):
    """Raised when a transaction cannot be read at all."""
