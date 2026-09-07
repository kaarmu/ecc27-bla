"""Parser for the canonical Unicode syntax and its direct ASCII aliases."""

from __future__ import annotations

import json
import re

from .ast import (
    Always,
    And,
    Boolean,
    Equal,
    Equivalent,
    Eventually,
    Formula,
    Implies,
    NaturalLiteral,
    NumericTerm,
    Not,
    Or,
    Proposition,
    Release,
    RestrictiveSelection,
    Selection,
    Signal,
    Until,
    VacuousSelection,
)
from .errors import FormulaSyntaxError
from .temporal import NUMBER_PATTERN, TemporalParameter, coerce_temporal_parameter


_NUMBER = re.compile(NUMBER_PATTERN)
_NATURAL = re.compile(r"\d+")
_IDENTIFIER = re.compile(r"(?:[^\W\d]|_)\w*", re.UNICODE)


def parse_formula(source: str) -> Formula:
    """Parse one interval-logic formula."""

    if not isinstance(source, str):
        raise TypeError("source must be a string")
    # A ')' after a postfix duration can close either the parameter or an
    # enclosing expression. Prefer the usual grouping interpretation; retry
    # only these lexical choices if the enclosing parse fails. This preserves
    # both bare-duration formatting and explicit d) syntax at arbitrary depth.
    pending = [{}]
    furthest_error = None
    while pending:
        parser = _Parser(source, pending.pop())
        try:
            return parser.parse()
        except FormulaSyntaxError as error:
            if furthest_error is None or error.position > furthest_error.position:
                furthest_error = error
            prefix = {}
            for position, consume in parser.duration_choices:
                if position not in parser.forced_closes:
                    pending.append(prefix | {position: not consume})
                prefix[position] = consume
    raise furthest_error


