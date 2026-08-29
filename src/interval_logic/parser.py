from __future__ import annotations

from math import isfinite

import portion as P

from .ast import (
    And,
    Atom,
    Bool,
    Equal,
    Eventually,
    Exists,
    Expression,
    ForAll,
    Guard,
    Hold,
    Natural,
    Not,
    Or,
    Restrict,
    Signal,
    Term,
)
from .derived import Equivalent, Implies, Xor
from .errors import ParseError


def parse_expression(source: str) -> Expression:
    """Parse an interval-logic expression in ASCII or Unicode notation.

    The accepted syntax is the syntax emitted by :func:`format_expression`.
    ASCII and Unicode operators may be mixed in the same expression.
    """

    if not isinstance(source, str):
        raise TypeError("source must be a string")
    return _Parser(source).parse()


def parse(source: str) -> Expression:
    """Alias for :func:`parse_expression`."""

    return parse_expression(source)


class _Parser:
    def __init__(self, source: str):
        self.source = source
        self.position = 0

    def parse(self) -> Expression:
        self._skip_whitespace()
        if self._at_end:
            self._fail("expected an expression")

        expression = self._parse_expression()
        self._skip_whitespace()
        if not self._at_end:
            self._fail(f"unexpected token {self._token_description()}")
        return expression

    def _parse_expression(self) -> Expression:
        return self._parse_quantifier()

    def _parse_quantifier(self) -> Expression:
        self._skip_whitespace()
        start = self.position

        if self._match_symbol("∀") or self._match_keyword("forall"):
            operator = ForAll
            name = "universal quantifier"
        elif self._match_symbol("∃") or self._match_keyword("exists"):
            operator = Exists
            name = "existential quantifier"
        else:
            self.position = start
            return self._parse_equivalent()

        self._skip_whitespace()
        interval_start = self.position
        colon = self.source.find(":", interval_start)
        if colon < 0:
            self._fail(f"expected ':' after {name} interval")

        interval = self._parse_interval_text(
            self.source[interval_start:colon], interval_start
        )
        self.position = colon + 1
        self._skip_whitespace()
        if self._at_end:
            self._fail(f"expected an expression after {name}")
        return operator(interval, self._parse_expression())

    def _parse_equivalent(self) -> Expression:
        expression = self._parse_implies()
        while True:
            if not self._match_operator("↔", "<->"):
                return expression
            expression = Equivalent(expression, self._parse_implies())

    def _parse_implies(self) -> Expression:
        left = self._parse_xor()
        if self._match_operator("→", "->"):
            return Implies(left, self._parse_implies())
        return left

    def _parse_xor(self) -> Expression:
        expression = self._parse_or()
        while True:
            if not self._match_operator("⊕", keyword="xor"):
                return expression
            expression = Xor(expression, self._parse_or())

    def _parse_or(self) -> Expression:
        operands = [self._parse_and()]
        while self._match_operator("∨", "|"):
            operands.append(self._parse_and())
        return operands[0] if len(operands) == 1 else Or(operands)

    def _parse_and(self) -> Expression:
        operands = [self._parse_unary()]
        while self._match_operator("∧", "&"):
            operands.append(self._parse_unary())
        return operands[0] if len(operands) == 1 else And(operands)

    def _parse_unary(self) -> Expression:
        if self._match_operator("¬", "!"):
            return Not(self._parse_unary())
        temporal = self._try_parse_temporal()
        if temporal is not None:
            return temporal
        return self._parse_primary()

    def _try_parse_temporal(self) -> Expression | None:
        self._skip_whitespace()
        start = self.position
        if self._match_symbol("H"):
            operator = Hold
            name = "hold"
            notation = "H^"
        elif self._match_symbol("F"):
            operator = Eventually
            name = "eventually"
            notation = "F^"
        else:
            return None
        if not self._match_symbol("^"):
            self.position = start
            return None

        self._skip_whitespace()
        delta_start = self.position
        if not self._at_end and self.source[self.position] in "+-":
            self.position += 1
        integer_digits = self._consume_ascii_digits()
        fractional_digits = False
        if not self._at_end and self.source[self.position] == ".":
            self.position += 1
            fractional_digits = self._consume_ascii_digits()
        if not integer_digits and not fractional_digits:
            self._fail(
                f"expected a non-negative real duration after '{notation}'",
                delta_start,
            )
        if not self._at_end and self.source[self.position] in "eE":
            exponent_start = self.position
            self.position += 1
            if not self._at_end and self.source[self.position] in "+-":
                self.position += 1
            if not self._consume_ascii_digits():
                self._fail(f"invalid exponent in {name} duration", exponent_start)

        text = self.source[delta_start:self.position]
        try:
            delta = float(text)
        except ValueError as error:
            self._fail(f"invalid {name} duration {text!r}", delta_start)
            raise AssertionError("unreachable") from error
        if not isfinite(delta) or delta < 0:
            self._fail(f"invalid {name} duration {text!r}", delta_start)
        return operator(delta, self._parse_unary())

    def _parse_primary(self) -> Expression:
        self._skip_whitespace()
        if self._at_end:
            self._fail("expected an expression")

        window = self._try_parse_window()
        if window is not None:
            return window

        if self._match_symbol("("):
            expression = self._parse_expression()
            self._expect_symbol(")", "expected ')' to close expression")
            return expression

        if self._match_symbol("⊤") or self._match_keyword("true"):
            return Bool(True)
        if self._match_symbol("⊥") or self._match_keyword("false"):
            return Bool(False)

        start = self.position
        if self._is_ascii_digit(self.source[self.position]):
            left = self._parse_natural()
            return self._parse_equality(left, start)

        name = self._parse_name(required=False)
        if name is not None:
            self._skip_whitespace()
            if self._equality_operator() is not None:
                self.position = start
                left = self._parse_term()
                return self._parse_equality(left, start)
            return Atom(name)

        if self.source[self.position] == "[":
            self._fail("expected '_' or '^' after interval")
        self._fail(f"expected an expression, found {self._token_description()}")

    def _parse_equality(self, left: Term, start: int) -> Expression:
        operator = self._equality_operator()
        if operator is None:
            self._fail("a natural number must be part of an equality", start)
        right = self._parse_term()
        equality = Equal(left, right)
        return Not(equality) if operator in ("!=", "≠") else equality

    def _parse_term(self) -> Term:
        self._skip_whitespace()
        if self._at_end:
            self._fail("expected a signal name or natural number")
        if self._is_ascii_digit(self.source[self.position]):
            return self._parse_natural()
        name = self._parse_name(required=False)
        if name is None:
            self._fail("expected a signal name or natural number")
        return Signal(name)

    def _parse_natural(self) -> Natural:
        self._skip_whitespace()
        start = self.position
        while not self._at_end and self._is_ascii_digit(self.source[self.position]):
            self.position += 1
        try:
            return Natural(int(self.source[start:self.position]))
        except ValueError as error:
            self._fail("invalid natural number", start)
            raise AssertionError("unreachable") from error

    def _parse_name(self, *, required: bool) -> str | None:
        self._skip_whitespace()
        if self._at_end:
            if required:
                self._fail("expected a name")
            return None

        if self.source[self.position] == "`":
            return self._parse_quoted_name()

        start = self.position
        first = self.source[self.position]
        if not (first == "_" or first.isidentifier()):
            if required:
                self._fail("expected a name")
            return None

        self.position += 1
        while not self._at_end and (
            self.source[self.position] == "_"
            or ("a" + self.source[self.position]).isidentifier()
        ):
            self.position += 1
        return self.source[start:self.position]

    def _parse_quoted_name(self) -> str:
        start = self.position
        self.position += 1
        characters: list[str] = []
        while not self._at_end:
            character = self.source[self.position]
            self.position += 1
            if character == "`":
                if not characters:
                    self._fail("names must not be empty", start)
                return "".join(characters)
            if character == "\\":
                if self._at_end:
                    self._fail("unterminated escape in quoted name", self.position - 1)
                escaped = self.source[self.position]
                if escaped not in ("`", "\\"):
                    self._fail(
                        "only '`' and '\\' may be escaped in a quoted name",
                        self.position - 1,
                    )
                characters.append(escaped)
                self.position += 1
            else:
                characters.append(character)
        self._fail("unterminated quoted name", start)

    def _try_parse_window(self) -> Expression | None:
        self._skip_whitespace()
        if self._at_end or self.source[self.position] not in "[(":
            return None

        start = self.position
        search = start + 1
        invalid_interval_at: int | None = None
        while search < len(self.source):
            marker = self.source[search]
            if marker not in "_^":
                search += 1
                continue

            body_start = search + 1
            while body_start < len(self.source) and self.source[body_start].isspace():
                body_start += 1
            if body_start >= len(self.source) or self.source[body_start] != "(":
                search += 1
                continue

            interval_text = self.source[start:search].strip()
            try:
                interval = P.from_string(interval_text, float)
            except (TypeError, ValueError):
                invalid_interval_at = start
                search += 1
                continue

            self.position = body_start + 1
            body = self._parse_expression()
            self._expect_symbol(")", "expected ')' to close interval expression")
            operator = Restrict if marker == "_" else Guard
            return operator(interval, body)

        if self.source[start] == "[" and invalid_interval_at is not None:
            self._fail("invalid interval", invalid_interval_at)
        return None

    def _parse_interval_text(self, text: str, start: int) -> P.Interval:
        stripped = text.strip()
        if not stripped:
            self._fail("expected an interval", start)
        try:
            return P.from_string(stripped, float)
        except (TypeError, ValueError) as error:
            self._fail(f"invalid interval {stripped!r}", start)
            raise AssertionError("unreachable") from error

    def _equality_operator(self) -> str | None:
        self._skip_whitespace()
        for operator in ("!=", "≠", "="):
            if self.source.startswith(operator, self.position):
                self.position += len(operator)
                return operator
        return None

    def _match_operator(
        self,
        *symbols: str,
        keyword: str | None = None,
    ) -> bool:
        self._skip_whitespace()
        for symbol in symbols:
            if self.source.startswith(symbol, self.position):
                self.position += len(symbol)
                return True
        return keyword is not None and self._match_keyword(keyword)

    def _match_symbol(self, symbol: str) -> bool:
        self._skip_whitespace()
        if not self.source.startswith(symbol, self.position):
            return False
        self.position += len(symbol)
        return True

    def _expect_symbol(self, symbol: str, message: str) -> None:
        if not self._match_symbol(symbol):
            self._fail(message)

    def _match_keyword(self, keyword: str) -> bool:
        self._skip_whitespace()
        end = self.position + len(keyword)
        if not self.source.startswith(keyword, self.position):
            return False
        if end < len(self.source) and (
            self.source[end] == "_" or ("a" + self.source[end]).isidentifier()
        ):
            return False
        self.position = end
        return True

    def _skip_whitespace(self) -> None:
        while not self._at_end and self.source[self.position].isspace():
            self.position += 1

    @staticmethod
    def _is_ascii_digit(character: str) -> bool:
        return "0" <= character <= "9"

    def _consume_ascii_digits(self) -> bool:
        start = self.position
        while not self._at_end and self._is_ascii_digit(self.source[self.position]):
            self.position += 1
        return self.position > start

    @property
    def _at_end(self) -> bool:
        return self.position >= len(self.source)

    def _token_description(self) -> str:
        if self._at_end:
            return "end of input"
        return repr(self.source[self.position])

    def _fail(self, message: str, position: int | None = None) -> None:
        raise ParseError(
            message,
            self.source,
            self.position if position is None else position,
        )
