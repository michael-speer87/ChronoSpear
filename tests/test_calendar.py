from dataclasses import FrozenInstanceError, replace
from typing import Any

import pytest

from chronospear import (
    CalendarDefinition,
    CalendarResolver,
    EpochDefinition,
    PeriodDefinition,
    ResolvedCalendarDate,
    resolve,
    to_world_time,
)
from chronospear.cam import WorldTime

SECONDS_PER_DAY = 86_400


def simple_calendar() -> CalendarDefinition:
    return CalendarDefinition(
        name="Simple Calendar",
        seconds_per_minute=60,
        minutes_per_hour=60,
        hours_per_day=24,
        weekdays=(
            "DayOne",
            "DayTwo",
            "DayThree",
            "DayFour",
            "DayFive",
            "DaySix",
            "DaySeven",
        ),
        periods=(
            PeriodDefinition("Firstmonth", 30),
            PeriodDefinition("Secondmonth", 31),
            PeriodDefinition("Thirdmonth", 29),
        ),
        epoch=EpochDefinition(
            year=1,
            period="Firstmonth",
            day=1,
            weekday="DayOne",
        ),
    )


@pytest.mark.parametrize(
    ("coordinate", "expected"),
    [
        (
            0,
            ResolvedCalendarDate(1, "Firstmonth", 1, "DayOne", 0, 0, 0),
        ),
        (
            86_399,
            ResolvedCalendarDate(1, "Firstmonth", 1, "DayOne", 23, 59, 59),
        ),
        (
            86_400,
            ResolvedCalendarDate(1, "Firstmonth", 2, "DayTwo", 0, 0, 0),
        ),
    ],
)
def test_resolves_epoch_and_intra_day_boundaries(
    coordinate: int, expected: ResolvedCalendarDate
) -> None:
    assert resolve(WorldTime(coordinate), simple_calendar()) == expected


def test_resolves_period_boundaries() -> None:
    calendar = simple_calendar()

    assert resolve(WorldTime(30 * SECONDS_PER_DAY - 1), calendar) == (
        ResolvedCalendarDate(1, "Firstmonth", 30, "DayTwo", 23, 59, 59)
    )
    assert resolve(WorldTime(30 * SECONDS_PER_DAY), calendar) == (
        ResolvedCalendarDate(1, "Secondmonth", 1, "DayThree", 0, 0, 0)
    )


def test_resolves_year_boundary_with_weekday_progression() -> None:
    calendar = simple_calendar()
    final_second = 90 * SECONDS_PER_DAY - 1

    assert resolve(WorldTime(final_second), calendar) == ResolvedCalendarDate(
        1, "Thirdmonth", 29, "DaySix", 23, 59, 59
    )
    assert resolve(WorldTime(final_second + 1), calendar) == ResolvedCalendarDate(
        2, "Firstmonth", 1, "DaySeven", 0, 0, 0
    )


def test_non_default_epoch_resolves_exactly_and_advances() -> None:
    calendar = replace(
        simple_calendar(),
        epoch=EpochDefinition(
            year=842,
            period="Secondmonth",
            day=17,
            weekday="DayFive",
            hour=3,
            minute=14,
            second=15,
        ),
    )
    until_midnight = 20 * 3600 + 45 * 60 + 45

    assert resolve(WorldTime(0), calendar) == ResolvedCalendarDate(
        842, "Secondmonth", 17, "DayFive", 3, 14, 15
    )
    assert resolve(WorldTime(until_midnight), calendar) == ResolvedCalendarDate(
        842, "Secondmonth", 18, "DaySix", 0, 0, 0
    )


def test_same_world_time_resolves_independently_through_different_calendars() -> None:
    world_time = WorldTime(100_000)
    first = simple_calendar()
    second = CalendarDefinition(
        name="Short Calendar",
        seconds_per_minute=10,
        minutes_per_hour=10,
        hours_per_day=10,
        weekdays=("Bright", "Dim"),
        periods=(PeriodDefinition("Onlyperiod", 5),),
        epoch=EpochDefinition(20, "Onlyperiod", 1, "Bright"),
    )

    first_result = CalendarResolver.resolve(world_time, first)
    second_result = CalendarResolver.resolve(world_time, second)

    assert first_result != second_result
    assert world_time == WorldTime(100_000)
    assert first == simple_calendar()


