"""Meaningful exception types so callers can tell *why* a run failed."""


class DataIntegrityError(Exception):
    """Base class for every error raised intentionally by this package."""


class CSVLoadError(DataIntegrityError):
    """A CSV file could not be read or is structurally malformed."""


class ConfigError(DataIntegrityError):
    """The configuration is invalid (unknown key, bad value, unreadable file)."""


class SchemaError(DataIntegrityError):
    """A schema problem is so severe that records cannot be matched at all."""
