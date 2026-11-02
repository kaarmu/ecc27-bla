"""Execute protocol.ipynb's actual bargaining code with a typed validator."""
from types import FunctionType

from protocol import validate_bargaining
from protocol.companion import load_method_notebook


def load_bargain(root, validate_offers):
    """protocol.ipynb's bargain, with its booking eligibility check replaced by ``validate_offers``."""
    def validate(offers, targets, minima, prices, round_budget):
        validate_offers(offers)
        # Reuse all numeric/budget validation; no corridor is cast into a Booking.
        return validate_bargaining((), targets, minima, prices, round_budget)

    original = load_method_notebook(root/'notebooks'/'protocol.ipynb').bargain
    return FunctionType(original.__code__, {**original.__globals__, 'validate_bargaining': validate},
                        original.__name__, original.__defaults__)
