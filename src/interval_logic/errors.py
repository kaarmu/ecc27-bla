"""Public exception types for interval logic."""


class IntervalLogicError(Exception):
    """Base class for interval-logic errors."""


class FormulaSyntaxError(IntervalLogicError, ValueError):
    """An interval-logic expression contains invalid syntax."""

    def __init__(self, message: str, source: str, position: int):
        self.message = message
        self.source = source
        self.position = max(0, min(position, len(source)))
        self.line = source.count("\n", 0, self.position) + 1
        line_start = source.rfind("\n", 0, self.position) + 1
        self.column = self.position - line_start + 1
        super().__init__(f"{message} at line {self.line}, column {self.column}")


class TraceValidationError(IntervalLogicError, ValueError):
    """A complete trace or evaluation request is invalid."""


class UnsupportedReachabilityError(IntervalLogicError, NotImplementedError):
    """A reachability backend cannot soundly evaluate the requested formula."""


class UnsupportedTemporalParameterError(UnsupportedReachabilityError):
    """A reachability backend cannot interpret a temporal parameter."""
