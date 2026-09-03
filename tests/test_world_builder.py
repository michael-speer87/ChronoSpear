from __future__ import annotations

import json
from pathlib import Path

import pytest

from chronospear.cam import IdentityKind
from chronospear.world_builder import (
    AssociationDraft,
    AuthoringWorld,
    HistoricalOccurrenceDraft,
    IdentityDraft,
    MemoryJsonSerializer,
)
from chronospear.world_import import WorldImportError, import_world


def _world() -> AuthoringWorld:
    return AuthoringWorld(
        identities=[
            IdentityDraft(
                key="e1",
                kind=IdentityKind.ENTITY,
                name="Alric",
                synopsis="Human fighter and veteran adventurer.",
                description="Line one.\n\nLine two contains detailed identity information.",
            ),
            IdentityDraft(
                key="e2",
                kind=IdentityKind.ENTITY,
                name="Elara",
                synopsis="",
                description="A traveler.",
            ),
            IdentityDraft(
                key="p1",
                kind=IdentityKind.PLACE,
                name="Stonebridge",
                description="A fortified settlement.",
            ),
            IdentityDraft(
                key="d1",
                kind=IdentityKind.DESCRIBER,
                name="Human",
                description="A human being.",
            ),
        ],
        associations=[
            AssociationDraft(
                key="a1", source="e1", relationship="IS_A", target="d1"
            )
        ],
        historical_occurrences=[
            HistoricalOccurrenceDraft(
                key="ho1",
                participants=["e1", "e2"],
                place="p1",
                world_time=100,
                system_time=1,
                synopsis="Alric and Elara met.",
                story="Alric and Elara met in Stonebridge.",
                started_associations=["a1"],
                ended_associations=[],
            )
        ],
    )


@pytest.mark.parametrize(
    ("family", "existing", "expected"),
    [
        ("ENTITY", [], "e1"),
        (
            "ENTITY",
            [IdentityDraft("e1", IdentityKind.ENTITY, "One")],
            "e2",
        ),
        (
            "ENTITY",
            [
                IdentityDraft("e1", IdentityKind.ENTITY, "One"),
                IdentityDraft("e3", IdentityKind.ENTITY, "Three"),
            ],
            "e2",
        ),
    ],
)
def test_key_suggestion_uses_lowest_unused_positive_number(
    family: str, existing: list[IdentityDraft], expected: str
) -> None:
    assert AuthoringWorld(identities=existing).suggest_key(family) == expected


def test_key_suggestions_are_scoped_to_logical_family() -> None:
    world = _world()

    assert world.suggest_key("PLACE") == "p2"
    assert world.suggest_key("DESCRIBER") == "d2"
    assert world.suggest_key("association") == "a2"
    assert world.suggest_key("historical_occurrence") == "ho2"


def test_memory_json_round_trip_preserves_logical_authoring_objects(
    tmp_path: Path,
) -> None:
    serializer = MemoryJsonSerializer()
    original = _world()

    serializer.save(tmp_path, original)
    loaded = serializer.load(tmp_path)

    assert loaded == original
    assert loaded.identities[0].synopsis == "Human fighter and veteran adventurer."
    assert loaded.identities[1].synopsis == ""
    assert "\n\n" in loaded.identities[0].description
    document = json.loads((tmp_path / "memory.json").read_text(encoding="utf-8"))
    assert document["associations"][0] == {
        "key": "a1",
        "source": "e1",
        "relationship": "IS_A",
        "target": "d1",
    }
    assert document["historical_occurrences"][0]["participants"] == ["e1", "e2"]
    assert document["historical_occurrences"][0]["place"] == "p1"
    assert document["historical_occurrences"][0]["started_associations"] == ["a1"]
    assert document["historical_occurrences"][0]["ended_associations"] == []


def test_save_rejects_invalid_references_without_replacing_memory(tmp_path: Path) -> None:
    serializer = MemoryJsonSerializer()
    serializer.save(tmp_path, _world())
    original_bytes = (tmp_path / "memory.json").read_bytes()
    invalid = _world()
    invalid.associations[0].source = "missing"

    with pytest.raises(WorldImportError, match="unknown source Identity key"):
        serializer.save(tmp_path, invalid)

    assert (tmp_path / "memory.json").read_bytes() == original_bytes


def test_save_rejects_same_started_and_ended_association(tmp_path: Path) -> None:
    world = _world()
    world.historical_occurrences[0].ended_associations = ["a1"]

    with pytest.raises(WorldImportError, match="cannot both start and end"):
        MemoryJsonSerializer().save(tmp_path, world)


def test_existing_world_edit_preserves_keys_and_imports(tmp_path: Path) -> None:
    serializer = MemoryJsonSerializer()
    serializer.save(tmp_path, _world())
    loaded = serializer.load(tmp_path)
    original_keys = [item.key for item in loaded.identities]
    loaded.identities[0].name = "Sir Alric Stonehand"
    loaded.identities[0].description = "Revised authoritative detail."

    serializer.save(tmp_path, loaded)
    reloaded = serializer.load(tmp_path)
    imported = import_world(tmp_path)

    assert [item.key for item in reloaded.identities] == original_keys
    assert reloaded.identities[0].name == "Sir Alric Stonehand"
    assert imported.identities.all()[0].name == "Sir Alric Stonehand"


def test_builder_never_changes_catalog_json(tmp_path: Path) -> None:
    catalog = b'{"machine_owned": true, "leave": "exactly alone"}\n'
    (tmp_path / "catalog.json").write_bytes(catalog)

    serializer = MemoryJsonSerializer()
    serializer.save(tmp_path, _world())
    loaded = serializer.load(tmp_path)
    loaded.identities[0].synopsis = "Edited summary."
    serializer.save(tmp_path, loaded)

    assert (tmp_path / "catalog.json").read_bytes() == catalog


def test_apply_workflow_commits_only_after_validation_then_resets_to_add_mode() -> None:
    from chronospear.world_builder.__main__ import _PAGE

    failure = "catch(error){const status=$('#status');status.textContent='Cannot apply: '"
    success = "world=candidate;dirty();render();reset(item)"

    assert "await validateCandidate(candidate)" in _PAGE
    assert failure in _PAGE
    assert _PAGE.index("await validateCandidate(candidate)") < _PAGE.index(success)
    assert "return}world=candidate" in _PAGE
    assert "f.reset();f.kind.value=kind;f.index.value=''" in _PAGE
    assert "f.reset();f.index.value='';f.key.value=nextKey('a'" in _PAGE
    assert "f.reset();f.index.value='';f.key.value=nextKey('ho'" in _PAGE


def test_apply_validation_is_separate_from_save_and_keeps_unsaved_status() -> None:
    from chronospear.world_builder.__main__ import _PAGE

    assert "fetch('/api/validate'" in _PAGE
    assert "fetch('/api/save'" in _PAGE
    assert "world=candidate;dirty();render();reset(item)" in _PAGE
    assert "function dirty(){" in _PAGE
    assert "status.textContent='Unsaved changes'" in _PAGE


def test_gap_aware_suggestion_remains_after_apply_and_delete() -> None:
    world = _world()
    world.identities.append(IdentityDraft("e3", IdentityKind.ENTITY, "Third"))
    del world.identities[1]
    world.associations.append(AssociationDraft("a3", "e1", "IS_A", "d1"))
    world.historical_occurrences.append(
        HistoricalOccurrenceDraft("ho3", ["e1"], "p1", 200, 2, "Later.", "Later.")
    )

    assert world.suggest_key("ENTITY") == "e2"
    assert world.suggest_key("association") == "a2"
    assert world.suggest_key("historical_occurrence") == "ho2"