def test_large_world_time_resolves_deterministically() -> None:
    world_time = WorldTime(10**15)
    calendar = simple_calendar()

    first = resolve(world_time, calendar)
    second = resolve(world_time, calendar)

    assert first == second
    assert first.year > 1
    assert first.period in {period.name for period in calendar.periods}


def reverse_resolved(
    resolved: ResolvedCalendarDate, calendar: CalendarDefinition
) -> WorldTime:
    return CalendarResolver.to_world_time(
        calendar,
        year=resolved.year,
        period=resolved.period,
        day=resolved.day,
        hour=resolved.hour,
        minute=resolved.minute,
        second=resolved.second,
    )


@pytest.mark.parametrize(
    "coordinate",
    [
        0,
        SECONDS_PER_DAY - 1,
        SECONDS_PER_DAY,
        30 * SECONDS_PER_DAY - 1,
        30 * SECONDS_PER_DAY,
        90 * SECONDS_PER_DAY - 1,
        90 * SECONDS_PER_DAY,
        10**15,
    ],
)
def test_world_time_to_calendar_to_world_time_round_trip(coordinate: int) -> None:
    calendar = simple_calendar()
    original = WorldTime(coordinate)

    assert reverse_resolved(resolve(original, calendar), calendar) == original


def test_non_default_epoch_round_trips_world_time() -> None:
    calendar = replace(
        simple_calendar(),
        epoch=EpochDefinition(842, "Secondmonth", 17, "DayFive", 3, 14, 15),
    )

    for original in (WorldTime(0), WorldTime(74_745), WorldTime(10**12)):
        assert reverse_resolved(resolve(original, calendar), calendar) == original


def test_calendar_date_to_world_time_to_calendar_date_round_trip() -> None:
    calendar = simple_calendar()
    expected = ResolvedCalendarDate(
        12, "Thirdmonth", 9, "DaySix", 17, 23, 41
    )

    world_time = to_world_time(
        calendar,
        year=expected.year,
        period=expected.period,
        day=expected.day,
        hour=expected.hour,
        minute=expected.minute,
        second=expected.second,
    )

    actual = resolve(world_time, calendar)
    assert actual.year == expected.year
    assert actual.period == expected.period
    assert actual.day == expected.day
    assert actual.hour == expected.hour
    assert actual.minute == expected.minute
    assert actual.second == expected.second


def test_same_apparent_date_maps_differently_under_different_calendars() -> None:
    first = simple_calendar()
    second = CalendarDefinition(
        name="Fast Calendar",
        seconds_per_minute=10,
        minutes_per_hour=10,
        hours_per_day=10,
        weekdays=("DayOne", "DayTwo"),
        periods=(PeriodDefinition("Firstmonth", 30),),
        epoch=EpochDefinition(1, "Firstmonth", 1, "DayOne"),
    )
    first_time = to_world_time(first, year=1, period="Firstmonth", day=2)
    second_time = to_world_time(second, year=1, period="Firstmonth", day=2)

    assert first_time == WorldTime(86_400)
    assert second_time == WorldTime(1_000)
    assert first_time != second_time
    for calendar in (first, second):
        coordinate = WorldTime(100_000)
        assert reverse_resolved(resolve(coordinate, calendar), calendar) == coordinate


