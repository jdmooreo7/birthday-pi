from datetime import date

from birthday_pi.dates import how_far, next_occurrence, valid_month_day


def test_next_occurrence_today_counts():
    assert next_occurrence(10, 14, date(2026, 10, 14)) == date(2026, 10, 14)


def test_next_occurrence_rolls_to_next_year():
    assert next_occurrence(1, 5, date(2026, 10, 14)) == date(2027, 1, 5)


def test_leap_day_on_feb_28_in_other_years():
    assert next_occurrence(2, 29, date(2027, 1, 1)) == date(2027, 2, 28)
    assert next_occurrence(2, 29, date(2028, 1, 1)) == date(2028, 2, 29)


def test_valid_month_day():
    assert valid_month_day(2, 29)
    assert not valid_month_day(2, 30)
    assert not valid_month_day(4, 31)
    assert not valid_month_day(13, 1)


def test_how_far():
    assert how_far(0) == "today"
    assert how_far(1) == "tomorrow"
    assert how_far(10) == "in 10 days"
    assert how_far(21) == "in 3 weeks"
