from __future__ import annotations

from math import isfinite

import portion as P

from .ast import (
    And,
    Proposition,
    Bool,
    Equal,
    Eventually,
    ExistentialCondition,
    Expression,
    Release,
    Selection,
    Until,
    UniversalCondition,
    VacuousSelection,
    NaturalLiteral,
    Not,
    Or,
    RestrictiveSelection,
    Signal,
    Term,
    WeakUntil,
)
from .derived import Equivalent, Implies, Xor
from .errors import ParseError
from .temporal import coerce_temporal_parameter


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
        return self._parse_condition()

    def _parse_condition(self) -> Expression:
        self._skip_whitespace()
        start = self.position

        if self._match_symbol("∀") or self._match_keyword("forall"):
            operator = UniversalCondition
            name = "universal condition"
        elif self._match_symbol("∃") or self._match_keyword("exists"):
            operator = ExistentialCondition
            name = "existential condition"
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
        operands = [self._parse_temporal_infix()]
        while self._match_operator("∧", "&"):
            operands.append(self._parse_temporal_infix())
        return operands[0] if len(operands) == 1 else And(operands)

    def _parse_temporal_infix(self) -> Expression:
        left = self._parse_unary()
        matched = self._match_temporal_infix()
        if matched is None:
            return left
        operator, name = matched
        parameter = self._parse_optional_parameter(name)
        return operator(parameter, left, self._parse_temporal_infix())

    def _parse_unary(self) -> Expression:
        if self._match_operator("¬", "!"):
            return Not(self._parse_unary())
        condition = self._try_parse_canonical_condition()
        if condition is not None:
            return condition
        temporal = self._try_parse_temporal()
        if temporal is not None:
            return temporal
        return self._parse_primary()

    def _try_parse_temporal(self) -> Expression | None:
        self._skip_whitespace()
        start = self.position
        if not self._match_symbol("F"):
            return None

        if not self._at_end and self.source[self.position] == "_":
            parameter = self._parse_optional_parameter("eventually")
            return Eventually(parameter, self._parse_unary())
        if not self._at_end and self.source[self.position].isspace():
            return Eventually(None, self._parse_unary())
        if self._at_end:
            self.position = start
            return None
        if self.source[self.position] != "^":
            self.position = start
            return None
        self.position += 1

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
                "expected a non-negative real duration after 'F^'",
                delta_start,
            )
        if not self._at_end and self.source[self.position] in "eE":
            exponent_start = self.position
            self.position += 1
            if not self._at_end and self.source[self.position] in "+-":
                self.position += 1
            if not self._consume_ascii_digits():
                self._fail("invalid exponent in eventually duration", exponent_start)

        text = self.source[delta_start:self.position]
        try:
            delta = float(text)
        except ValueError as error:
            self._fail(f"invalid eventually duration {text!r}", delta_start)
            raise AssertionError("unreachable") from error
        if not isfinite(delta) or delta < 0:
            self._fail(f"invalid eventually duration {text!r}", delta_start)
        return Eventually(delta, self._parse_unary())

    def _parse_primary(self) -> Expression:
        self._skip_whitespace()
        if self._at_end:
            self._fail("expected an expression")

        selection = self._try_parse_selection()
        if selection is not None:
            return selection

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
            return Proposition(name)

        if self.source[self.position] == "[":
            self._fail("expected '_' or '^' after interval")
        self._fail(f"expected an expression, found {self._token_description()}")

    def _try_parse_canonical_condition(self) -> Expression | None:
        self._skip_whitespace()
        start = self.position
        if self._match_symbol("□") or self._match_temporal_keyword("always"):
            operator = UniversalCondition
            name = "universal condition"
        elif self._match_symbol("◇") or self._match_temporal_keyword("eventually"):
            operator = ExistentialCondition
            name = "existential condition"
        else:
            self.position = start
            return None
        parameter = self._parse_optional_parameter(name)
        return operator(parameter, self._parse_unary())

    def _try_parse_selection(self) -> Expression | None:
        self._skip_whitespace()
        start = self.position
        if self._match_symbol("⟨"):
            closing = "⟩"
        elif self._match_symbol("<"):
            closing = ">"
        else:
            return None

        try:
            inside = self._parse_expression()
            self._skip_whitespace()
            outside = None
            if self._match_symbol(","):
                outside = self._parse_expression()
            self._expect_symbol(closing, "expected a closing selection bracket")
            restrictive = self._match_symbol("*")
            if restrictive and outside is not None:
                self._fail("binary selection cannot use the unary '*' marker")
            parameter = self._parse_optional_parameter("selection")
            if outside is not None:
                return Selection(parameter, inside, outside)
            operator = RestrictiveSelection if restrictive else VacuousSelection
            return operator(parameter, inside)
        except ParseError:
            self.position = start
            raise

    def _match_temporal_infix(self):
        self._skip_whitespace()
        start = self.position
        choices = (
            ("until", Until, "until"),
            ("unless", WeakUntil, "weak until"),
            ("release", Release, "release"),
        )
        for keyword, operator, name in choices:
            if self._match_temporal_keyword(keyword):
                return operator, name
            self.position = start
        for token, operator, name in (
            ("U", Until, "until"),
            ("W", WeakUntil, "weak until"),
            ("R", Release, "release"),
        ):
            if not self.source.startswith(token, self.position):
                continue
            end = self.position + 1
            if end < len(self.source):
                following = self.source[end]
                if following == "_" or following.isspace() or following in "(<⟨!¬□◇`":
                    self.position = end
                    return operator, name
                continue
            self.position = end
            return operator, name
        self.position = start
        return None

    def _parse_optional_parameter(self, operator_name: str):
        self._skip_whitespace()
        if not self._match_symbol("_"):
            return None
        return self._parse_temporal_parameter(operator_name)

    def _parse_temporal_parameter(self, operator_name: str):
        self._skip_whitespace()
        start = self.position
        if self._at_end:
            self._fail(f"expected a temporal parameter after {operator_name}", start)

        if self.source[self.position] in "[(":
            search = self.position + 1
            while search < len(self.source) and self.source[search] not in ")]":
                search += 1
            if search >= len(self.source):
                self._fail("unterminated temporal interval", start)
            self.position = search + 1
            if not self._at_end and self.source[self.position] == "+":
                self.position += 1
            text = self.source[start:self.position]
        else:
            while not self._at_end and self.source[self.position] not in "])":
                character = self.source[self.position]
                if character.isspace():
                    break
                self.position += 1
            if self._at_end or self.source[self.position] not in "])":
                self._fail("expected ']' or ')' after temporal duration", start)
            self.position += 1
            text = self.source[start:self.position]

        try:
            return coerce_temporal_parameter(text)
        except (TypeError, ValueError) as error:
            self._fail(f"invalid temporal parameter {text!r}", start)
            raise AssertionError("unreachable") from error

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

    def _parse_natural(self) -> NaturalLiteral:
        self._skip_whitespace()
        start = self.position
        while not self._at_end and self._is_ascii_digit(self.source[self.position]):
            self.position += 1
        try:
            return NaturalLiteral(int(self.source[start:self.position]))
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
            if len(list(interval)) > 1:
                self._fail("absolute temporal parameter must be connected", start)

            self.position = body_start + 1
            body = self._parse_expression()
            self._expect_symbol(")", "expected ')' to close interval expression")
            operator = RestrictiveSelection if marker == "_" else VacuousSelection
            return operator(interval, body)

        if self.source[start] == "[" and invalid_interval_at is not None:
            self._fail("invalid interval", invalid_interval_at)
        return None

    def _parse_interval_text(self, text: str, start: int) -> P.Interval:
        stripped = text.strip()
        if not stripped:
            self._fail("expected an interval", start)
        try:
            interval = P.from_string(stripped, float)
        except (TypeError, ValueError) as error:
            self._fail(f"invalid interval {stripped!r}", start)
            raise AssertionError("unreachable") from error
        if len(list(interval)) > 1:
            self._fail("absolute temporal parameter must be connected", start)
        return interval

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

    def _match_temporal_keyword(self, keyword: str) -> bool:
        self._skip_whitespace()
        end = self.position + len(keyword)
        if not self.source.startswith(keyword, self.position):
            return False
        if end < len(self.source) and (
            self.source[end] != "_"
            and ("a" + self.source[end]).isidentifier()
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
