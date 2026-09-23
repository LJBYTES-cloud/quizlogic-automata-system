from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
import re
import unicodedata
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

EPSILON = None
ANY = object()


@dataclass
class NFA:
    start: int
    accepts: Set[int]
    transitions: Dict[int, List[Tuple[object, int]]] = field(default_factory=dict)


@dataclass
class DFA:
    start: int
    accepts: Set[int]
    transitions: Dict[int, Dict[object, int]]

    def accepts_text(self, text: str) -> bool:
        state = self.start
        for ch in text:
            mapping = self.transitions.get(state, {})
            if ch in mapping:
                state = mapping[ch]
            elif ANY in mapping:
                state = mapping[ANY]
            else:
                return False
        return state in self.accepts


def normalize_answer(value: str) -> str:
    """Normalize student input for consistent case/spacing/punctuation."""
    value = unicodedata.normalize("NFKC", value or "").casefold().strip()
    cleaned = []
    for ch in value:
        if ch.isalnum() or ch.isspace():
            cleaned.append(ch)
        else:
            cleaned.append(" ")
    return re.sub(r"\s+", " ", "".join(cleaned)).strip()


class RegexParser:
    """Build a Thompson epsilon-NFA from a small regular-expression syntax.

    Supported: literals, |, concatenation, *, +, ?, (...), ., [abc], [a-z].
    The resulting NFA is determinized into a DFA before matching answers.
    """

    def __init__(self, pattern: str):
        self.pattern = pattern
        self.i = 0
        self.next_state = 0

    def new_state(self) -> int:
        state = self.next_state
        self.next_state += 1
        return state

    def parse(self) -> NFA:
        start, end, transitions = self.parse_expr()
        if self.i != len(self.pattern):
            raise ValueError(f"Unexpected token at position {self.i}")
        return NFA(start, {end}, transitions)

    @staticmethod
    def merge(a, b):
        result = {k: list(v) for k, v in a.items()}
        for k, values in b.items():
            result.setdefault(k, []).extend(values)
        return result

    def epsilon_fragment(self):
        s, e = self.new_state(), self.new_state()
        return s, e, {s: [(EPSILON, e)]}

    def parse_expr(self):
        left = self.parse_term()
        while self.peek() == "|":
            self.i += 1
            right = self.parse_term()
            s, e = self.new_state(), self.new_state()
            trans = self.merge(left[2], right[2])
            trans.setdefault(s, []).extend([(EPSILON, left[0]), (EPSILON, right[0])])
            trans.setdefault(left[1], []).append((EPSILON, e))
            trans.setdefault(right[1], []).append((EPSILON, e))
            left = (s, e, trans)
        return left

    def parse_term(self):
        parts = []
        while self.peek() not in (None, ")", "|"):
            parts.append(self.parse_factor())
        if not parts:
            return self.epsilon_fragment()
        current = parts[0]
        for part in parts[1:]:
            trans = self.merge(current[2], part[2])
            trans.setdefault(current[1], []).append((EPSILON, part[0]))
            current = (current[0], part[1], trans)
        return current

    def parse_factor(self):
        base = self.parse_base()
        token = self.peek()
        if token not in ("*", "+", "?"):
            return base
        self.i += 1
        s, e = self.new_state(), self.new_state()
        trans = {k: list(v) for k, v in base[2].items()}
        if token == "*":
            trans.setdefault(s, []).extend([(EPSILON, e), (EPSILON, base[0])])
            trans.setdefault(base[1], []).extend([(EPSILON, base[0]), (EPSILON, e)])
        elif token == "+":
            trans.setdefault(s, []).append((EPSILON, base[0]))
            trans.setdefault(base[1], []).extend([(EPSILON, base[0]), (EPSILON, e)])
        else:
            trans.setdefault(s, []).extend([(EPSILON, e), (EPSILON, base[0])])
            trans.setdefault(base[1], []).append((EPSILON, e))
        return s, e, trans

    def parse_base(self):
        ch = self.peek()
        if ch is None:
            return self.epsilon_fragment()
        if ch == "(":
            self.i += 1
            result = self.parse_expr()
            if self.peek() != ")":
                raise ValueError("Unclosed group")
            self.i += 1
            return result
        if ch == ".":
            self.i += 1
            return self.literal_fragment(ANY)
        if ch == "[":
            return self.char_class_fragment()
        if ch in "*+?|)":
            raise ValueError(f"Unexpected operator '{ch}'")
        if ch == "\\":
            self.i += 1
            if self.peek() is None:
                raise ValueError("Trailing escape")
            ch = self.pattern[self.i]
        self.i += 1
        return self.literal_fragment(ch)

    def literal_fragment(self, symbol):
        s, e = self.new_state(), self.new_state()
        return s, e, {s: [(symbol, e)]}

    def char_class_fragment(self):
        self.i += 1  # [
        chars: Set[str] = set()
        negated = False
        if self.peek() == "^":
            negated = True
            self.i += 1
        while self.peek() not in (None, "]"):
            if self.peek() == "\\":
                self.i += 1
                if self.peek() is None:
                    raise ValueError("Invalid character class")
                chars.add(self.pattern[self.i])
                self.i += 1
                continue
            start = self.pattern[self.i]
            self.i += 1
            if self.peek() == "-" and self.i + 1 < len(self.pattern) and self.pattern[self.i + 1] != "]":
                self.i += 1
                end = self.pattern[self.i]
                self.i += 1
                if ord(start) > ord(end):
                    raise ValueError("Invalid character range")
                chars.update(chr(c) for c in range(ord(start), ord(end) + 1))
            else:
                chars.add(start)
        if self.peek() != "]":
            raise ValueError("Unclosed character class")
        self.i += 1
        if negated:
            chars = {chr(c) for c in range(32, 127)} - chars
        if not chars:
            raise ValueError("Empty character class")
        s, e = self.new_state(), self.new_state()
        return s, e, {s: [(c, e) for c in chars]}

    def peek(self) -> Optional[str]:
        return self.pattern[self.i] if self.i < len(self.pattern) else None