class _Parser:
    def __init__(self, source: str, forced_closes: dict[int, bool] | None = None):
        self.source = source
        self.position = 0
        self.group_depth = 0
        self.forced_closes = {} if forced_closes is None else forced_closes
        self.duration_choices: list[tuple[int, bool]] = []

    def parse(self) -> Formula:
        self._skip()
        if self._at_end:
            self._fail("expected an expression")
        expression = self._parse_equivalent()
        self._skip()
        if not self._at_end:
            self._fail(f"unexpected token {self.source[self.position]!r}")
        return expression

    def _parse_equivalent(self) -> Formula:
        expression = self._parse_implies()
        while self._match_operator("↔", "<->", keyword="equivalent"):
            expression = Equivalent(expression, self._parse_implies())
        return expression

    def _parse_implies(self) -> Formula:
        left = self._parse_or()
        if self._match_operator("→", "->", keyword="implies"):
            return Implies(left, self._parse_implies())
        return left

    def _parse_or(self) -> Formula:
        operands = [self._parse_and()]
        while self._match_operator("∨", "|", keyword="or"):
            operands.append(self._parse_and())
        return operands[0] if len(operands) == 1 else Or(operands)

    def _parse_and(self) -> Formula:
        operands = [self._parse_temporal()]
        while self._match_operator("∧", "&", keyword="and"):
            operands.append(self._parse_temporal())
        return operands[0] if len(operands) == 1 else And(operands)

    def _parse_temporal(self) -> Formula:
        left = self._parse_unary()
        matched = self._match_temporal_operator()
        if matched is None:
            return left
        node = matched
        parameter = self._parse_parameter_suffix()
        return node(left, self._parse_temporal(), parameter)

    def _parse_unary(self) -> Formula:
        if self._match_operator("¬", "!", keyword="not"):
            return Not(self._parse_unary())
        if self._match_operator("□", keyword="always"):
            parameter = self._parse_parameter_suffix()
            return Always(self._parse_unary(), parameter)
        if self._match_operator("◇", keyword="eventually"):
            parameter = self._parse_parameter_suffix()
            return Eventually(self._parse_unary(), parameter)
        return self._parse_primary()

    def _parse_primary(self) -> Formula:
        self._skip()
        if self._at_end:
            self._fail("expected an expression")

        selection = self._try_selection()
        if selection is not None:
            return selection

        if self._match_symbol("("):
            self.group_depth += 1
            try:
                expression = self._parse_equivalent()
                self._expect_symbol(")", "expected ')' to close expression")
            finally:
                self.group_depth -= 1
            return expression
        if self._match_symbol("⊤") or self._match_keyword("true"):
            return Boolean(True)
        if self._match_symbol("⊥") or self._match_keyword("false"):
            return Boolean(False)

        start = self.position
        left = self._parse_term_or_name()
        if left is None:
            self._fail("expected a proposition, equality, selection, or parenthesized expression")
        equality = self._match_equality()
        if equality is not None:
            left_term = left if isinstance(left, NumericTerm) else Signal(left)
            right = self._parse_term()
            result: Formula = Equal(left_term, right)
            return Not(result) if equality == "!=" else result
        if isinstance(left, NaturalLiteral):
            self._fail("a natural literal is only valid in an equality", start)
        if isinstance(left, Signal):
            return Proposition(left.name)
        return Proposition(left)

    def _try_selection(self) -> Formula | None:
        self._skip()
        start = self.position
        if self._match_keyword("select"):
            self._expect_symbol("(", "expected '(' after 'select'")
            close = ")"
        elif self._match_symbol("⟨"):
            close = "⟩"
        elif self.source.startswith("<->", self.position):
            return None
        elif self._match_symbol("<"):
            close = ">"
        else:
            return None

        depth_before = self.group_depth
        if close == ")":
            self.group_depth += 1
        try:
            inside = self._parse_equivalent()
            if self._match_symbol(","):
                outside = self._parse_equivalent()
                self._expect_symbol(close, f"expected {close!r} to close selection")
                self.group_depth = depth_before
                parameter = self._parse_parameter_suffix()
                return Selection(inside, outside, parameter)
            self._expect_symbol(close, f"expected {close!r} to close selection")
            self.group_depth = depth_before
            restrictive = self._match_symbol("*")
            parameter = self._parse_parameter_suffix()
            trailing_star = self._match_symbol("*")
            if restrictive or trailing_star:
                return RestrictiveSelection(inside, parameter)
            return VacuousSelection(inside, parameter)
        except FormulaSyntaxError:
            if self.position == start:
                return None
            raise
        finally:
            self.group_depth = depth_before

    def _parse_term_or_name(self) -> NumericTerm | str | None:
        self._skip()
        natural = _NATURAL.match(self.source, self.position)
        if natural:
            self.position = natural.end()
            return NaturalLiteral(int(natural.group()))
        name = self._parse_name()
        return name

    def _parse_term(self) -> NumericTerm:
        value = self._parse_term_or_name()
        if value is None:
            self._fail("expected a signal name or natural literal")
        if isinstance(value, NumericTerm):
            return value
        return Signal(value)

    def _parse_name(self) -> str | None:
        self._skip()
        if not self._at_end and self.source[self.position] == '"':
            start = self.position
            try:
                name, length = json.JSONDecoder().raw_decode(self.source[start:])
            except json.JSONDecodeError:
                self._fail("invalid JSON quoted name", start)
            if not name:
                self._fail("a quoted name must not be empty", start)
            self.position += length
            return name
        if not self._at_end and self.source[self.position] == "`":
            start = self.position
            self.position += 1
            characters: list[str] = []
            while not self._at_end:
                char = self.source[self.position]
                self.position += 1
                if char == "`":
                    if not characters:
                        self._fail("a quoted name must not be empty", start)
                    return "".join(characters)
                if char == "\\":
                    if self._at_end:
                        self._fail("unterminated escape in quoted name", start)
                    char = self.source[self.position]
                    self.position += 1
                characters.append(char)
            self._fail("unterminated quoted name", start)
        match = _IDENTIFIER.match(self.source, self.position)
        if match is None:
            return None
        self.position = match.end()
        return match.group()

    def _match_temporal_operator(self):
        for word, node in (
            ("until", Until),
            ("release", Release),
            ("U", Until),
            ("R", Release),
        ):
            if self._match_keyword(word, allow_parameter_suffix=True):
                return node
        return None

    def _parse_parameter_suffix(self) -> TemporalParameter:
        self._skip()
        if not self._match_symbol("_"):
            return None
        self._skip()
        start = self.position
        if self._at_end:
            self._fail("expected a temporal parameter after '_'")

        if self.source[self.position] in "[(":
            self.position += 1
            while not self._at_end and self.source[self.position] not in ")]":
                self.position += 1
            if self._at_end:
                self._fail("unterminated absolute interval", start)
            self.position += 1
        else:
            match = _NUMBER.match(self.source, self.position)
            if match is None:
                self._fail("expected a duration or absolute interval", start)
            self.position = match.end()
            if not self._at_end and self.source[self.position] == "]":
                self.position += 1
            elif not self._at_end and self.source[self.position] == ")":
                consume = self.group_depth == 0 or self._duration_close_has_operand_after()
                if self.group_depth:
                    consume = self.forced_closes.get(self.position, consume)
                    self.duration_choices.append((self.position, consume))
                if consume:
                    self.position += 1

        text = self.source[start:self.position]
        try:
            return coerce_temporal_parameter(text)
        except (TypeError, ValueError) as error:
            self._fail(str(error), start)

    def _duration_close_has_operand_after(self) -> bool:
        position = self.position + 1
        while position < len(self.source) and self.source[position].isspace():
            position += 1
        if position >= len(self.source):
            return False
        remaining = self.source[position:]
        if remaining[0] in ")⟩>,&|∧∨↔→_*":
            return False
        if remaining.startswith(("<->", "->")):
            return False
        operator_words = (
            "and", "or", "equivalent", "implies", "until", "release",
            "U", "R",
        )
        for word in operator_words:
            if remaining.startswith(word):
                end = len(word)
                parameterized = word in {"until", "release", "U", "R"}
                if (
                    end == len(remaining)
                    or not (remaining[end].isalnum() or remaining[end] == "_")
                    or (parameterized and remaining[end] == "_")
                ):
                    return False
        return True

    def _match_equality(self) -> str | None:
        self._skip()
        for token in ("!=", "≠", "="):
            if self.source.startswith(token, self.position):
                self.position += len(token)
                return "!=" if token in {"!=", "≠"} else "="
        return None

    def _match_operator(
        self, unicode: str, ascii: str | None = None, *, keyword: str | None = None
    ) -> bool:
        self._skip()
        for token in (unicode, ascii):
            if token and self.source.startswith(token, self.position):
                self.position += len(token)
                return True
        return bool(
            keyword
            and self._match_keyword(
                keyword, allow_parameter_suffix=keyword in {"always", "eventually"}
            )
        )

    def _match_keyword(
        self, keyword: str, *, allow_parameter_suffix: bool = False
    ) -> bool:
        self._skip()
        end = self.position + len(keyword)
        if self.source[self.position:end] != keyword:
            return False
        if end < len(self.source) and self.source[end].isalnum():
            return False
        if (
            end < len(self.source)
            and self.source[end] == "_"
            and not allow_parameter_suffix
        ):
            return False
        if self.position and (
            self.source[self.position - 1].isalnum() or self.source[self.position - 1] == "_"
        ):
            return False
        self.position = end
        return True

    def _match_symbol(self, symbol: str) -> bool:
        self._skip()
        if not self.source.startswith(symbol, self.position):
            return False
        self.position += len(symbol)
        return True

    def _expect_symbol(self, symbol: str, message: str) -> None:
        if not self._match_symbol(symbol):
            self._fail(message)

    def _skip(self) -> None:
        while not self._at_end and self.source[self.position].isspace():
            self.position += 1

    @property
    def _at_end(self) -> bool:
        return self.position >= len(self.source)

    def _fail(self, message: str, position: int | None = None):
        raise FormulaSyntaxError(
            message, self.source, self.position if position is None else position
        )
