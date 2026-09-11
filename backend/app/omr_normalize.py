"""Turn whatever a vision model reads off a screening sheet into our schema.

Sheets arrive in many shapes. The standard CRIST register is one of them, but
field teams also send locally printed variants: columns in a different order,
questions worded differently, a serial column that isn't numbered, and — most
often — an age column that actually holds a date of birth rather than an age.

The model is asked to map whatever it sees onto one fixed JSON shape (see
ai_client._EXTRACTION_PROMPT), but models improvise: they rename keys, answer
"हाँ" where "yes" was asked for, write "2½ साल" into a number field, or hand
back a date of birth with no age at all.

This module is the safety net. It accepts those loose shapes and returns
exactly the fields omr_pages / omr_rows store, so the review screen and the
CSV export never have to know which layout a sheet came from. Everything here
is pure text handling — no database, no network — which is also what makes it
cheap to test.
"""
import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------- digits ---

# Every Indic (and Arabic-Indic) digit block we might meet on a scanned sheet,
# keyed by the codepoint of its zero. Handwritten ages and dates come in the
# script of the sheet; everything downstream expects Western digits.
_DIGIT_ZEROS = (
    0x0966,  # Devanagari  ०१२३४५६७८९
    0x09E6,  # Bengali
    0x0A66,  # Gurmukhi
    0x0AE6,  # Gujarati
    0x0B66,  # Odia
    0x0BE6,  # Tamil
    0x0C66,  # Telugu
    0x0CE6,  # Kannada     ೦೧೨೩೪೫೬೭೮೯
    0x0D66,  # Malayalam
    0x0660,  # Arabic-Indic
    0x06F0,  # Extended Arabic-Indic (Persian/Urdu)
)
_DIGIT_MAP = {}
for _zero in _DIGIT_ZEROS:
    for _d in range(10):
        _DIGIT_MAP[_zero + _d] = str(_d)

# "2½" is an extremely common way to write two-and-a-half years.
_FRACTION_GLYPHS = {
    "½": ".5",    # ½
    "¼": ".25",   # ¼
    "¾": ".75",   # ¾
    "⅓": ".33",   # ⅓
    "⅔": ".67",   # ⅔
    "⅛": ".125",  # ⅛
}


def to_western_digits(text: Any) -> str:
    """Devanagari/Kannada/… digits and vulgar fractions -> ASCII."""
    if text is None:
        return ""
    out = str(text).translate(_DIGIT_MAP)
    for glyph, value in _FRACTION_GLYPHS.items():
        out = out.replace(glyph, value)
    # "2 ½" became "2 .5"; join it back onto its whole number.
    return re.sub(r"(\d)\s+\.(\d)", r"\1.\2", out)


