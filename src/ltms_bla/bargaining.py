"""Execute the charging notebook's actual bargaining code with a typed validator."""
from types import FunctionType

from protocol import validate_bargaining
from protocol.companion import load_method_notebook
from .records import CorridorOffer, certify_template


def validate_corridors(offers, targets, minima, prices, round_budget):
    for offer in offers:
        if not isinstance(offer, CorridorOffer):
            raise TypeError('corridor bargaining requires CorridorOffer records')
        certify_template(offer)
    if len({o.id for o in offers}) != len(offers):
        raise ValueError('duplicate offer identities')
    if len({(o.service.key, o.access, o.snapshot) for o in offers}) > 1:
        raise ValueError('offers must share one selected service, client model and snapshot')
    # Reuse all numeric/budget validation. Only the charging-specific booking
    # eligibility check is replaced; no corridor is cast into a Booking.
    return validate_bargaining((), targets, minima, prices, round_budget)


def load_bargain(root):
    original = load_method_notebook(root/'notebooks'/'protocol.ipynb').bargain
    return FunctionType(original.__code__,
                        {**original.__globals__, 'validate_bargaining': validate_corridors},
                        original.__name__, original.__defaults__)
