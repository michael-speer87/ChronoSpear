from dataclasses import FrozenInstanceError
from typing import cast

import pytest

from chronospear.cam import ChronoStamp, SystemTime, WorldTime


def test_world_time_and_system_time_are_distinct_types() -> None:
    wt = WorldTime(50)
    st = SystemTime(50)
    wt_as_object: object = wt
    st_as_object: object = st

    assert wt.value == st.value == 50
    assert (type(wt), type(st)) == (WorldTime, SystemTime)
    assert wt_as_object != st_as_object


def test_chronostamp_pairs_the_two_coordinates() -> None:
    stamp = ChronoStamp(world_time=WorldTime(100), system_time=SystemTime(500))

    assert stamp.world_time == WorldTime(100)
    assert stamp.system_time == SystemTime(500)


def test_chronostamp_is_immutable() -> None:
    stamp = ChronoStamp(WorldTime(100), SystemTime(500))

    with pytest.raises(FrozenInstanceError):
        setattr(stamp, "world_time", WorldTime(101))


@pytest.mark.parametrize(
    ("world_time", "system_time", "message"),
    [
        (cast(WorldTime, SystemTime(1)), SystemTime(2), "world_time must be a WorldTime"),
        (WorldTime(1), cast(SystemTime, WorldTime(2)), "system_time must be a SystemTime"),
        (cast(WorldTime, 1), SystemTime(2), "world_time must be a WorldTime"),
        (WorldTime(1), cast(SystemTime, 2), "system_time must be a SystemTime"),
    ],
)
def test_chronostamp_rejects_incorrect_temporal_types(
    world_time: WorldTime,
    system_time: SystemTime,
    message: str,
) -> None:
    with pytest.raises(TypeError, match=message):
        ChronoStamp(world_time=world_time, system_time=system_time)


@pytest.mark.parametrize("time_type", [WorldTime, SystemTime])
def test_temporal_coordinates_reject_negative_values(
    time_type: type[WorldTime] | type[SystemTime],
) -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        time_type(-1)


@pytest.mark.parametrize("bad", [1.5, "1", True])
def test_world_time_rejects_non_integer_coordinates(bad: object) -> None:
    with pytest.raises(TypeError, match="integer coordinate"):
        WorldTime(cast(int, bad))


def test_world_time_advance_returns_new_coordinate() -> None:
    current = WorldTime(10)
    later = current.advance(5)

    assert current == WorldTime(10)
    assert later == WorldTime(15)


def test_system_time_advance_returns_new_coordinate() -> None:
    current = SystemTime(10)
    later = current.advance(1)

    assert current == SystemTime(10)
    assert later == SystemTime(11)


@pytest.mark.parametrize("time", [WorldTime(1), SystemTime(1)])
def test_temporal_advance_rejects_zero(time: WorldTime | SystemTime) -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        time.advance(0)
