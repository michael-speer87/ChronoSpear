from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest

from chronospear.cam import IdentityKind
from chronospear.playground import PlaygroundAdapter
from chronospear.world_import import WorldImportError, import_world


def _memory() -> dict[str, Any]:
    return {
        "identities": [
            {
                "key": "alric",
                "kind": "ENTITY",
                "name": "Alric",
                "synopsis": "Human fighter and veteran adventurer.",
                "description": "A veteran adventurer.",
            },
            {
                "key": "royal_guard",
                "kind": "ENTITY",
                "name": "Royal Guard",
                "description": "The royal military organization.",
            },
            {
                "key": "stonebridge",
                "kind": "PLACE",
                "name": "Stonebridge",
                "description": "A fortified settlement.",
            },
            {
                "key": "human",
                "kind": "DESCRIBER",
                "name": "Human",
                "description": "A human being.",
            },
        ],
        "associations": [
            {
                "key": "alric_guard_member",
                "source": "alric",
                "relationship": "MEMBER_OF",
                "target": "royal_guard",
            },
            {
                "key": "alric_is_human",
                "source": "alric",
                "relationship": "IS_A",
                "target": "human",
            },
        ],
        "historical_occurrences": [
            {
                "key": "alric_joins_guard",
                "participants": ["alric"],
                "place": "stonebridge",
                "world_time": 100,
                "system_time": 1,
                "synopsis": "Alric joined the Royal Guard.",
                "story": "Alric formally joined the Royal Guard in Stonebridge.",
                "started_associations": ["alric_guard_member"],
                "ended_associations": [],
            }
        ],
    }


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")


def _read_catalog(package: Path) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads((package / "catalog.json").read_text(encoding="utf-8")),
    )


def _prepare(package: Path, memory: dict[str, Any] | None = None) -> dict[str, Any]:
    content = memory or _memory()
    _write_json(package / "memory.json", content)
    return content


def _assert_uuid(identifier: str, prefix: str) -> None:
    assert identifier.startswith(prefix)
    assert UUID(identifier.removeprefix(prefix)).version == 4


def test_first_import_allocates_typed_ids_builds_cam_and_supports_playground(
    tmp_path: Path,
) -> None:
    memory = _prepare(tmp_path)

    world = import_world(tmp_path)
    catalog = _read_catalog(tmp_path)

    for key in ("alric", "royal_guard"):
        _assert_uuid(catalog["identities"][key]["id"], "E-")
    _assert_uuid(catalog["identities"]["stonebridge"]["id"], "P-")
    _assert_uuid(catalog["identities"]["human"]["id"], "D-")
    _assert_uuid(catalog["associations"]["alric_guard_member"], "A-")
    _assert_uuid(catalog["historical_occurrences"]["alric_joins_guard"], "HO-")
    assert len(world.identities.all()) == len(memory["identities"])
    alric = world.identities.all()[0]
    assert alric.name == "Alric"
    assert alric.synopsis == "Human fighter and veteran adventurer."
    assert alric.description == "A veteran adventurer."
    assert world.identities.all()[1].synopsis == ""
    snapshot = PlaygroundAdapter(world).snapshot()
    assert len(snapshot["details"]) == 7
    alric_detail = next(
        detail
        for detail in snapshot["details"]
        if detail["id"] == str(alric.identity_id)
    )
    assert ("Synopsis", "Human fighter and veteran adventurer.") in alric_detail["fields"]


def test_repeat_import_preserves_all_canonical_ids(tmp_path: Path) -> None:
    _prepare(tmp_path)
    first_world = import_world(tmp_path)
    first_catalog = _read_catalog(tmp_path)

    second_world = import_world(tmp_path)

    assert _read_catalog(tmp_path) == first_catalog
    assert first_world.identities.all() == second_world.identities.all()
    assert first_world.associations.all() == second_world.associations.all()
    assert first_world.occurrences.all() == second_world.occurrences.all()


def test_new_content_gets_one_new_id_while_existing_ids_remain(tmp_path: Path) -> None:
    memory = _prepare(tmp_path)
    import_world(tmp_path)
    original = _read_catalog(tmp_path)
    memory["identities"].append(
        {
            "key": "elara",
            "kind": "ENTITY",
            "name": "Elara",
            "description": "A traveler.",
        }
    )
    _write_json(tmp_path / "memory.json", memory)

    import_world(tmp_path)
    updated = _read_catalog(tmp_path)

    assert updated["identities"]["alric"] == original["identities"]["alric"]
    _assert_uuid(updated["identities"]["elara"]["id"], "E-")
    assert updated["identities"]["elara"]["id"] not in {
        entry["id"] for entry in original["identities"].values()
    }


