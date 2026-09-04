"""Deterministic calendar interpretation of objective WorldTime coordinates."""

from __future__ import annotations

from dataclasses import dataclass

from chronospear.cam.time import WorldTime


def _require_int(value: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an integer.")


def _require_positive(value: int, label: str) -> None:
    _require_int(value, label)
    if value <= 0:
        raise ValueError(f"{label} must be greater than zero.")


def _require_name(value: str, label: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string.")
    if not value or value != value.strip():
        raise ValueError(f"{label} must be nonblank and contain no outer whitespace.")


@dataclass(frozen=True, slots=True)
class PeriodDefinition:
    """One named, fixed-length period in a calendar year."""

    name: str
    days: int

    def __post_init__(self) -> None:
        _require_name(self.name, "Period name")
        _require_positive(self.days, f"Period {self.name!r} days")


@dataclass(frozen=True, slots=True)
class EpochDefinition:
    """Calendar interpretation assigned to WorldTime zero."""

    year: int
    period: str
    day: int
    weekday: str
    hour: int = 0
    minute: int = 0
    second: int = 0

    def __post_init__(self) -> None:
        _require_int(self.year, "Epoch year")
        _require_name(self.period, "Epoch period")
        _require_positive(self.day, "Epoch day")
        _require_name(self.weekday, "Epoch weekday")
        for value, label in (
            (self.hour, "Epoch hour"),
            (self.minute, "Epoch minute"),
            (self.second, "Epoch second"),
        ):
            _require_int(value, label)
            if value < 0:
                raise ValueError(f"{label} cannot be negative.")


@dataclass(frozen=True, slots=True)
class CalendarDefinition:
    """Immutable structure used to interpret WorldTime."""

    name: str
    seconds_per_minute: int
    minutes_per_hour: int
    hours_per_day: int
    weekdays: tuple[str, ...]
    periods: tuple[PeriodDefinition, ...]
    epoch: EpochDefinition

    def __post_init__(self) -> None:
        _require_name(self.name, "Calendar name")
        _require_positive(self.seconds_per_minute, "seconds_per_minute")
        _require_positive(self.minutes_per_hour, "minutes_per_hour")
        _require_positive(self.hours_per_day, "hours_per_day")
        if not isinstance(self.weekdays, tuple):
            raise TypeError("Calendar weekdays must be a tuple.")
        if not self.weekdays:
            raise ValueError("Calendar must define at least one weekday.")
        for weekday in self.weekdays:
            _require_name(weekday, "Weekday name")
        if len({name.casefold() for name in self.weekdays}) != len(self.weekdays):
            raise ValueError("Calendar weekday names must be unambiguous.")
        if not isinstance(self.periods, tuple):
            raise TypeError("Calendar periods must be a tuple.")
        if not self.periods:
            raise ValueError("Calendar must define at least one period.")
        if not all(isinstance(period, PeriodDefinition) for period in self.periods):
            raise TypeError("Calendar periods must contain PeriodDefinition values.")
        period_names = tuple(period.name for period in self.periods)
        if len({name.casefold() for name in period_names}) != len(period_names):
            raise ValueError("Calendar period names must be unambiguous.")
        if not isinstance(self.epoch, EpochDefinition):
            raise TypeError("Calendar epoch must be an EpochDefinition.")
        if self.epoch.period not in period_names:
            raise ValueError("Epoch period must reference a configured period.")
        if self.epoch.weekday not in self.weekdays:
            raise ValueError("Epoch weekday must reference a configured weekday.")
        epoch_period = self.periods[period_names.index(self.epoch.period)]
        if self.epoch.day > epoch_period.days:
            raise ValueError("Epoch day is outside the configured epoch period.")
        if self.epoch.hour >= self.hours_per_day:
            raise ValueError("Epoch hour is outside the configured day.")
        if self.epoch.minute >= self.minutes_per_hour:
            raise ValueError("Epoch minute is outside the configured hour.")
        if self.epoch.second >= self.seconds_per_minute:
            raise ValueError("Epoch second is outside the configured minute.")


@dataclass(frozen=True, slots=True)
class ResolvedCalendarDate:
    """Immutable calendar-facing interpretation of one WorldTime coordinate."""

    year: int
    period: str
    day: int
    weekday: str
    hour: int
    minute: int
    second: int


class CalendarResolver:
    """Resolve WorldTime without materializing elapsed dates or days."""

    @staticmethod
    def resolve(
        world_time: WorldTime, calendar: CalendarDefinition
    ) -> ResolvedCalendarDate:
        if not isinstance(world_time, WorldTime):
            raise TypeError("world_time must be a WorldTime.")
        if not isinstance(calendar, CalendarDefinition):
            raise TypeError("calendar must be a CalendarDefinition.")

        seconds_per_hour = (
            calendar.seconds_per_minute * calendar.minutes_per_hour
        )
        seconds_per_day = seconds_per_hour * calendar.hours_per_day
        days_per_year = sum(period.days for period in calendar.periods)
        seconds_per_year = days_per_year * seconds_per_day

        epoch_period_index = next(
            index
            for index, period in enumerate(calendar.periods)
            if period.name == calendar.epoch.period
        )
        epoch_day_of_year = sum(
            period.days for period in calendar.periods[:epoch_period_index]
        ) + (calendar.epoch.day - 1)
        epoch_second_of_day = (
            calendar.epoch.hour * seconds_per_hour
            + calendar.epoch.minute * calendar.seconds_per_minute
            + calendar.epoch.second
        )
        epoch_second_of_year = (
            epoch_day_of_year * seconds_per_day + epoch_second_of_day
        )
        year_offset, second_of_year = divmod(
            epoch_second_of_year + world_time.value, seconds_per_year
        )
        day_of_year, second_of_day = divmod(second_of_year, seconds_per_day)

        remaining_day = day_of_year
        resolved_period = calendar.periods[0]
        for period in calendar.periods:
            if remaining_day < period.days:
                resolved_period = period
                break
            remaining_day -= period.days

        hour, within_hour = divmod(second_of_day, seconds_per_hour)
        minute, second = divmod(within_hour, calendar.seconds_per_minute)
        elapsed_epoch_days = (epoch_second_of_day + world_time.value) // seconds_per_day
        epoch_weekday_index = calendar.weekdays.index(calendar.epoch.weekday)
        weekday = calendar.weekdays[
            (epoch_weekday_index + elapsed_epoch_days) % len(calendar.weekdays)
        ]
        return ResolvedCalendarDate(
            year=calendar.epoch.year + year_offset,
            period=resolved_period.name,
            day=remaining_day + 1,
            weekday=weekday,
            hour=hour,
            minute=minute,
            second=second,
        )

    @staticmethod
    def to_world_time(
        calendar: CalendarDefinition,
        *,
        year: int,
        period: str,
        day: int,
        hour: int = 0,
        minute: int = 0,
        second: int = 0,
    ) -> WorldTime:
        """Convert one exact calendar instant to its objective WorldTime."""

        if not isinstance(calendar, CalendarDefinition):
            raise TypeError("calendar must be a CalendarDefinition.")
        _require_int(year, "Calendar date year")
        _require_name(period, "Calendar date period")
        _require_positive(day, "Calendar date day")
        for value, label, limit in (
            (hour, "Calendar date hour", calendar.hours_per_day),
            (minute, "Calendar date minute", calendar.minutes_per_hour),
            (second, "Calendar date second", calendar.seconds_per_minute),
        ):
            _require_int(value, label)
            if value < 0 or value >= limit:
                raise ValueError(f"{label} is outside the configured calendar units.")

        period_names = tuple(item.name for item in calendar.periods)
        if period not in period_names:
            raise ValueError("Calendar date period must reference a configured period.")
        period_index = period_names.index(period)
        period_definition = calendar.periods[period_index]
        if day > period_definition.days:
            raise ValueError("Calendar date day is outside the requested period.")

        seconds_per_hour = (
            calendar.seconds_per_minute * calendar.minutes_per_hour
        )
        seconds_per_day = seconds_per_hour * calendar.hours_per_day
        days_per_year = sum(item.days for item in calendar.periods)
        seconds_per_year = days_per_year * seconds_per_day

        target_day_of_year = sum(
            item.days for item in calendar.periods[:period_index]
        ) + (day - 1)
        target_second_of_year = (
            target_day_of_year * seconds_per_day
            + hour * seconds_per_hour
            + minute * calendar.seconds_per_minute
            + second
        )

        epoch_period_index = period_names.index(calendar.epoch.period)
        epoch_day_of_year = sum(
            item.days for item in calendar.periods[:epoch_period_index]
        ) + (calendar.epoch.day - 1)
        epoch_second_of_year = (
            epoch_day_of_year * seconds_per_day
            + calendar.epoch.hour * seconds_per_hour
            + calendar.epoch.minute * calendar.seconds_per_minute
            + calendar.epoch.second
        )
        coordinate = (
            (year - calendar.epoch.year) * seconds_per_year
            + target_second_of_year
            - epoch_second_of_year
        )
        if coordinate < 0:
            raise ValueError("Calendar date is before WorldTime(0) for this calendar.")
        return WorldTime(coordinate)


def resolve(
    world_time: WorldTime, calendar: CalendarDefinition
) -> ResolvedCalendarDate:
    """Resolve a WorldTime using the supplied immutable calendar definition."""

    return CalendarResolver.resolve(world_time, calendar)


def to_world_time(
    calendar: CalendarDefinition,
    *,
    year: int,
    period: str,
    day: int,
    hour: int = 0,
    minute: int = 0,
    second: int = 0,
) -> WorldTime:
    """Convert an exact calendar instant to the supplied calendar's WorldTime."""

    return CalendarResolver.to_world_time(
        calendar,
        year=year,
        period=period,
        day=day,
        hour=hour,
        minute=minute,
        second=second,
    )
