class IntervalLogicError(Exception):
    """Base class for interval-logic errors."""


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
