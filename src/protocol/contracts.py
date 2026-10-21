"""Saturated contract algebra and exact Boolean normalization."""
from dataclasses import dataclass
from fractions import Fraction as F
import portion as P
import interval_logic as il
from itertools import combinations

def _dual(literal):
    return il.to_nnf(~literal)

def _minimal_clauses(clauses):
    clauses = {c for c in clauses if not any(_dual(lit) in c for lit in c)}
    if frozenset() in clauses:
        return {frozenset()}
    return {c for c in clauses if not any(other < c for other in clauses)}

def _cnf(formula):
    if isinstance(formula, il.Boolean):
        return set() if formula.value else {frozenset()}
    if isinstance(formula, il.And):
        return _minimal_clauses(set().union(*(_cnf(c) for c in formula.operands)))
    if isinstance(formula, il.Or):
        result = {frozenset()}
        for child in formula.operands:
            result = _minimal_clauses({a | b for a in result for b in _cnf(child)})
        return result
    return {frozenset((formula,))}

def normalize(formula, now=0):
    current = il.to_nnf(formula)
    while True:
        clauses = _cnf(current)
        while True:
            additions = set()
            for left, right in combinations(clauses, 2):
                for literal in left:
                    complement = _dual(literal)
                    if complement in right:
                        additions.add((left - {literal}) | (right - {complement}))
            reduced = _minimal_clauses(clauses | additions)
            if reduced == clauses:
                break
            clauses = reduced
        ordered = sorted(clauses, key=lambda c: tuple(sorted(map(str, c))))
        result = il.And(il.Or(sorted(c, key=str)) for c in ordered).simplify(anchor=now)
        if result == current:
            return result
        current = result

@dataclass(frozen=True)
class Contract:
    """Saturated assumption/guarantee contract; Section II algebra.

    Refinement C1 <= C2 means A2 implies A1 and G1 implies G2.
    All operations use stored saturated guarantees.
    """
    assumption: il.Formula
    guarantee: il.Formula

    def __post_init__(self):
        a = il.to_nnf(self.assumption)
        object.__setattr__(self, 'assumption', a)
        object.__setattr__(self, 'guarantee', il.to_nnf(il.as_formula(self.guarantee) | ~a))

    def __str__(self):
        return f'⟨ {self.assumption} ∣ {self.guarantee} ⟩'

    def _repr_latex_(self):
        """Display the stored saturated contract as an assumption/guarantee pair."""
        return (r'$\displaystyle \left\langle '
                + il.format_latex(self.assumption) + r' \;\middle\vert\; '
                + il.format_latex(self.guarantee) + r' \right\rangle$')

    def compose(self, other):
        g = self.guarantee & other.guarantee
        return Contract((self.assumption & other.assumption) | ~g, g)

    def quotient(self, component):
        a = self.assumption & component.guarantee
        return Contract(a, (self.guarantee & component.assumption) | ~a)

    def conjoin(self, other):
        return Contract(self.assumption | other.assumption,
                        self.guarantee & other.guarantee)

    def normalize(self, now=0):
        return Contract(normalize(self.assumption, now), normalize(self.guarantee, now))
