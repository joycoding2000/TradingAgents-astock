from datetime import date

from web.trading_dates import most_recent_weekday


def test_weekend_analysis_date_uses_prior_friday():
    assert most_recent_weekday(date(2026, 7, 18)) == date(2026, 7, 17)
    assert most_recent_weekday(date(2026, 7, 19)) == date(2026, 7, 17)


def test_weekday_analysis_date_is_preserved():
    assert most_recent_weekday(date(2026, 7, 17)) == date(2026, 7, 17)
