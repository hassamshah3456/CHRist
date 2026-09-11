# -*- coding: utf-8 -*-
"""Checks that any sheet layout still lands in our columns.

Run from the backend/ directory:

    .venv/bin/python -m pytest tests/ -q

The vision model is free to return a differently shaped JSON object for every
sheet it meets — different key names, answers in three languages, an age
column that holds a date of birth. These tests pin down what the app stores
afterwards, which is the part the review screen and the CSV export depend on.
"""
import os
import sys
from datetime import date

import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

from app import omr_normalize as norm  # noqa: E402

REF = date(2026, 9, 11)  # the sheet's own date, in every test below


# ---------------------------------------------------------------- ages ---

@pytest.mark.parametrize("written,years,months", [
    # a date of birth, however it is written
    ("12/03/2019", 7, 5),
    ("12-03-2019", 7, 5),
    ("2019-03-12", 7, 5),
    ("12.3.19", 7, 5),
    ("१२/०३/२०१९", 7, 5),
    ("12 Jan 2020", 6, 7),
    ("5 जून 2021", 5, 3),
    ("31/12/2025", 0, 8),
    # a plain year of birth
    ("2019", 7, 0),
    # years and months, in three languages
    ("5 वर्ष", 5, 0),
    ("5 साल 3 माह", 5, 3),
    ("8 ವರ್ಷ", 8, 0),
    ("3 ತಿಂಗಳು", 0, 3),
    ("5 yrs 3 months", 5, 3),
    ("5y3m", 5, 3),
    ("18 months", 1, 6),
    ("3 माह", 0, 3),
    # halves, decimals and words
    ("2½", 2, 6),
    ("1½ साल", 1, 6),
    ("2.5", 2, 6),
    ("2 1/2 saal", 2, 6),
    ("five years", 5, 0),
    ("पांच साल", 5, 0),
    # days and weeks round down to whole months
    ("45 days", 0, 1),
    ("6 weeks", 0, 1),
    ("10 दिन", 0, 0),
    # bare numbers are years
    ("5", 5, 0),
    ("0", 0, 0),
])
def test_age_forms_land_in_years_and_months(written, years, months):
    parsed = norm.parse_age(written, REF)
    assert (parsed["years"], parsed["months"]) == (years, months)


@pytest.mark.parametrize("written", ["", "   ", "-", "अस्पष्ट", "??"])
def test_unreadable_age_leaves_the_numbers_empty(written):
    parsed = norm.parse_age(written, REF)
    assert parsed["years"] is None and parsed["months"] is None


def test_age_is_counted_against_the_sheet_date_not_today():
    """Two sheets a year apart record the same child as a year older."""
    older = norm.parse_age("01/01/2020", date(2026, 6, 1))
    newer = norm.parse_age("01/01/2020", date(2025, 6, 1))
    assert older["years"] == 6 and newer["years"] == 5


def test_birth_date_after_the_sheet_date_is_rejected():
    parsed = norm.parse_age("12/03/2030", REF)
    assert parsed["years"] is None and parsed["confident"] is False


def test_month_only_birth_date_is_flagged_for_review():
    parsed = norm.parse_age("03/2019", REF)
    assert (parsed["years"], parsed["months"]) == (7, 6)
    assert parsed["confident"] is False


# ------------------------------------------------------------- answers ---

@pytest.mark.parametrize("cell,expected", [
    ("yes", "yes"), ("Yes", "yes"), ("Y", "yes"), ("1", "yes"), (True, "yes"),
    ("हाँ", "yes"), ("हां", "yes"), ("ಹೌದು", "yes"), ("haan", "yes"),
    ("✓", "yes"), ("✔", "yes"), ("yes ✓", "yes"),
    ("no", "no"), ("N", "no"), ("0", "no"), (False, "no"),
    ("नहीं", "no"), ("ಇಲ್ಲ", "no"), ("nahi", "no"), ("✗", "no"), ("×", "no"),
    ("blank", None), ("", None), ("-", None), ("n/a", None), (None, None),
    ("yes/no", None),  # nothing was actually marked
])
def test_answer_vocabulary(cell, expected):
    assert norm.normalize_answer(cell) == expected


# -------------------------------------------------------------- mobile ---

@pytest.mark.parametrize("written,expected", [
    ("9876543210", "9876543210"),
    ("+91 98765 43210", "9876543210"),
    ("09876543210", "9876543210"),
    ("९८७६५४३२१०", "9876543210"),
    ("", None),
])
def test_mobile_numbers_are_stored_as_ten_digits(written, expected):
    assert norm.normalize_mobile(written)[0] == expected


def test_short_mobile_is_kept_but_marked_invalid():
    value, ok = norm.normalize_mobile("98765")
    assert value == "98765" and ok is False


# ------------------------------------------------- whole-sheet mapping ---

def test_standard_sheet_maps_straight_through():
    result = norm.normalize_extraction({
        "language": "hi",
        "header": {"place": "रामपुर", "block": "सदर", "district": "वाराणसी",
                   "date": "11/09/2026"},
        "rows": [
            {"serial": 1, "age_text": "५ वर्ष", "age_years": 5, "age_months": 0,
             "q1": "yes", "q2": "no", "q3": "yes", "q4": "no",
             "mobile": "", "uncertain": False},
        ],
        "footer": {"filler_name": "सीता देवी", "designation": "आशा",
                   "mobile": "9876543210"},
    })
    assert result["header"] == {"place": "रामपुर", "block": "सदर",
                                "district": "वाराणसी", "date": "2026-09-11"}
    assert result["footer"]["filler_name"] == "सीता देवी"
    assert result["footer"]["mobile"] == "9876543210"
    row = result["rows"][0]
    assert (row["age_years"], row["age_months"]) == (5, 0)
    assert [row["q1"], row["q2"], row["q3"], row["q4"]] == ["yes", "no", "yes", "no"]
    assert row["uncertain"] is False