def epsilon_closure(states: Set[int], transitions) -> FrozenSet[int]:
    closure = set(states)
    stack = list(states)
    while stack:
        state = stack.pop()
        for symbol, target in transitions.get(state, []):
            if symbol is EPSILON and target not in closure:
                closure.add(target)
                stack.append(target)
    return frozenset(closure)


def move(states: FrozenSet[int], symbol: str, transitions) -> Set[int]:
    result = set()
    for state in states:
        for edge, target in transitions.get(state, []):
            if edge is ANY or edge == symbol:
                result.add(target)
    return result


def nfa_to_dfa(nfa: NFA) -> DFA:
    start_set = epsilon_closure({nfa.start}, nfa.transitions)
    state_map: Dict[FrozenSet[int], int] = {start_set: 0}
    queue = [start_set]
    dfa_trans: Dict[int, Dict[object, int]] = {}
    dfa_accepts: Set[int] = set()

    alphabet = set()
    for edges in nfa.transitions.values():
        for symbol, _ in edges:
            if symbol is not EPSILON and symbol is not ANY:
                alphabet.add(symbol)

    while queue:
        current = queue.pop(0)
        current_id = state_map[current]
        if current & nfa.accepts:
            dfa_accepts.add(current_id)

        any_targets_raw = set()
        for state in current:
            for symbol, target in nfa.transitions.get(state, []):
                if symbol is ANY:
                    any_targets_raw.add(target)
        any_targets = epsilon_closure(any_targets_raw, nfa.transitions) if any_targets_raw else frozenset()

        mapping: Dict[object, int] = {}
        for ch in alphabet:
            combined = set(move(current, ch, nfa.transitions)) | set(any_targets)
            targets = epsilon_closure(combined, nfa.transitions)
            if not targets:
                continue
            if targets not in state_map:
                state_map[targets] = len(state_map)
                queue.append(targets)
            mapping[ch] = state_map[targets]

        if any_targets:
            if any_targets not in state_map:
                state_map[any_targets] = len(state_map)
                queue.append(any_targets)
            mapping[ANY] = state_map[any_targets]

        dfa_trans[current_id] = mapping

    return DFA(0, dfa_accepts, dfa_trans)


@lru_cache(maxsize=512)
def compile_pattern(pattern: str) -> DFA:
    return nfa_to_dfa(RegexParser(pattern).parse())


def matches_any(answer: str, patterns: List[str]) -> Optional[str]:
    normalized = normalize_answer(answer)
    for pattern in patterns:
        if compile_pattern(pattern).accepts_text(normalized):
            return pattern
    return None