def _clean(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _to_int(value: Any) -> Optional[int]:
    """First integer in a value, tolerating "1.", "०८", "Sl 3", 4.0, None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    m = re.search(r"-?\d+", to_western_digits(value))
    return int(m.group()) if m else None


# --------------------------------------------------------------- answers ---

# A yes/no cell can arrive as a word in three languages, a romanised spelling,
# a tick glyph, a 1/0 flag or a bare letter. Collected here so the AI path and
# the admin-edit path accept exactly the same vocabulary.
_YES_TOKENS = {
    "yes", "y", "ye", "yeah", "yep", "true", "t", "1", "positive", "pos", "p",
    "present", "affirmative", "checked", "ticked", "tick", "check", "marked",
    "right", "correct", "ok",
    "✓", "✔", "☑", "√",                   # ✓ ✔ ☑ √
    "हाँ", "हां", "हा",  # हाँ हां हा
    "जी", "हाँजी",            # जी, हाँजी
    "haan", "han", "ha", "hai", "ji",
    "ಹௌದು", "ಹೌದು",      # ಹೌದು
    "ಇದೆ", "ಹೌದು.",
    "howdu", "houdu", "haudu", "ide",
}
_NO_TOKENS = {
    "no", "n", "nope", "false", "f", "0", "negative", "neg", "absent",
    "unchecked", "wrong", "nil",
    "✗", "✘", "☒", "×", "x",                 # ✗ ✘ ☒ × x
    "नहीं", "नही",            # नहीं नही
    "ना", "नहि",                        # ना नहि
    "nahi", "nahin", "nahee", "na", "nai",
    "ಇಲ್ಲ", "ಇಲ್ಲ.",     # ಇಲ್ಲ
    "illa", "ila",
}
# Explicitly "nothing was marked" — distinct from a "no" answer.
_BLANK_TOKENS = {
    "blank", "empty", "none", "null", "nan", "unknown", "unclear", "-", "--",
    "?", "n/a", "na/", "not marked", "nm",
}


def normalize_answer(value: Any) -> Optional[str]:
    """Any spelling of a yes/no cell -> "yes" | "no" | None (blank)."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float)):
        return {1: "yes", 0: "no"}.get(int(value))

    token = to_western_digits(value).strip().lower()
    token = token.strip(" \t.,;:()[]{}<>\"'")
    if not token or token in _BLANK_TOKENS:
        return None
    if token in _YES_TOKENS:
        return "yes"
    if token in _NO_TOKENS:
        return "no"

    # Mixed cells such as "yes (हाँ)" or "no - nahi": decide on whole words,
    # never substrings ("no" lives inside "none").
    words = {w.strip(" .,;:()[]") for w in re.split(r"[\s/|,;]+", token) if w}
    yes = bool(words & _YES_TOKENS)
    no = bool(words & _NO_TOKENS)
    if yes and not no:
        return "yes"
    if no and not yes:
        return "no"
    return None


# ----------------------------------------------------------------- dates ---

_MONTH_NAMES = {}
for _idx, _names in enumerate([
    ("jan", "january", "जनवरी", "ಜನವರಿ"),
    ("feb", "february", "फरवरी", "ಫೆಬ್ರವರಿ"),
    ("mar", "march", "मार्च", "ಮಾರ್ಚ್"),
    ("apr", "april", "अप्रैल", "ಏಪ್ರಿಲ್"),
    ("may", "मई", "मईं", "ಮೇ"),
    ("jun", "june", "जून", "ಜೂನ್"),
    ("jul", "july", "जुलाई", "ಜುಲೈ"),
    ("aug", "august", "अगस्त", "ಆಗಸ್ಟ್"),
    ("sep", "sept", "september", "सितंबर",
     "सितम्बर", "ಸೆಪ್ಟೆಂಬರ್"),
    ("oct", "october", "अक्टूबर",
     "अक्तूबर", "ಅಕ್ಟೋಬರ್"),
    ("nov", "november", "नवंबर",
     "नवम्बर", "ನವೆಂಬರ್"),
    ("dec", "december", "दिसंबर",
     "दिसम्बर", "ಡಿಸೆಂಬರ್"),
]):
    for _name in _names:
        _MONTH_NAMES[_name] = _idx + 1

_SEP = r"[-/.\s]"
# "Letter" has to include Devanagari and Kannada vowel signs, which are marks
# rather than letters — \w would split जून into ज + न and never match a month.
_WORD = r"(?:[^\d\s./\\,;:()\[\]|-]){2,15}"
_RE_ISO = re.compile(r"(?<!\d)(\d{4})" + _SEP + r"(\d{1,2})" + _SEP + r"(\d{1,2})(?!\d)")
_RE_DMY = re.compile(r"(?<!\d)(\d{1,2})" + _SEP + r"(\d{1,2})" + _SEP + r"(\d{2,4})(?!\d)")
_RE_DAY_MONTH_NAME = re.compile(
    r"(?<!\d)(\d{1,2})\s*[-/.\s]?\s*(" + _WORD + r")\.?\s*[-/,.\s]\s*(\d{2,4})(?!\d)")
_RE_MONTH_NAME_DAY = re.compile(
    r"(" + _WORD + r")\.?\s*[-/.\s]\s*(\d{1,2})\s*[-/,.\s]\s*(\d{2,4})(?!\d)")
_RE_MONTH_YEAR = re.compile(r"(?<!\d)(\d{1,2})" + _SEP + r"(\d{4})(?!\d)")
_RE_WORDS = re.compile(_WORD)


def _month_from_name(word: str) -> Optional[int]:
    word = (word or "").strip().lower()
    if word in _MONTH_NAMES:
        return _MONTH_NAMES[word]
    # "septembar", "ಮಾರ್ಚ್‌" and other spellings: match on the stem.
    for name, num in _MONTH_NAMES.items():
        if len(name) >= 3 and (word.startswith(name) or name.startswith(word[:4])):
            return num
    return None


def _full_year(year: int, reference: date) -> int:
    """Expand a 2-digit year, never into the future ("19" -> 2019, "78" -> 1978)."""
    if year >= 100:
        return year
    candidate = 2000 + year
    return candidate if candidate <= reference.year else 1900 + year


def _build(year: int, month: int, day: int) -> Optional[date]:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_date_detailed(text: Any, reference: Optional[date] = None,
                        day_first: bool = True):
    """(date, exact) — `exact` is False when part of it had to be assumed."""
    ref = reference or date.today()
    raw = _clean(to_western_digits(text))
    if not raw:
        return None, True

    m = _RE_ISO.search(raw)
    if m:
        return _build(int(m.group(1)), int(m.group(2)), int(m.group(3))), True

    m = _RE_DAY_MONTH_NAME.search(raw)
    if m:
        month = _month_from_name(m.group(2))
        if month:
            return _build(_full_year(int(m.group(3)), ref), month,
                          int(m.group(1))), True

    m = _RE_MONTH_NAME_DAY.search(raw)
    if m:
        month = _month_from_name(m.group(1))
        if month:
            return _build(_full_year(int(m.group(3)), ref), month,
                          int(m.group(2))), True

    m = _RE_DMY.search(raw)
    if m:
        first, second = int(m.group(1)), int(m.group(2))
        year = _full_year(int(m.group(3)), ref)
        if first > 12 >= second:
            day, month = first, second
        elif second > 12 >= first:
            day, month = second, first
        else:
            day, month = (first, second) if day_first else (second, first)
        return _build(year, month, day), True

    # "03/2019" — month and year only, so the day has to be assumed.
    m = _RE_MONTH_YEAR.search(raw)
    if m and 1 <= int(m.group(1)) <= 12:
        return _build(int(m.group(2)), int(m.group(1)), 1), False
    return None, True


def parse_date(text: Any, reference: Optional[date] = None,
               day_first: bool = True) -> Optional[date]:
    """Best-effort date out of a handwritten cell; None if it isn't one.

    Sheets are filled in India, so an ambiguous 03/04/2019 is read day-first.
    A value that can only be one way round (13/04) is read that way regardless.
    """
    return parse_date_detailed(text, reference, day_first)[0]


def normalize_date_text(text: Any, reference: Optional[date] = None) -> str:
    """Header/sheet date as ISO (YYYY-MM-DD) when readable, else as written."""
    written = _clean(to_western_digits(text))
    if not written:
        return ""
    parsed = parse_date(written, reference)
    return parsed.isoformat() if parsed else written


# ------------------------------------------------------------------- age ---

# Unit words for a written age, in English, romanised Hindi, Devanagari and
# Kannada. Matched as prefixes (longest first) so "months", "महीने" and
# "ತಿಂಗಳುಗಳು" all land on the same unit.
_UNIT_WORDS = {
    "y": ("y", "yr", "yrs", "year", "years", "yo", "yrold", "varsh", "varsha",
          "saal", "sal", "वर्ष", "साल",
          "बरस", "ವರ್ಷ"),
    "m": ("m", "mo", "mos", "mon", "mth", "mnth", "month", "months", "maah",
          "mah", "mahina", "mahine", "tingal",
          "माह", "महीन", "महिन",
          "मास", "ಮಾಹೆ", "ತಿಂಗ"),
    "w": ("w", "wk", "wks", "week", "weeks", "hafta", "hafte", "saptah",
          "सप्ताह", "हफ्त",
          "ವಾರ"),
    "d": ("d", "day", "days", "din", "dino", "दिन", "ದಿನ"),
}
# Longest prefix wins, so "mon" is a month and not a mis-read "m" + "on".
_UNIT_PREFIXES = sorted(
    ((word, unit) for unit, words in _UNIT_WORDS.items() for word in words),
    key=lambda pair: len(pair[0]), reverse=True,
)

# Spelled-out numbers, as a backstop for when the model transcribes the word
# instead of the digit.
_NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
    "ek": 1, "do": 2, "teen": 3, "char": 4, "panch": 5, "chah": 6, "chhah": 6,
    "saat": 7, "aath": 8, "nau": 9, "das": 10,
    "एक": 1, "दो": 2, "तीन": 3,
    "चार": 4, "पांच": 5,
    "पाँच": 5, "छह": 6, "सात": 7,
    "आठ": 8, "नौ": 9, "दस": 10,
    "ಒಂದು": 1, "ಎರಡು": 2,
    "ಮೂರು": 3, "ನಾಲ್ಕು": 4,
    "ಐದು": 5, "ಆರು": 6, "ಏಳು": 7,
    "ಎಂಟು": 8, "ಹತ್ತು": 10,
}