def test_renaming_identity_preserves_canonical_id(tmp_path: Path) -> None:
    memory = _prepare(tmp_path)
    import_world(tmp_path)
    original_id = _read_catalog(tmp_path)["identities"]["alric"]["id"]
    memory["identities"][0]["name"] = "Alric Stonehand"
    _write_json(tmp_path / "memory.json", memory)

    world = import_world(tmp_path)

    assert _read_catalog(tmp_path)["identities"]["alric"]["id"] == original_id
    assert world.identities.all()[0].name == "Alric Stonehand"


@pytest.mark.parametrize(
    ("field", "revised"),
    [
        ("synopsis", "Veteran human fighter and former royal soldier."),
        ("description", "Revised full authoritative detail."),
    ],
)
def test_identity_content_change_preserves_canonical_id(
    tmp_path: Path, field: str, revised: str
) -> None:
    memory = _prepare(tmp_path)
    first_world = import_world(tmp_path)
    original_id = str(first_world.identities.all()[0].identity_id)
    memory["identities"][0][field] = revised
    _write_json(tmp_path / "memory.json", memory)

    second_world = import_world(tmp_path)
    identity = second_world.identities.all()[0]

    assert str(identity.identity_id) == original_id
    assert getattr(identity, field) == revised


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda memory: memory["associations"][0].update(source="missing"),
            "unknown source Identity key",
        ),
        (
            lambda memory: memory["historical_occurrences"][0].update(
                started_associations=["missing"]
            ),
            "unknown started_associations key",
        ),
    ],
)
def test_broken_human_references_fail_without_catalog_write(
    tmp_path: Path,
    mutation: Any,
    message: str,
) -> None:
    memory = _prepare(tmp_path)
    mutation(memory)
    _write_json(tmp_path / "memory.json", memory)

    with pytest.raises(WorldImportError, match=message):
        import_world(tmp_path)

    assert not (tmp_path / "catalog.json").exists()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("participants", ["stonebridge"], "IdentityKind.ENTITY"),
        ("place", "royal_guard", "IdentityKind.PLACE"),
    ],
)
def test_production_cam_rejects_invalid_occurrence_anchor_semantics(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    memory = _prepare(tmp_path)
    memory["historical_occurrences"][0][field] = value
    _write_json(tmp_path / "memory.json", memory)

    with pytest.raises(ValueError, match=message):
        import_world(tmp_path)

    assert not (tmp_path / "catalog.json").exists()


def test_corrupt_catalog_fails_without_silent_replacement(tmp_path: Path) -> None:
    _prepare(tmp_path)
    corrupt = {
        "identities": {"alric": {"kind": "ENTITY", "id": "P-not-a-uuid"}},
        "associations": {},
        "historical_occurrences": {},
    }
    _write_json(tmp_path / "catalog.json", corrupt)

    with pytest.raises(WorldImportError, match="Catalog identity 'alric' is invalid"):
        import_world(tmp_path)

    assert _read_catalog(tmp_path) == corrupt


def test_cataloged_identity_kind_conflict_fails(tmp_path: Path) -> None:
    memory = _prepare(tmp_path)
    import_world(tmp_path)
    memory["identities"][0]["kind"] = IdentityKind.PLACE.value
    _write_json(tmp_path / "memory.json", memory)

    with pytest.raises(WorldImportError, match="changed kind from ENTITY to PLACE"):
        import_world(tmp_path)


def test_removed_entry_stays_cataloged_and_recovers_original_id(tmp_path: Path) -> None:
    memory = _prepare(tmp_path)
    import_world(tmp_path)
    original_catalog = _read_catalog(tmp_path)
    human_record = memory["identities"].pop(3)
    memory["associations"].pop(1)
    _write_json(tmp_path / "memory.json", memory)

    world_without = import_world(tmp_path)

    assert all(node.name != "Human" for node in world_without.identities.all())
    assert _read_catalog(tmp_path)["identities"]["human"] == original_catalog["identities"]["human"]

    memory["identities"].append(human_record)
    _write_json(tmp_path / "memory.json", memory)
    world_restored = import_world(tmp_path)
    restored = next(node for node in world_restored.identities.all() if node.name == "Human")
    assert str(restored.identity_id) == original_catalog["identities"]["human"]["id"]
