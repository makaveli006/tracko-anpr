import pytest

from tracko_anpr.pipeline.validation import (
    CONFIRMED,
    NOT_DETECTED,
    UNCONFIRMED,
    Observation,
    ValidationRules,
    correct,
    decide,
    is_valid_plate,
    normalize,
    plate_kind,
)


def readings(*items) -> list[Observation]:
    return [Observation(text, confidence) for text, confidence in items]


# --- shape of a registration -------------------------------------------------------------------


def test_normalize_keeps_only_letters_and_digits_in_upper_case():
    assert normalize(" kl-10 ab.1234 ") == "KL10AB1234"
    assert normalize("KL 07·CN 9092") == "KL07CN9092"
    assert normalize("") == ""


@pytest.mark.parametrize(
    "plate",
    ["KL10AB1234", "KL07CN9092", "KL57B1883", "KL05AA470", "DL9CBH1669", "HR12AX8522", "TN22DJ7205", "KL11BW2228"],
)
def test_standard_registrations_are_recognised(plate):
    assert plate_kind(plate) == "standard"


@pytest.mark.parametrize("plate", ["22BH1234AA", "21BH0001A"])
def test_bharat_series_registrations_are_recognised(plate):
    assert plate_kind(plate) == "bharat"


@pytest.mark.parametrize(
    "text",
    ["", "KL", "1234", "XX10AB1234", "KL10AB12345", "KLAB1234", "KL10ABCD1234", "UNREADBLE", "22BH123AA", "22BH1234XO"],
)
def test_other_text_is_not_a_registration(text):
    assert not is_valid_plate(text)


# --- look-alike correction ---------------------------------------------------------------------


def test_a_valid_plate_is_left_exactly_as_it_is():
    assert correct("KL10AB1234") == ("KL10AB1234", 0)
    assert correct("kl 10 ab 1234") == ("KL10AB1234", 0)


def test_the_example_in_the_architecture_document_is_corrected():
    # Frame 3 read KL10A81234: an 8 where the series needs a letter.
    assert correct("KL10A81234") == ("KL10AB1234", 1)


@pytest.mark.parametrize(
    ("read", "expected"),
    [
        ("KLO7CN9092", "KL07CN9092"),  # letter O in the district number
        ("KL07CN9O92", "KL07CN9092"),  # letter O in the number
        ("KL1OAB1234", "KL10AB1234"),
        ("KL10AB12S4", "KL10AB1254"),  # S for 5 in the number
        ("K110AB1234", "KL10AB1234"),  # 1 for L in the state code
        ("T522AB1234", "TS22AB1234"),  # 5 for S in the state code
        ("KL10A81234", "KL10AB1234"),
    ],
)
def test_look_alikes_are_fixed_where_the_shape_demands(read, expected):
    plate, changed = correct(read)
    assert plate == expected
    assert changed >= 1


def test_when_two_corrections_are_equally_likely_nothing_is_guessed():
    # "0D" could be OD (Odisha) or DD (Daman and Diu): admit doubt rather than pick one.
    assert correct("0D02AB1234") is None


def test_series_letters_never_include_i_or_o():
    assert not is_valid_plate("KL10AO1234")
    assert not is_valid_plate("KL10IB1234")
    assert correct("KL1OAB1234") == ("KL10AB1234", 1)


def test_correction_gives_up_when_too_much_would_have_to_change():
    assert correct("OLOOABIZEA") is None


@pytest.mark.parametrize("text", ["UNREADBLE", "XX10AB1234", "KA", "", "HELLO"])
def test_text_that_cannot_become_a_plate_is_not_corrected(text):
    assert correct(text) is None


def test_correction_never_invents_a_state_code():
    # ZZ is not a state; nothing within reach makes it one.
    assert correct("ZZ10AB1234") is None


# --- deciding from several frames --------------------------------------------------------------


def test_the_worked_example_from_the_architecture_document():
    decision = decide(readings(("KL10AB1234", 0.95), ("KL10AB1234", 0.94), ("KL10A81234", 0.80), ("KL10AB1234", 0.96)))
    assert decision.status == CONFIRMED
    assert decision.text == "KL10AB1234"
    assert decision.support == 4  # the misread frame is corrected and agrees
    assert decision.readings == 4
    assert decision.share == 1.0


def test_no_plate_found_is_not_detected():
    decision = decide([])
    assert decision.status == NOT_DETECTED
    assert decision.text == ""


def test_a_plate_that_was_found_but_never_read_is_unconfirmed_without_text():
    decision = decide([Observation("", 0.8, unreadable=True), Observation("", 0.7, unreadable=True)])
    assert (decision.status, decision.text) == (UNCONFIRMED, "")
    assert "could not be read" in decision.reason


def test_low_confidence_readings_do_not_vote():
    # The reader writes believable numbers on things that are not plates, at confidence 0.2 to 0.5.
    decision = decide(readings(("KA02CM4231", 0.32), ("MH42AR4447", 0.26)))
    assert (decision.status, decision.text) == (UNCONFIRMED, "")


def test_a_single_good_reading_is_not_enough_to_confirm():
    decision = decide(readings(("KL07CN9092", 0.92)))
    assert decision.status == UNCONFIRMED
    assert decision.text == "KL07CN9092"
    assert "only one frame" in decision.reason


def test_two_agreeing_confident_readings_confirm():
    decision = decide(readings(("KL07CN9092", 0.92), ("KL07CN9092", 0.91)))
    assert decision.status == CONFIRMED
    assert decision.confidence == pytest.approx(0.915)
    assert decision.reason == "2 frames agree"


def test_agreement_without_confidence_is_not_confirmed():
    decision = decide(readings(("KL07CN9092", 0.70), ("KL07CN9092", 0.72)))
    assert decision.status == UNCONFIRMED
    assert "not confident enough" in decision.reason


def test_split_readings_are_unconfirmed():
    decision = decide(readings(("KL07CN9092", 0.90), ("KL07CN9092", 0.90), ("KL07CN9093", 0.90), ("KL07CN9093", 0.89)))
    assert decision.status == UNCONFIRMED
    assert "disagree" in decision.reason
    assert decision.text == "KL07CN9092"


def test_a_minority_misreading_does_not_stop_confirmation():
    # One frame read the Kerala plate as Delhi, as happened in the smoke test.
    decision = decide(readings(("KL11CD7074", 0.92), ("KL11CD7074", 0.91), ("KL11CD7074", 0.90), ("DL11CD7074", 0.86)))
    assert decision.status == CONFIRMED
    assert decision.text == "KL11CD7074"
    assert decision.support == 3
    assert 0.6 < decision.share < 1.0


def test_text_that_is_not_a_registration_is_never_confirmed_however_often_it_repeats():
    decision = decide(readings(("ABC123XYZ9", 0.95), ("ABC123XYZ9", 0.95), ("ABC123XYZ9", 0.95)))
    assert decision.status == UNCONFIRMED
    assert "not a valid Indian registration" in decision.reason


def test_a_valid_registration_beats_more_frequent_invalid_text():
    decision = decide(readings(("KLXX", 0.9), ("KLXX", 0.9), ("KLXX", 0.9), ("KL07CN9092", 0.9), ("KL07CN9092", 0.9)))
    assert decision.text == "KL07CN9092"


def test_rules_can_be_tightened():
    strict = ValidationRules(min_observations=3)
    decision = decide(readings(("KL07CN9092", 0.92), ("KL07CN9092", 0.91)), strict)
    assert decision.status == UNCONFIRMED