_DAYS_PER_MONTH = 30.44
_MAX_AGE_YEARS = 120
_RE_DIGIT_SEP_DIGIT = re.compile(r"\d\s*[-/.]\s*\d")


def _looks_like_a_date(text: str) -> bool:
    """A bare "5" is an age; "5/6/19" or "5 जून 2021" is a date of birth."""
    if _RE_DIGIT_SEP_DIGIT.search(text):
        return True
    if not re.search(r"\d", text):
        return False
    return any(_month_from_name(word) for word in _RE_WORDS.findall(text))


def _classify_unit(token: str) -> str:
    token = (token or "").strip(" .,;:()[]{}-_/‌‍").lower()
    if not token:
        return ""
    for prefix, unit in _UNIT_PREFIXES:
        if token.startswith(prefix):
            return unit
    return "?"


def _spell_out_numbers(text: str) -> str:
    for word, value in _NUMBER_WORDS.items():
        text = re.sub(r"(?<!\w)" + re.escape(word) + r"(?!\w)", str(value), text)
    return text


def age_from_birth_date(dob: date, reference: date):
    """(years, months) completed at `reference`, or None if dob is impossible."""
    total = (reference.year - dob.year) * 12 + (reference.month - dob.month)
    if reference.day < dob.day:
        total -= 1
    if total < 0 or total > _MAX_AGE_YEARS * 12:
        return None
    return divmod(total, 12)