def test_unfamiliar_sheet_shape_still_fills_the_table():
    """Different column names, a DOB column, answers as a list, rows in
    "table" — the shape a model reaches for when the sheet isn't the usual
    one. Nothing about this layout is in our schema, yet all of it lands."""
    result = norm.normalize_extraction({
        "lang": "Kannada",
        "Location Details": {"Village": "Hosahalli", "Taluk": "Hoskote",
                             "Zilla": "Bengaluru Rural", "Date": "11 Sep 2026"},
        "table": [
            {"Sl. No.": "1", "Date of Birth": "12/03/2019",
             "answers": ["ಹೌದು", "ಇಲ್ಲ", "ಹೌದು", "ಇಲ್ಲ"],
             "Contact Number": "+91 98765 43210"},
            {"Sl. No.": "2", "Age": "3 ತಿಂಗಳು",
             "answers": ["no", "no", "no", "no"]},
        ],
        "filled_by": {"Name": "Lakshmi", "Post": "ASHA", "Phone": "9000000000"},
    })
    assert result["language"] == "kn"
    assert result["header"]["place"] == "Hosahalli"
    assert result["header"]["block"] == "Hoskote"
    assert result["header"]["district"] == "Bengaluru Rural"
    assert result["header"]["date"] == "2026-09-11"
    assert result["footer"]["designation"] == "ASHA"

    first, second = result["rows"]
    assert first["serial"] == 1
    assert first["age_text"] == "12/03/2019"      # kept verbatim for review
    assert (first["age_years"], first["age_months"]) == (7, 5)
    assert [first["q1"], first["q2"], first["q3"], first["q4"]] == \
        ["yes", "no", "yes", "no"]
    assert first["mobile"] == "9876543210"
    assert (second["age_years"], second["age_months"]) == (0, 3)
    assert second["q1"] == "no"


def test_dates_of_birth_are_aged_against_the_sheets_own_date():
    result = norm.normalize_extraction({
        "header": {"date": "01/02/2024"},
        "rows": [{"serial": 1, "date_of_birth": "2019-03-12", "q1": "yes"}],
    })
    assert (result["rows"][0]["age_years"], result["rows"][0]["age_months"]) == (4, 10)


def test_a_bare_list_of_rows_is_accepted():
    result = norm.normalize_extraction(
        [{"serial": 1, "age": "4 years", "q1": "yes", "q2": "no"}]
    )
    assert result["rows"][0]["age_years"] == 4
    assert result["rows"][0]["q2"] == "no"


def test_rows_are_numbered_when_the_sheet_is_not():
    result = norm.normalize_extraction({
        "rows": [{"age": "4"}, {"age": "6"}, {"age": "8"}],
    })
    assert [r["serial"] for r in result["rows"]] == [1, 2, 3]


def test_empty_rows_are_dropped():
    result = norm.normalize_extraction({
        "rows": [
            {"serial": 1, "age_text": "5", "q1": "yes"},
            {"serial": 2, "age_text": "", "q1": "blank", "q2": "blank",
             "q3": "blank", "q4": "blank", "mobile": ""},
            {"serial": 3, "age_text": "7", "q1": "no"},
        ],
    })
    assert [r["serial"] for r in result["rows"]] == [1, 3]


def test_a_misconverted_age_is_corrected_and_flagged():
    """The model transcribed "3 माह" but filled in 3 *years*. The written
    cell wins, and the row is raised for review."""
    result = norm.normalize_extraction({
        "rows": [{"serial": 1, "age_text": "3 माह", "age_years": 3,
                  "age_months": 0, "q1": "yes"}],
    })
    row = result["rows"][0]
    assert (row["age_years"], row["age_months"]) == (0, 3)
    assert row["uncertain"] is True


def test_an_unreadable_age_raises_the_row_for_review():
    result = norm.normalize_extraction({
        "rows": [{"serial": 1, "age_text": "स्पष्ट नहीं", "q1": "yes"}],
    })
    assert result["rows"][0]["uncertain"] is True


def test_the_model_flagging_a_row_is_respected():
    result = norm.normalize_extraction({
        "rows": [{"serial": 1, "age_text": "5", "q1": "blank",
                  "uncertain": True}],
    })
    assert result["rows"][0]["uncertain"] is True


def test_a_sheet_with_two_questions_leaves_the_rest_empty():
    result = norm.normalize_extraction({
        "rows": [{"serial": 1, "age_text": "6", "q1": "yes", "q2": "no"}],
    })
    row = result["rows"][0]
    assert row["q3"] is None and row["q4"] is None


def test_a_future_sheet_date_does_not_drive_the_ages():
    """A mis-read year on the header must not make every child older."""
    result = norm.normalize_extraction({
        "header": {"date": "11/09/2099"},
        "rows": [{"serial": 1, "date_of_birth": "2019-03-12", "q1": "yes"}],
    })
    assert result["rows"][0]["age_years"] < 20


def test_an_unfamiliar_name_for_the_table_is_still_found():
    result = norm.normalize_extraction({
        "screening_list": [
            {"sl": 1, "age": "4 years", "q1": "yes"},
            {"sl": 2, "age": "6 years", "q1": "no"},
        ],
    })
    assert [r["serial"] for r in result["rows"]] == [1, 2]
