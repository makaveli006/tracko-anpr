"""Decide each vehicle's registration number from several readings of its plate.

One reading of one frame is not trusted. The reader is sometimes wrong while sounding sure,
so a number is only **confirmed** when several frames agree on it, it has the shape of an
Indian registration, and the reader was confident. Everything else is reported as
unconfirmed or not detected, never dressed up as a result.

Nothing here needs a model; it is plain logic over text and confidences.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from itertools import product

CONFIRMED = "confirmed"
UNCONFIRMED = "unconfirmed"
NOT_DETECTED = "not_detected"
FAILED = "failed"

# Registration codes of India's states and union territories, including codes still seen on older plates.
STATE_CODES = frozenset(
    {
        "AN", "AP", "AR", "AS", "BR", "CG", "CH", "DD", "DL", "DN", "GA", "GJ", "HP", "HR", "JH", "JK",
        "KA", "KL", "LA", "LD", "MH", "ML", "MN", "MP", "MZ", "NL", "OD", "OR", "PB", "PY", "RJ", "SK",
        "TG", "TN", "TR", "TS", "UA", "UK", "UP", "WB",
    }
)  # fmt: skip

# Characters the reader mixes up. A swap is only ever applied where the plate's shape demands
# the other kind of character, and only if the result is then a valid registration.
DIGIT_FOR_LETTER = {"O": "0", "Q": "0", "D": "0", "I": "1", "L": "1", "Z": "2", "S": "5", "B": "8", "G": "6"}
# In the series letters only one-to-one swaps are safe; a 0 or 1 there could be several letters.
SERIES_LETTER_FOR_DIGIT = {"8": "B", "5": "S", "2": "Z", "6": "G"}
# In the state code every option can be tried, because the result must be a real state code.
STATE_LETTERS_FOR_DIGIT = {"0": "OD", "1": "LI", "8": "B", "5": "S", "2": "Z", "6": "G"}

MAX_CORRECTIONS = 2
# The series letters never include I or O: registration offices skip them because they look like
# 1 and 0. Treating them as invalid there is what lets "KL1OAB1234" be recognised as KL10AB1234.
_SERIES_LETTERS = "A-HJ-NP-Z"
_STANDARD = re.compile(rf"^([A-Z]{{2}})(\d{{1,2}})([{_SERIES_LETTERS}]{{0,3}})(\d{{1,4}})$")
_BHARAT = re.compile(rf"^(\d{{2}})BH(\d{{4}})([{_SERIES_LETTERS}]{{1,2}})$")


def normalize(text: str) -> str:
    """Upper case, with spaces, dashes, dots and anything else that is not a letter or digit removed."""
    return "".join(character for character in text.upper() if character.isascii() and character.isalnum())


def edit_distance(a: str, b: str) -> int:
    """Levenshtein distance: the fewest single-character substitutions, insertions and deletions from `a` to `b`."""
    if a == b:
        return 0
    previous = list(range(len(b) + 1))
    for row, ours in enumerate(a, 1):
        current = [row]
        for column, theirs in enumerate(b, 1):
            current.append(min(previous[column] + 1, current[column - 1] + 1, previous[column - 1] + (ours != theirs)))
        previous = current
    return previous[-1]


def describe_difference(number: str, candidate: str) -> str:
    """Words for a one-edit difference between a recognised number and a record ("3 read where the record has 8")."""
    if len(number) == len(candidate):
        for ours, theirs in zip(number, candidate, strict=True):
            if ours != theirs:
                return f"{ours} read where the record has {theirs}"
        return "identical"
    if len(number) < len(candidate):
        return "one character missing from the reading"
    return "one extra character in the reading"


def plate_kind(text: str) -> str | None:
    """'standard' or 'bharat' when the text has the shape of an Indian registration, else None.

    Standard:  state code, district number, series letters, number  (KL10AB1234, KL05AA470, DL9CBH1669)
    Bharat:    year, BH, number, letters                             (22BH1234AA)
    """
    if _BHARAT.match(text):
        return "bharat"
    match = _STANDARD.match(text)
    if match and match.group(1) in STATE_CODES:
        return "standard"
    return None


def is_valid_plate(text: str) -> bool:
    return plate_kind(text) is not None


def _to_digit(character: str) -> str | None:
    return character if character.isdigit() else DIGIT_FOR_LETTER.get(character)


def _to_series_letter(character: str) -> str | None:
    if character.isalpha():
        return None if character in "IO" else character
    return SERIES_LETTER_FOR_DIGIT.get(character)


def _coerce(text: str, converter) -> tuple[str, int] | None:
    """Convert every character with `converter`; returns the result and how many changed, or None."""
    converted = [converter(character) for character in text]
    if any(character is None for character in converted):
        return None
    return "".join(converted), sum(1 for before, after in zip(text, converted, strict=True) if before != after)


def _state_options(text: str) -> list[tuple[str, int]]:
    """Every real state code the first two characters could stand for, with the number of swaps needed."""
    choices = [
        [character] if character.isalpha() else list(STATE_LETTERS_FOR_DIGIT.get(character, "")) for character in text
    ]
    options = []
    for candidate in product(*choices):
        code = "".join(candidate)
        if code in STATE_CODES:
            options.append((code, sum(1 for before, after in zip(text, code, strict=True) if before != after)))
    return options


def correct(text: str) -> tuple[str, int] | None:
    """Return the text as a valid registration, with look-alike characters fixed where the shape demands.

    Gives (plate, number of characters changed), or None if no valid registration is within
    reach. A text that is already valid comes back unchanged with 0. When two different
    corrections are equally cheap the text is left alone, because guessing would be worse
    than admitting doubt.
    """
    text = normalize(text)
    if is_valid_plate(text):
        return text, 0

    candidates: dict[str, int] = {}

    # Standard shape: 2 state letters, 1-2 district digits, 0-3 series letters, 1-4 number digits.
    for district, series, number in product((1, 2), (0, 1, 2, 3), (1, 2, 3, 4)):
        if 2 + district + series + number != len(text):
            continue
        parts = (
            text[:2],
            text[2 : 2 + district],
            text[2 + district : 2 + district + series],
            text[2 + district + series :],
        )
        middle = [_coerce(parts[1], _to_digit), _coerce(parts[2], _to_series_letter), _coerce(parts[3], _to_digit)]
        if any(part is None for part in middle):
            continue
        for state, state_cost in _state_options(parts[0]):
            plate = state + "".join(part[0] for part in middle)
            cost = state_cost + sum(part[1] for part in middle)
            if 0 < cost <= MAX_CORRECTIONS and plate_kind(plate) == "standard":
                candidates[plate] = min(cost, candidates.get(plate, cost))

    # Bharat shape: 2 year digits, "BH", 4 number digits, 1-2 letters.
    if len(text) in (9, 10):
        year, marker, number, letters = text[:2], text[2:4], text[4:8], text[8:]
        fixed = [_coerce(year, _to_digit), _coerce(marker, _to_series_letter), _coerce(number, _to_digit)]
        tail = _coerce(letters, _to_series_letter)
        if all(part is not None for part in fixed) and tail is not None:
            plate = "".join(part[0] for part in fixed) + tail[0]
            cost = sum(part[1] for part in fixed) + tail[1]
            if 0 < cost <= MAX_CORRECTIONS and plate_kind(plate) == "bharat":
                candidates[plate] = min(cost, candidates.get(plate, cost))

    if not candidates:
        return None
    cheapest = min(candidates.values())
    best = [plate for plate, cost in candidates.items() if cost == cheapest]
    return (best[0], cheapest) if len(best) == 1 else None


@dataclass(frozen=True)
class Observation:
    """One reading of a vehicle's plate in one frame."""

    text: str
    confidence: float
    unreadable: bool = False