def parse_age(age_text: Any, reference: Optional[date] = None,
              dob_text: Any = None) -> Dict[str, Any]:
    """Read an age cell in any of the forms a sheet uses.

    Handles a date of birth (any separator, any of three scripts, 2- or
    4-digit year), a plain year of birth, "5 वर्ष 3 माह", "2½", "18 months",
    "45 days", "five years" and a bare number. Returns the age as our two
    columns plus how it was read, so the caller can flag what it couldn't.
    """
    ref = reference or date.today()
    out = {"years": None, "months": None, "dob": None, "source": "empty",
           "confident": True}

    written = _clean(to_western_digits(age_text))
    hinted = _clean(to_western_digits(dob_text))
    if not written and not hinted:
        return out

    # 1. An explicit date of birth, from the model's own field or from a
    #    date-shaped age cell. We do the arithmetic; models are bad at it.
    for candidate in (hinted, written if _looks_like_a_date(written) else ""):
        if not candidate:
            continue
        dob, exact = parse_date_detailed(candidate, ref)
        if dob is None:
            continue
        pair = age_from_birth_date(dob, ref)
        if pair is None:
            out["source"] = "unparsed"
            out["confident"] = False
            return out
        out["years"], out["months"] = pair
        out["dob"] = dob
        out["source"] = "date"
        out["confident"] = exact
        return out

    if not written:
        out["source"] = "unparsed"
        out["confident"] = False
        return out

    # 2. A duration: any mix of years / months / weeks / days, in any script.
    body = _spell_out_numbers(written.lower())
    body = re.sub(r"(?<![\d/])1\s*/\s*2(?![\d/])", ".5", body)  # "2 1/2 saal"
    body = re.sub(r"(\d)\s+\.(\d)", r"\1.\2", body)
    pairs = re.findall(r"(\d+(?:\.\d+)?)\s*([^\d\s]*)", body)
    if not pairs:
        out["source"] = "unparsed"
        out["confident"] = False
        return out

    totals = {"y": 0.0, "m": 0.0, "w": 0.0, "d": 0.0, "": 0.0}
    unknown_unit = False
    for value, unit_token in pairs:
        unit = _classify_unit(unit_token)
        if unit == "?":
            unknown_unit = True
            unit = ""
        totals[unit] += float(value)

    bare = totals.pop("")
    if any(totals.values()):
        # A trailing bare number after a year ("5 साल 3") is the month part;
        # anything else unaccounted for means we guessed.
        if bare:
            if totals["y"] and not totals["m"] and bare <= 11:
                totals["m"] += bare
            else:
                out["confident"] = False
        out["source"] = "duration"
    else:
        if len(pairs) > 1:
            out["confident"] = False
        # A lone 4-digit number in an age column is a year of birth.
        if bare == int(bare) and 1900 <= bare <= ref.year:
            out["years"] = ref.year - int(bare)
            out["months"] = 0
            out["source"] = "birth_year"
            out["confident"] = False
            return out
        totals["y"] = bare
        out["source"] = "number"
    if unknown_unit:
        out["confident"] = False

    months_total = (
        totals["y"] * 12 + totals["m"]
        + (totals["w"] * 7 + totals["d"]) / _DAYS_PER_MONTH
    )
    months_total = int(round(months_total))
    if months_total < 0 or months_total > _MAX_AGE_YEARS * 12:
        return {"years": None, "months": None, "dob": None,
                "source": "unparsed", "confident": False}
    out["years"], out["months"] = divmod(months_total, 12)
    return out


