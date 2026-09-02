from __future__ import annotations

import pytest

from chronospear.playground import PlaygroundAdapter, build_demo_world
from chronospear.playground.model import (
    ALRIC_ID,
    IS_A_ID,
    JOINED_ID,
    LEFT_ID,
    MEMBER_OF_ID,
    ROYAL_GUARD_ID,
    STONEBRIDGE_ID,
)


def refs(detail: object, group_name: str) -> set[str]:
    assert isinstance(detail, dict)
    groups = detail["groups"]
    assert isinstance(groups, list)
    for name, items in groups:
        if name == group_name:
            return {item["id"] for item in items}
    raise AssertionError(f"Missing group {group_name!r}")


def test_demo_world_uses_production_cam_catalogs() -> None:
    world = build_demo_world()

    assert [node.name for node in world.identities.all()] == [
        "Alric",
        "Elara",
        "Royal Guard",
        "Stonebridge",
        "Fighter",
    ]
    assert len(world.associations.all()) == 3
    assert len(world.occurrences.all()) == 2


def test_identity_view_resolves_associations_and_occurrences() -> None:
    adapter = PlaygroundAdapter(build_demo_world())

    alric = adapter.identity(str(ALRIC_ID))
    guard = adapter.identity(str(ROYAL_GUARD_ID))
    stonebridge = adapter.identity(str(STONEBRIDGE_ID))

    assert refs(alric, "Outgoing Associations") == {
        str(MEMBER_OF_ID),
        str(IS_A_ID),
    }
    assert refs(guard, "Incoming Associations") == {str(MEMBER_OF_ID)}
    assert refs(alric, "Participant in History") == {
        str(JOINED_ID),
        str(LEFT_ID),
    }
    assert refs(stonebridge, "Place of History") == {
        str(JOINED_ID),
        str(LEFT_ID),
    }


def test_association_view_resolves_source_and_target() -> None:
    detail = PlaygroundAdapter(build_demo_world()).association(
        str(MEMBER_OF_ID)
    )

    assert refs(detail, "Source Identity") == {str(ALRIC_ID)}
    assert refs(detail, "Target Identity") == {str(ROYAL_GUARD_ID)}


def test_occurrence_view_resolves_participants_place_and_lifecycle() -> None:
    adapter = PlaygroundAdapter(build_demo_world())
    started = adapter.occurrence(str(JOINED_ID))
    ended = adapter.occurrence(str(LEFT_ID))

    assert refs(ended, "Participants") == {str(ALRIC_ID)}
    assert refs(ended, "Place") == {str(STONEBRIDGE_ID)}
    assert refs(started, "Started Associations") == {str(MEMBER_OF_ID)}
    assert refs(ended, "Ended Associations") == {str(MEMBER_OF_ID)}


def test_association_view_resolves_reverse_lifecycle_occurrences() -> None:
    detail = PlaygroundAdapter(build_demo_world()).association(
        str(MEMBER_OF_ID)
    )

    assert refs(detail, "Started By") == {str(JOINED_ID)}
    assert refs(detail, "Ended By") == {str(LEFT_ID)}


@pytest.mark.parametrize("object_type", ["identity", "association", "occurrence"])
def test_unknown_object_ids_fail_cleanly(object_type: str) -> None:
    adapter = PlaygroundAdapter(build_demo_world())

    with pytest.raises(KeyError, match="Unknown playground"):
        if object_type == "identity":
            adapter.identity("missing")
        elif object_type == "association":
            adapter.association("missing")
        else:
            adapter.occurrence("missing")


def test_inspection_does_not_mutate_cam() -> None:
    world = build_demo_world()
    before = (
        world.identities.all(),
        world.associations.all(),
        world.occurrences.all(),
    )

    adapter = PlaygroundAdapter(world)
    adapter.snapshot()
    adapter.identity(str(ALRIC_ID))
    adapter.association(str(MEMBER_OF_ID))
    adapter.occurrence(str(JOINED_ID))

    assert before == (
        world.identities.all(),
        world.associations.all(),
        world.occurrences.all(),
    )