@pytest.mark.parametrize(
    ("date", "message"),
    [
        ({"year": 1, "period": "Missing", "day": 1}, "configured period"),
        ({"year": 1, "period": "Firstmonth", "day": 0}, "greater than zero"),
        ({"year": 1, "period": "Firstmonth", "day": 31}, "requested period"),
        ({"year": 1, "period": "Firstmonth", "day": 1, "hour": 24}, "hour"),
        ({"year": 1, "period": "Firstmonth", "day": 1, "minute": 60}, "minute"),
        ({"year": 1, "period": "Firstmonth", "day": 1, "second": 60}, "second"),
    ],
)
def test_reverse_conversion_rejects_invalid_dates(
    date: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        to_world_time(simple_calendar(), **date)


def test_reverse_conversion_rejects_date_before_epoch() -> None:
    calendar = replace(
        simple_calendar(),
        epoch=EpochDefinition(842, "Secondmonth", 17, "DayFive", 3, 14, 15),
    )

    with pytest.raises(ValueError, match=r"before WorldTime\(0\)"):
        to_world_time(
            calendar,
            year=842,
            period="Secondmonth",
            day=17,
            hour=3,
            minute=14,
            second=14,
        )


@pytest.mark.parametrize(
    "date",
    [
        {"year": "1", "period": "Firstmonth", "day": 1},
        {"year": 1, "period": 1, "day": 1},
        {"year": 1, "period": "Firstmonth", "day": "1"},
        {"year": 1, "period": "Firstmonth", "day": 1, "hour": True},
    ],
)
def test_reverse_conversion_rejects_untyped_date_components(
    date: dict[str, Any],
) -> None:
    with pytest.raises(TypeError):
        to_world_time(simple_calendar(), **date)


def test_reverse_conversion_requires_calendar_definition() -> None:
    with pytest.raises(TypeError, match="must be a CalendarDefinition"):
        to_world_time(
            object(),  # type: ignore[arg-type]
            year=1,
            period="Firstmonth",
            day=1,
        )


def test_calendar_values_are_immutable() -> None:
    calendar = simple_calendar()
    resolved = resolve(WorldTime(0), calendar)

    with pytest.raises(FrozenInstanceError):
        setattr(calendar, "name", "Changed")  # noqa: B010
    with pytest.raises(FrozenInstanceError):
        setattr(resolved, "day", 2)  # noqa: B010


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"seconds_per_minute": 0}, "seconds_per_minute"),
        ({"minutes_per_hour": 0}, "minutes_per_hour"),
        ({"hours_per_day": 0}, "hours_per_day"),
        ({"weekdays": ()}, "at least one weekday"),
        ({"weekdays": ("DayOne", "dayone")}, "unambiguous"),
        ({"periods": ()}, "at least one period"),
        (
            {"periods": (PeriodDefinition("Firstmonth", 1), PeriodDefinition("firstmonth", 1))},
            "unambiguous",
        ),
        ({"epoch": EpochDefinition(1, "Missing", 1, "DayOne")}, "Epoch period"),
        ({"epoch": EpochDefinition(1, "Firstmonth", 1, "Missing")}, "Epoch weekday"),
        ({"epoch": EpochDefinition(1, "Firstmonth", 31, "DayOne")}, "Epoch day"),
        ({"epoch": EpochDefinition(1, "Firstmonth", 1, "DayOne", hour=24)}, "Epoch hour"),
        (
            {"epoch": EpochDefinition(1, "Firstmonth", 1, "DayOne", minute=60)},
            "Epoch minute",
        ),
        (
            {"epoch": EpochDefinition(1, "Firstmonth", 1, "DayOne", second=60)},
            "Epoch second",
        ),
    ],
)
def test_calendar_definition_rejects_invalid_configuration(
    changes: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(simple_calendar(), **changes)


def test_period_rejects_nonpositive_days() -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        PeriodDefinition("Empty", 0)


def test_calendar_rejects_non_tuple_collections() -> None:
    with pytest.raises(TypeError, match="weekdays must be a tuple"):
        replace(simple_calendar(), weekdays=["DayOne"])  # type: ignore[arg-type]


def test_resolver_requires_typed_world_time() -> None:
    with pytest.raises(TypeError, match="must be a WorldTime"):
        resolve(1, simple_calendar())  # type: ignore[arg-type]