# ---------------------------------------------------------------- mobile ---

def normalize_mobile(value: Any):
    """(digits, looks_valid). Strips +91 / leading 0 off Indian numbers."""
    digits = re.sub(r"\D", "", to_western_digits(value))
    if not digits:
        return None, True
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return digits[:32], len(digits) == 10


# ------------------------------------------------- shape-tolerant mapping ---

def _key(name: Any) -> str:
    """Fold a JSON key so "Age (years)", "age_years" and "AgeYears" match."""
    folded = re.sub(r"[^a-z0-9]", "", str(name).lower())
    return folded or str(name).strip().lower()


def _index(obj: Any) -> Dict[str, Any]:
    if not isinstance(obj, dict):
        return {}
    return {_key(k): v for k, v in obj.items()}


def _pick(idx: Dict[str, Any], *names: str) -> Any:
    """First non-empty value among these key spellings.

    Containers are skipped: "filled_by" folds to the same key as the
    "filledBy" name field, and a whole footer block is not a person's name.
    """
    for name in names:
        value = idx.get(name)
        if value in (None, "") or isinstance(value, (dict, list)):
            continue
        return value
    return None


def _pick_container(idx: Dict[str, Any], *names: str) -> Any:
    """Like _pick, but for a key that is meant to hold a list or an object."""
    for name in names:
        value = idx.get(name)
        if isinstance(value, (dict, list)) and value:
            return value
    return None


_ROWS_KEYS = ("rows", "table", "tablerows", "entries", "records", "data",
              "children", "participants", "items", "lines", "sheetrows",
              "results")
_HEADER_KEYS = ("header", "location", "locationdetails", "locationdetail",
                "sheetheader", "heading", "top", "meta", "metadata",
                "placedetails", "sthanvivaran")
_FOOTER_KEYS = ("footer", "filledby", "filler", "surveyor", "submittedby",
                "bottom", "signature", "fillerdetails")

_PLACE_KEYS = ("place", "placename", "village", "villagename", "gram",
               "mohalla", "locality", "ward", "town", "hamlet", "sthan")
_BLOCK_KEYS = ("block", "blockarea", "blockname", "taluk", "taluka", "tehsil",
               "mandal", "subdistrict", "area", "circle", "sector")
_DISTRICT_KEYS = ("district", "districtname", "dist", "zilla", "zila", "jila")
_DATE_KEYS = ("date", "sheetdate", "surveydate", "dateofsurvey", "filleddate",
              "dateofvisit", "visitdate", "dt", "dinank")

_NAME_KEYS = ("fillername", "name", "filledby", "filledbyname", "surveyorname",
              "workername", "personname", "bharankarta", "fullname")
_DESIGNATION_KEYS = ("designation", "post", "pad", "role", "title", "position",
                     "jobtitle")
_MOBILE_KEYS = ("mobile", "mobileno", "mobilenumber", "phone", "phoneno",
                "phonenumber", "contact", "contactno", "contactnumber", "mob",
                "cell", "cellnumber", "whatsapp")

_SERIAL_KEYS = ("serial", "serialno", "serialnumber", "sl", "slno", "sno",
                "sn", "srno", "sr", "no", "number", "num", "row", "rowno",
                "rownumber", "index", "idx", "item", "krsn", "crsn")
_AGE_TEXT_KEYS = ("agetext", "age", "ageaswritten", "agewritten", "agevalue",
                  "agestr", "agestring", "ageraw", "umar", "umr", "vay", "ayu")
