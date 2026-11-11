"""Exception types."""


class Error(Exception):
    """A runtime failure (exit status 1)."""


class UsageError(Exception):
    """A command-line usage mistake (exit status 2)."""
