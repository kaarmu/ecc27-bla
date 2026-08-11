class IntervalLogicError(Exception):
    """Base class for interval-logic errors."""


class ParseError(IntervalLogicError, ValueError):
    """An interval-logic expression contains invalid syntax."""

    def __init__(self, message: str, source: str, position: int):
        self.message = message
        self.source = source
        self.position = max(0, min(position, len(source)))
        self.line = source.count("\n", 0, self.position) + 1
        line_start = source.rfind("\n", 0, self.position) + 1
        self.column = self.position - line_start + 1
        super().__init__(
            f"{message} at line {self.line}, column {self.column}"
        )


class DerivedExpressionError(IntervalLogicError):
    """A derived expression could not be lowered to the core language."""


class DerivedExpressionCycleError(DerivedExpressionError):
    """A derived expression recursively lowered to itself."""


class ExpansionLimitError(IntervalLogicError):
    """Interval normalization would exceed its configured node budget."""

    def __init__(self, limit: int, attempted: int):
        self.limit = limit
        self.attempted = attempted
        super().__init__(
            f"normalization would create {attempted} nodes; limit is {limit}"
        )
