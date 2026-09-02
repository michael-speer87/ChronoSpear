from __future__ import annotations

import pytest

from chronospear.playground import PlaygroundAdapter, build_demo_world


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

    alric = adapter.identity("alric")
    guard = adapter.identity("royal_guard")
    stonebridge = adapter.identity("stonebridge")

    assert refs(alric, "Outgoing Associations") == {
        "alric_member_of_royal_guard",
        "alric_is_a_fighter",
    }
    assert refs(guard, "Incoming Associations") == {"alric_member_of_royal_guard"}
    assert refs(alric, "Participant in History") == {
        "alric_joins_guard",
        "alric_leaves_guard",
    }
    assert refs(stonebridge, "Place of History") == {
        "alric_joins_guard",
        "alric_leaves_guard",
    }


def test_association_view_resolves_source_and_target() -> None:
    detail = PlaygroundAdapter(build_demo_world()).association(
        "alric_member_of_royal_guard"
    )

    assert refs(detail, "Source Identity") == {"alric"}
    assert refs(detail, "Target Identity") == {"royal_guard"}


def test_occurrence_view_resolves_participants_and_place() -> None:
    detail = PlaygroundAdapter(build_demo_world()).occurrence("alric_leaves_guard")

    assert refs(detail, "Participants") == {"alric"}
    assert refs(detail, "Place") == {"stonebridge"}


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
    adapter.identity("alric")
    adapter.association("alric_member_of_royal_guard")
    adapter.occurrence("alric_joins_guard")

    assert before == (
        world.identities.all(),
        world.associations.all(),
        world.occurrences.all(),
    )