@dataclass(frozen=True)
class ValidationRules:
    min_reading_confidence: float = 0.6
    """Readings below this are ignored; the reader scores things that are not plates around 0.2 to 0.5."""
    confirm_confidence: float = 0.85
    """At least one agreeing reading must be this confident for a number to be confirmed."""
    min_observations: int = 2
    """How many frames must give the same number."""
    consensus_share: float = 0.6
    """The winning number's share of all the confidence-weighted votes."""


@dataclass(frozen=True)
class PlateDecision:
    """The outcome for one vehicle."""

    status: str
    text: str = ""
    confidence: float = 0.0
    """Average confidence of the readings that agreed on `text`."""
    support: int = 0
    """How many readings agreed on `text`."""
    readings: int = 0
    """How many readings were good enough to vote."""
    share: float = 0.0
    """`text`'s share of the confidence-weighted votes."""
    reason: str = ""
    """Why this status, in plain words."""

    @property
    def is_confirmed(self) -> bool:
        return self.status == CONFIRMED


def decide(observations: list[Observation], rules: ValidationRules | None = None) -> PlateDecision:
    """Combine a vehicle's plate readings into one decision.

    Each reading votes for its (corrected) text with a weight equal to its confidence.
    A number is confirmed only if it is a valid registration, enough frames agree on it,
    it carries most of the votes, and the reader was confident at least once.
    """
    rules = rules or ValidationRules()
    if not observations:
        return PlateDecision(NOT_DETECTED, reason="no plate was found on this vehicle")

    usable = [
        observation
        for observation in observations
        if not observation.unreadable and observation.text and observation.confidence >= rules.min_reading_confidence
    ]
    if not usable:
        return PlateDecision(UNCONFIRMED, reason="a plate was found but could not be read")

    votes: dict[str, list[float]] = defaultdict(list)
    valid: dict[str, bool] = {}
    for observation in usable:
        corrected = correct(observation.text)
        text = corrected[0] if corrected else normalize(observation.text)
        if not text:
            continue
        votes[text].append(observation.confidence)
        valid[text] = corrected is not None
    if not votes:
        return PlateDecision(UNCONFIRMED, reason="a plate was found but could not be read")

    total = sum(sum(confidences) for confidences in votes.values())
    # A valid registration always beats text that is not one; among equals, the most votes wins.
    winner = max(votes, key=lambda text: (valid[text], sum(votes[text]), len(votes[text]), text))
    confidences = votes[winner]
    decision = {
        "text": winner,
        "confidence": round(sum(confidences) / len(confidences), 4),
        "support": len(confidences),
        "readings": sum(len(group) for group in votes.values()),
        "share": round(sum(confidences) / total, 4),
    }

    if not valid[winner]:
        return PlateDecision(UNCONFIRMED, reason="the text read is not a valid Indian registration", **decision)
    if len(confidences) < rules.min_observations:
        return PlateDecision(UNCONFIRMED, reason="only one frame gave this number", **decision)
    if decision["share"] < rules.consensus_share:
        return PlateDecision(UNCONFIRMED, reason="the frames disagree about the number", **decision)
    if max(confidences) < rules.confirm_confidence:
        return PlateDecision(UNCONFIRMED, reason="the reader was not confident enough", **decision)
    return PlateDecision(CONFIRMED, reason=f"{len(confidences)} frames agree", **decision)