_AGE_YEARS_KEYS = ("ageyears", "years", "year", "ageyear", "yrs", "yr",
                   "ageinyears", "agey")
_AGE_MONTHS_KEYS = ("agemonths", "months", "month", "agemonth", "mos", "mo",
                    "ageinmonths", "agem")
_DOB_KEYS = ("dateofbirth", "dob", "birthdate", "birthday", "dateofbirthiso",
             "birth", "dobiso", "janmatithi")
_UNCERTAIN_KEYS = ("uncertain", "unsure", "lowconfidence", "needsreview",
                   "doubtful", "ambiguous", "unclear")
_CONFIDENCE_KEYS = ("confidence", "conf", "certainty", "score")

_LANGUAGE_ALIASES = {
    "hindi": "hi", "hin": "hi", "devanagari": "hi",
    "kannada": "kn", "kan": "kn",
    "english": "en", "eng": "en",
}


def _flag(value: Any) -> bool:
    """A truthiness flag that survives "false", "no" and 0 arriving as text."""
    if isinstance(value, str):
        return value.strip().lower() in ("true", "yes", "y", "1")
    return bool(value)


def _row_answers(row_idx: Dict[str, Any]) -> List[Optional[str]]:
    """The four screening answers, however the model chose to name them."""
    answers = []
    for i in (1, 2, 3, 4):
        answers.append(normalize_answer(_pick(
            row_idx,
            "q%d" % i, "question%d" % i, "q%dans" % i, "a%d" % i, "ans%d" % i,
            "answer%d" % i, "response%d" % i, "col%d" % i,
        )))
    if any(a is not None for a in answers):
        return answers

    # List / dict-of-labels form: take the first four in the order given.
    seq = _pick_container(row_idx, "answers", "questions", "responses", "q",
                          "marks", "values", "screening")
    if isinstance(seq, dict):
        seq = list(seq.values())
    if isinstance(seq, list):
        values = []
        for cell in seq[:4]:
            if isinstance(cell, dict):
                cell = _pick(_index(cell), "answer", "value", "response",
                             "marked", "result", "reply")
            values.append(normalize_answer(cell))
        return (values + [None] * 4)[:4]
    return [None] * 4


def _row_from_list(cells: List[Any]) -> Dict[str, Any]:
    """Positional fallback: [serial, age, q1..q4, mobile]."""
    padded = list(cells) + [None] * 7
    return {
        "serial": padded[0], "age_text": padded[1],
        "q1": padded[2], "q2": padded[3], "q3": padded[4], "q4": padded[5],
        "mobile": padded[6], "uncertain": True,
    }


def normalize_row(raw: Any, position: int,
                  reference: Optional[date] = None) -> Optional[Dict[str, Any]]:
    """One model row -> one omr_rows record. None if the row is empty."""
    if isinstance(raw, list):
        raw = _row_from_list(raw)
    if not isinstance(raw, dict):
        return None
    idx = _index(raw)

    answers = _row_answers(idx)
    dob_value = _pick(idx, *_DOB_KEYS)
    age_written = _clean(to_western_digits(_pick(idx, *_AGE_TEXT_KEYS)))
    if not age_written and dob_value:
        age_written = _clean(to_western_digits(dob_value))
    mobile, mobile_ok = normalize_mobile(_pick(idx, *_MOBILE_KEYS))

    model_years = _to_int(_pick(idx, *_AGE_YEARS_KEYS))
    model_months = _to_int(_pick(idx, *_AGE_MONTHS_KEYS))

    if not age_written and model_years is None and model_months is None \
            and not mobile and not any(answers):
        return None  # nothing was written on this line

    parsed = parse_age(age_written, reference, dob_value)
    years, months = parsed["years"], parsed["months"]
    uncertain = _flag(_pick(idx, *_UNCERTAIN_KEYS))

    confidence = _pick(idx, *_CONFIDENCE_KEYS)
    if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
        uncertain = uncertain or float(confidence) < 0.75
    elif isinstance(confidence, str) and confidence.strip().lower() in ("low", "poor"):
        uncertain = True

    if years is None and months is None:
        # Nothing we could read; fall back to whatever the model computed.
        years, months = model_years, model_months
        if age_written:
            uncertain = True
    elif not parsed["confident"]:
        uncertain = True
    elif model_years is not None or model_months is not None:
        # Both readings exist: keep ours (the conversion is deterministic) but
        # flag the row when the model read the age materially differently.
        ours = (years or 0) * 12 + (months or 0)
        theirs = (model_years or 0) * 12 + (model_months or 0)
        if abs(ours - theirs) > 2:
            uncertain = True

    if months is not None and months >= 12:
        years = (years or 0) + months // 12
        months = months % 12
    if years is not None and not 0 <= years <= _MAX_AGE_YEARS:
        years, months, uncertain = None, None, True
    if mobile and not mobile_ok:
        uncertain = True

    # Sheet serials are small. A huge one means we picked up something else
    # under a generic key like "number", so fall back to the row's position.
    serial = _to_int(_pick(idx, *_SERIAL_KEYS))
    if serial is None or not 0 <= serial <= 999:
        serial = position

    return {
        "serial": serial,
        "age_text": age_written[:64] or None,
        "age_years": years,
        "age_months": months,
        "q1": answers[0], "q2": answers[1], "q3": answers[2], "q4": answers[3],
        "mobile": mobile,
        "uncertain": bool(uncertain),
    }


