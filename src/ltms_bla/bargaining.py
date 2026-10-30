"""Execute protocol.ipynb's actual bargaining code with a typed validator."""
from types import FunctionType

from protocol import validate_bargaining
from protocol.companion import load_method_notebook
from .records import CorridorOffer, implies


def validate_corridors(offers, targets, minima, prices, round_budget):
    if any(not isinstance(o, CorridorOffer) or not o.certificate.certified
           or not o.certificate.compatible for o in offers):
        raise ValueError('bargaining accepts only certified compatible offers')
    if any(not implies(o.contract.guarantee, o.access) for o in offers):
        raise ValueError('offer does not imply the fixed sufficient-access predicate')
    if len({(o.service, o.access) for o in offers}) > 1:
        raise ValueError('offers must share one selected service and client model')
    # Reuse all numeric/budget validation. Only the charging-specific booking
    # eligibility check is replaced; no corridor is cast into a Booking.
    return validate_bargaining((), targets, minima, prices, round_budget)


def load_bargain(root):
    original = load_method_notebook(root/'notebooks'/'protocol.ipynb').bargain
    return FunctionType(original.__code__,
                        {**original.__globals__, 'validate_bargaining': validate_corridors},
                        original.__name__, original.__defaults__)
