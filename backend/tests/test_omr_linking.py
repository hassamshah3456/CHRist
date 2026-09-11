# -*- coding: utf-8 -*-
"""Joining split sheets: a village list plus one questionnaire per child.

Gwalior uploads put a roster of children on the first page and then a
full-page CRIST questionnaire for each child after it, so a child's age and
that child's answers arrive on different pages. These tests drive the real
database objects through the linking pass and assert the rows a reviewer
would end up looking at.

Run from the backend/ directory:

    .venv/bin/python -m pytest tests/ -q
"""
import os
import sys

import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("SECRET_KEY", "a" * 64)

from app import models, omr_normalize  # noqa: E402
from app.routers import omr_router  # noqa: E402

ROSTER = omr_normalize.KIND_ROSTER
QUESTIONNAIRE = omr_normalize.KIND_QUESTIONNAIRE


class FakeQuery:
    """Just enough of a SQLAlchemy query for the linking pass."""

    def __init__(self, pages):
        self._pages = pages

    def filter(self, *_):
        return self

    def order_by(self, *_):
        return self

    def all(self):
        return self._pages


class FakeSession:
    def __init__(self, pages):
        self._pages = pages

    def query(self, _model):
        return FakeQuery(self._pages)


def _page(number, kind, rows):
    page = models.OmrPage(id="p%d" % number, batch_id="b1",
                          page_number=number, image_filename="x.jpg",
                          status="extracted", kind=kind)
    for row in rows:
        page.rows.append(models.OmrRow(**row))
    return page


def _roster_row(serial, dob, mobile=None):
    return {"serial": serial, "age_text": dob, "age_years": 1,
            "age_months": 0, "mobile": mobile, "uncertain": False}


def _answers(serial=0, dob=None, values=("yes", "no", "yes", "no"),
             uncertain=False):
    return {"serial": serial, "age_text": dob, "q1": values[0],
            "q2": values[1], "q3": values[2], "q4": values[3],
            "uncertain": uncertain}


def _link(pages):
    omr_router._link_batch_pages(FakeSession(pages), "b1")
    return pages


def test_answers_land_on_the_child_named_by_serial_and_birth_date():
    roster = _page(1, ROSTER, [_roster_row(1, "7/3/26"),
                               _roster_row(6, "21/9/24")])
    q = _page(2, QUESTIONNAIRE, [_answers(6, "21/9/24",
                                          ("no", "no", "no", "no"))])
    _link([roster, q])

    first, sixth = roster.rows
    assert [sixth.q1, sixth.q2, sixth.q3, sixth.q4] == ["no"] * 4
    assert first.q1 is None          # this child's page has not arrived
    assert q.rows == []              # absorbed into the roster row


def test_questionnaires_are_matched_out_of_page_order():
    """The pages are not filed in roster order, so position must not decide."""
    roster = _page(1, ROSTER, [_roster_row(1, "7/3/26"),
                               _roster_row(2, "21/4/2026"),
                               _roster_row(6, "21/9/24")])
    pages = [roster,
             _page(2, QUESTIONNAIRE, [_answers(6, "21/9/24", ("yes",) * 4)]),
             _page(3, QUESTIONNAIRE, [_answers(1, "7/3/26", ("no",) * 4)])]
    _link(pages)

    by_serial = {r.serial: r for r in roster.rows}
    assert by_serial[6].q1 == "yes"
    assert by_serial[1].q1 == "no"
    assert by_serial[2].q1 is None


def test_a_birth_date_alone_identifies_the_child():
    roster = _page(1, ROSTER, [_roster_row(1, "7/3/26"),
                               _roster_row(2, "21/4/2026")])
    q = _page(2, QUESTIONNAIRE, [_answers(0, "21/4/2026", ("yes",) * 4)])
    _link([roster, q])
    assert roster.rows[1].q1 == "yes"


def test_the_only_child_gets_the_only_questionnaire():
    """A questionnaire headed with just a name still links when it is the
    last one left, which is how single-child village files read."""
    roster = _page(1, ROSTER, [_roster_row(1, "1½ माह")])
    q = _page(2, QUESTIONNAIRE, [_answers(0, None, ("no",) * 4)])
    _link([roster, q])
    assert roster.rows[0].q1 == "no"
    assert q.rows == []


def test_an_unmatchable_questionnaire_is_kept_and_flagged():
    roster = _page(1, ROSTER, [_roster_row(1, "7/3/26"),
                               _roster_row(2, "21/4/2026")])
    q = _page(2, QUESTIONNAIRE, [_answers(9, "1/1/2001", ("yes",) * 4)])
    _link([roster, q])

    assert len(q.rows) == 1                  # never thrown away
    assert q.rows[0].uncertain is True       # raised for a human
    assert all(r.q1 is None for r in roster.rows)


def test_a_serial_that_contradicts_the_birth_date_loses_to_the_date():
    """One circled digit is easier to misread than a whole date, so an exact
    date match wins. The disagreement is still surfaced."""
    roster = _page(1, ROSTER, [_roster_row(1, "7/3/26"),
                               _roster_row(2, "21/4/2026")])
    q = _page(2, QUESTIONNAIRE, [_answers(2, "7/3/26", ("yes",) * 4)])
    _link([roster, q])

    matched, other = roster.rows
    assert matched.q1 == "yes"        # the child whose birth date agrees
    assert matched.uncertain is True  # flagged, because the serial disagreed
    assert other.q1 is None


def test_a_child_with_no_questionnaire_is_flagged():
    roster = _page(1, ROSTER, [_roster_row(1, "7/3/26"),
                               _roster_row(2, "21/4/2026")])
    q = _page(2, QUESTIONNAIRE, [_answers(1, "7/3/26")])
    _link([roster, q])
    assert roster.rows[0].uncertain is False
    assert roster.rows[1].uncertain is True


def test_an_uncertain_questionnaire_makes_the_childs_row_uncertain():
    roster = _page(1, ROSTER, [_roster_row(1, "7/3/26")])
    q = _page(2, QUESTIONNAIRE, [_answers(1, "7/3/26", uncertain=True)])
    _link([roster, q])
    assert roster.rows[0].uncertain is True


def test_a_classic_register_batch_is_left_alone():
    """Sheets that hold the age and the answers on one line must not be
    touched by any of this."""
    page = _page(1, omr_normalize.KIND_REGISTER, [
        {"serial": 1, "age_text": "5", "age_years": 5, "age_months": 0,
         "q1": "yes", "q2": "no", "q3": "yes", "q4": "no", "uncertain": False},
    ])
    _link([page])
    assert len(page.rows) == 1
    assert page.rows[0].q1 == "yes"
    assert page.rows[0].uncertain is False
