"""Small, structure-preserving AST transformations."""

from __future__ import annotations

from collections.abc import Callable

from .ast import Formula, as_formula


def replace(
    formula: Formula | str,
    *functions: Callable[[Formula], Formula | str],
) -> Formula:
    """Apply functions in order to every node, bottom-up."""

    formula = as_formula(formula)
    for function in functions:
        if not callable(function):
            raise TypeError("replacement functions must be callable")
    children = tuple(replace(child, *functions) for child in formula.children)
    result = formula._with_children(children) if children != formula.children else formula
    for function in functions:
        result = as_formula(function(result))
    return result