def _section(idx: Dict[str, Any], container_keys) -> Dict[str, Any]:
    """Header/footer values, whether nested in a container or left flat.

    A nested block wins over a same-named key at the top level, because that
    is the shape we asked for.
    """
    merged = dict(idx)
    for key in container_keys:
        nested = idx.get(key)
        if isinstance(nested, dict):
            merged.update({k: v for k, v in _index(nested).items()
                           if v not in (None, "")})
    return merged


def normalize_extraction(data: Any, reference: Optional[date] = None) -> Dict[str, Any]:
    """Whatever the model returned -> the exact shape omr_pages/omr_rows store.

    `reference` is the date the ages are counted against when a sheet records
    dates of birth; the sheet's own date is used when it has one.
    """
    if isinstance(data, list):
        data = {"rows": data}
    if not isinstance(data, dict):
        raise ValueError("Extraction result was not a JSON object.")
    idx = _index(data)

    header = _section(idx, _HEADER_KEYS)
    footer = _section(idx, _FOOTER_KEYS)

    language = _clean(_pick(idx, "language", "lang", "detectedlanguage",
                            "sheetlanguage")).lower()
    language = _LANGUAGE_ALIASES.get(language, language)
    if not re.match(r"^[a-z]{2,3}(-[a-z]{2,4})?$", language):
        language = ""  # a sentence, not a language code

    sheet_date_raw = _pick(header, *_DATE_KEYS)
    sheet_date = normalize_date_text(sheet_date_raw)
    parsed_sheet_date = parse_date(sheet_date_raw)
    today = datetime.utcnow().date()
    if parsed_sheet_date and parsed_sheet_date > today:
        parsed_sheet_date = None  # a mis-read year, not a future survey
    ref = reference or parsed_sheet_date or today

    rows_raw = None
    for key in _ROWS_KEYS:
        value = idx.get(key)
        if isinstance(value, list):
            rows_raw = value
            break
    if rows_raw is None:
        # An unfamiliar name for the table: take the longest list of row-like
        # objects in the reply rather than losing the sheet over a key name.
        candidates = [v for v in data.values() if isinstance(v, list)
                      and any(isinstance(cell, (dict, list)) for cell in v)]
        if candidates:
            rows_raw = max(candidates, key=len)
    rows = []
    for position, raw in enumerate(rows_raw or [], start=1):
        row = normalize_row(raw, position, ref)
        if row is not None:
            rows.append(row)

    footer_mobile = normalize_mobile(_pick(footer, *_MOBILE_KEYS))[0]
    return {
        "language": language or None,
        "header": {
            "place": _clean(_pick(header, *_PLACE_KEYS))[:255] or None,
            "block": _clean(_pick(header, *_BLOCK_KEYS))[:255] or None,
            "district": _clean(_pick(header, *_DISTRICT_KEYS))[:255] or None,
            "date": sheet_date[:64] or None,
        },
        "footer": {
            "filler_name": _clean(_pick(footer, *_NAME_KEYS))[:255] or None,
            "designation": _clean(_pick(footer, *_DESIGNATION_KEYS))[:255] or None,
            "mobile": footer_mobile,
        },
        "rows": rows,
        "reference_date": ref,
    }
