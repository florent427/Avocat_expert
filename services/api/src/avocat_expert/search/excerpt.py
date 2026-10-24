"""Choix d'un extrait citable, respectueux de la structure des articles.

Un article de code est une suite de lignes hiérarchisées : parties (« I.- »,
« II.- »), alinéas, items numérotés (« 1° »), sous-items (« a) »), tirets.
Une phrase introductive terminée par « : » n'a de sens qu'avec l'énumération
qu'elle annonce, et un item n'a de sens qu'avec sa phrase introductive.

Règles garanties par ce module (et testées) :
* l'extrait est composé de lignes littérales du texte, dans l'ordre ;
* il ne commence jamais par un item d'énumération ;
* il ne se termine jamais par une phrase introductive privée de sa suite ;
* lorsqu'une unité dépasse le budget, la phrase introductive est conservée et
  seuls des items complets sont retenus, les parties omises étant signalées par
  une ligne « […] » (élision reconnue par le moteur de vérification) ;
* chaque segment entre deux élisions compte au moins ``MIN_SEGMENT_CHARS``
  caractères significatifs, seuil de preuve du moteur de vérification.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from avocat_expert.search.query import terms_of

ELISION = "[…]"
#: Budget indicatif d'un extrait ; une ligne isolée plus longue est citée entière.
MAX_EXCERPT_CHARS = 1800
#: Doit rester ≥ au seuil `MIN_SEGMENT_LEN` du moteur lexverif (20).
MIN_SEGMENT_CHARS = 25

ROMAN, PLAIN, DEGREE, LETTER, DASH = 0, 1, 2, 3, 4
_ROMAN = re.compile(r"^[IVXLC]+\s?\.\s?-")
_DEGREE = re.compile(r"^\d+\s?°(?:\s?(?:bis|ter|quater|quinquies|sexies|septies|octies|nonies|decies))?\b")
_LETTER = re.compile(r"^[a-z](?:\s?(?:bis|ter|quater|quinquies))?\s?\)")
_DASH = re.compile(r"^[-–—•]\s")


def line_level(line: str) -> int:
    if _ROMAN.match(line):
        return ROMAN
    if _DEGREE.match(line):
        return DEGREE
    if _LETTER.match(line):
        return LETTER
    if _DASH.match(line):
        return DASH
    return PLAIN


def is_item(line: str) -> bool:
    return line_level(line) in (DEGREE, LETTER, DASH)


def _significant(text: str) -> int:
    return sum(1 for c in text if not c.isspace())


@dataclass
class _Node:
    line: str
    level: float
    score: int = 0
    children: list[_Node] = field(default_factory=list)

    def lines(self) -> list[str]:
        out = [self.line] if self.line else []
        for child in self.children:
            out.extend(child.lines())
        return out

    def text(self) -> str:
        return "\n".join(self.lines())

    def total(self) -> int:
        return self.score + sum(c.total() for c in self.children)


def parse_structure(text: str) -> _Node:
    """Arbre des lignes : chaque ligne est rattachée à la plus proche ligne
    précédente de niveau inférieur. Les alinéas sans marque qui suivent une
    phrase introductive (« … : ») sans énumération marquée lui sont rattachés
    jusqu'à la fin de la phrase (« . »)."""
    root = _Node("", -1.0)
    stack: list[_Node] = [root]
    absorbing: _Node | None = None
    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            continue
        level: float = line_level(line)
        if level == PLAIN and absorbing is not None:
            level = PLAIN + 0.5
        while stack[-1].level >= level:
            stack.pop()
        node = _Node(line, level)
        stack[-1].children.append(node)
        stack.append(node)
        if level == PLAIN + 0.5:
            absorbing = None if line.endswith(".") else absorbing
        elif level in (ROMAN, PLAIN) and line.endswith(":"):
            absorbing = node
        elif level != PLAIN + 0.5:
            absorbing = None
    return root


def _score(node: _Node, prefixes: set[str]) -> None:
    if node.line:
        node.score = sum(1 for t in set(terms_of(node.line)) if t[:5] in prefixes)
    for child in node.children:
        _score(child, prefixes)


def _window(children: list[_Node], budget: int, anchor: int) -> tuple[int, int] | None:
    """Meilleure suite contiguë d'enfants complets contenant l'enfant ``anchor``
    et tenant dans le budget, élargie au besoin pour atteindre la longueur
    minimale d'un segment."""
    best: tuple[int, int, int, int] | None = None  # (score, -longueur, -début, fin)
    for start in range(anchor + 1):
        length = 0
        for end in range(start + 1, len(children) + 1):
            length += len(children[end - 1].text()) + 1
            if length > budget:
                break
            if end <= anchor:
                continue
            segment = "\n".join(c.text() for c in children[start:end])
            if _significant(segment) < MIN_SEGMENT_CHARS:
                continue
            score = sum(c.total() for c in children[start:end])
            candidate = (score, -length, -start, end)
            if best is None or candidate > best:
                best = candidate
    if best is None:
        return None
    return -best[2], best[3]


def _render(node: _Node, budget: int) -> str:
    full = node.text()
    if len(full) <= budget or not node.children:
        return full
    remaining = max(budget - len(node.line) - 2 * (len(ELISION) + 2), 0)
    # L'extrait retenu contient toujours l'enfant le plus pertinent.
    index = max(range(len(node.children)), key=lambda i: (node.children[i].total(), -i))
    span = _window(node.children, remaining, index)
    if span is None:
        # L'enfant le plus pertinent ne tient pas entier : on descend dans sa structure.
        inner = _render(node.children[index], remaining)
        span_text, start, end = inner, index, index + 1
    else:
        start, end = span
        span_text = "\n".join(c.text() for c in node.children[start:end])
    parts = [node.line]
    if start > 0:
        parts.append(ELISION)
    parts.append(span_text)
    if end < len(node.children):
        parts.append(ELISION)
    return "\n".join(parts)


def select_excerpt(text: str, query_terms: tuple[str, ...], budget: int = MAX_EXCERPT_CHARS) -> str:
    """Extrait littéral et structurellement complet le plus pertinent."""
    root = parse_structure(text)
    if not root.children:
        return ""
    _score(root, {t[:5] for t in query_terms})
    units = root.children
    best = max(range(len(units)), key=lambda i: (units[i].total(), -i))
    unit = units[best]
    # Une unité trop courte pour être probante est complétée par l'unité suivante.
    if _significant(unit.text()) < MIN_SEGMENT_CHARS and best + 1 < len(units):
        merged = _Node("", -1.0, children=[unit, units[best + 1]])
        return _render(merged, budget).strip("\n")
    return _render(unit, budget)
