"""Bounded two-file import experiment for human-authored CAM worlds."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, TypedDict, cast

from chronospear.cam import (
    Association,
    AssociationCatalog,
    AssociationId,
    ChronoStamp,
    HistoricalOccurrence,
    IdentityCatalog,
    IdentityId,
    IdentityKind,
    IdentityNode,
    OccurrenceCatalog,
    OccurrenceId,
    RelationshipVocabulary,
    SystemTime,
    WorldTime,
)


class WorldImportError(ValueError):
    """The world package cannot be reconciled into valid CAM."""


class IdentityMemory(TypedDict):
    key: str
    kind: IdentityKind
    name: str
    synopsis: str
    description: str


class AssociationMemory(TypedDict):
    key: str
    source: str
    relationship: str
    target: str


class OccurrenceMemory(TypedDict):
    key: str
    participants: tuple[str, ...]
    place: str
    world_time: int
    system_time: int
    synopsis: str
    story: str
    started_associations: tuple[str, ...]
    ended_associations: tuple[str, ...]


class ParsedMemory(TypedDict):
    identities: list[IdentityMemory]
    associations: list[AssociationMemory]
    historical_occurrences: list[OccurrenceMemory]


class CatalogIdentity(TypedDict):
    kind: str
    id: str


class PackageCatalog(TypedDict):
    identities: dict[str, CatalogIdentity]
    associations: dict[str, str]
    historical_occurrences: dict[str, str]


@dataclass(frozen=True, slots=True)
class ImportedWorld:
    identities: IdentityCatalog
    associations: AssociationCatalog
    occurrences: OccurrenceCatalog


def import_world(package_directory: str | Path) -> ImportedWorld:
    """Import ``memory.json``, reconcile identity, then atomically save its Catalog."""

    package = Path(package_directory)
    memory_path = package / "memory.json"
    catalog_path = package / "catalog.json"
    memory = _parse_memory(_read_json(memory_path, "Memory"))
    catalog = _read_catalog(catalog_path)
    _reconcile(memory, catalog)
    try:
        world = _build_world(memory, catalog)
    except (KeyError, TypeError, ValueError) as exc:
        raise WorldImportError(f"Memory could not construct valid CAM: {exc}") from exc
    _write_catalog(catalog_path, catalog)
    return world


def _read_json(path: Path, label: str) -> object:
    try:
        with path.open(encoding="utf-8") as source:
            return cast(object, json.load(source))
    except FileNotFoundError as exc:
        raise WorldImportError(f"{label} file does not exist: {path}.") from exc
    except json.JSONDecodeError as exc:
        raise WorldImportError(f"{label} file is malformed JSON: {path}.") from exc
    except OSError as exc:
        raise WorldImportError(f"Could not read {label} file: {path}.") from exc


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise WorldImportError(f"{label} must be a JSON object.")
    return cast(dict[str, Any], value)


def _list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise WorldImportError(f"{label} must be a JSON array.")
    return cast(list[object], value)


def _string(record: dict[str, Any], field: str, label: str) -> str:
    value = record.get(field)
    if not isinstance(value, str):
        raise WorldImportError(f"{label}.{field} must be a string.")
    return value


def _optional_string(
    record: dict[str, Any], field: str, label: str, default: str = ""
) -> str:
    if field not in record:
        return default
    return _string(record, field, label)


def _integer(record: dict[str, Any], field: str, label: str) -> int:
    value = record.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise WorldImportError(f"{label}.{field} must be an integer.")
    return value


def _string_tuple(record: dict[str, Any], field: str, label: str) -> tuple[str, ...]:
    values = _list(record.get(field), f"{label}.{field}")
    if any(not isinstance(value, str) for value in values):
        raise WorldImportError(f"{label}.{field} must contain only strings.")
    return tuple(cast(list[str], values))


def _records(root: dict[str, Any], field: str) -> list[dict[str, Any]]:
    values = _list(root.get(field), f"Memory.{field}")
    return [_object(value, f"Memory.{field}[{index}]") for index, value in enumerate(values)]


def _parse_memory(raw: object) -> ParsedMemory:
    root = _object(raw, "Memory")
    identities: list[IdentityMemory] = []
    associations: list[AssociationMemory] = []
    occurrences: list[OccurrenceMemory] = []

    for index, record in enumerate(_records(root, "identities")):
        label = f"Memory.identities[{index}]"
        kind_text = _string(record, "kind", label)
        try:
            kind = IdentityKind(kind_text)
        except ValueError as exc:
            raise WorldImportError(f"{label}.kind is not a valid Identity kind.") from exc
        identities.append(
            {
                "key": _package_key(record, label),
                "kind": kind,
                "name": _string(record, "name", label),
                "synopsis": _optional_string(record, "synopsis", label),
                "description": _string(record, "description", label),
            }
        )

    vocabulary = RelationshipVocabulary.core()
    for index, record in enumerate(_records(root, "associations")):
        label = f"Memory.associations[{index}]"
        relationship = _string(record, "relationship", label)
        try:
            vocabulary.require(relationship)
        except KeyError as exc:
            raise WorldImportError(
                f"{label}.relationship is not in the controlled vocabulary."
            ) from exc
        associations.append(
            {
                "key": _package_key(record, label),
                "source": _string(record, "source", label),
                "relationship": relationship,
                "target": _string(record, "target", label),
            }
        )

    for index, record in enumerate(_records(root, "historical_occurrences")):
        label = f"Memory.historical_occurrences[{index}]"
        occurrences.append(
            {
                "key": _package_key(record, label),
                "participants": _string_tuple(record, "participants", label),
                "place": _string(record, "place", label),
                "world_time": _integer(record, "world_time", label),
                "system_time": _integer(record, "system_time", label),
                "synopsis": _string(record, "synopsis", label),
                "story": _string(record, "story", label),
                "started_associations": _string_tuple(
                    record, "started_associations", label
                ),
                "ended_associations": _string_tuple(
                    record, "ended_associations", label
                ),
            }
        )

    memory: ParsedMemory = {
        "identities": identities,
        "associations": associations,
        "historical_occurrences": occurrences,
    }
    _validate_memory_references(memory)
    return memory


def _package_key(record: dict[str, Any], label: str) -> str:
    key = _string(record, "key", label)
    if not key or key != key.strip():
        raise WorldImportError(
            f"{label}.key cannot be empty or have surrounding whitespace."
        )
    return key


def _unique_keys(records: list[dict[str, Any]], label: str) -> set[str]:
    keys = [cast(str, record["key"]) for record in records]
    if len(keys) != len(set(keys)):
        raise WorldImportError(f"{label} package keys must be unique.")
    return set(keys)


def _validate_memory_references(memory: ParsedMemory) -> None:
    identity_keys = _unique_keys(cast(list[dict[str, Any]], memory["identities"]), "Identity")
    association_keys = _unique_keys(
        cast(list[dict[str, Any]], memory["associations"]), "Association"
    )
    _unique_keys(
        cast(list[dict[str, Any]], memory["historical_occurrences"]),
        "Historical Occurrence",
    )
    for association in memory["associations"]:
        for field in ("source", "target"):
            if association[field] not in identity_keys:
                raise WorldImportError(
                    f"Association {association['key']!r} has unknown {field} "
                    f"Identity key {association[field]!r}."
                )
    for occurrence in memory["historical_occurrences"]:
        for participant in occurrence["participants"]:
            if participant not in identity_keys:
                raise WorldImportError(
                    f"Historical Occurrence {occurrence['key']!r} has unknown "
                    f"participant Identity key {participant!r}."
                )
        if occurrence["place"] not in identity_keys:
            raise WorldImportError(
                f"Historical Occurrence {occurrence['key']!r} has unknown place "
                f"Identity key {occurrence['place']!r}."
            )
        lifecycle_references = (
            ("started_associations", occurrence["started_associations"]),
            ("ended_associations", occurrence["ended_associations"]),
        )
        for field, references in lifecycle_references:
            for association_key in references:
                if association_key not in association_keys:
                    raise WorldImportError(
                        f"Historical Occurrence {occurrence['key']!r} has unknown "
                        f"{field} key {association_key!r}."
                    )


def _empty_catalog() -> PackageCatalog:
    return {"identities": {}, "associations": {}, "historical_occurrences": {}}


def _read_catalog(path: Path) -> PackageCatalog:
    if not path.exists():
        return _empty_catalog()
    root = _object(_read_json(path, "Catalog"), "Catalog")
    identities_raw = _object(root.get("identities"), "Catalog.identities")
    associations_raw = _object(root.get("associations"), "Catalog.associations")
    occurrences_raw = _object(
        root.get("historical_occurrences"), "Catalog.historical_occurrences"
    )
    identities: dict[str, CatalogIdentity] = {}
    associations: dict[str, str] = {}
    occurrences: dict[str, str] = {}
    canonical_ids: set[str] = set()

    for key, raw_entry in identities_raw.items():
        _validate_catalog_key(key)
        entry = _object(raw_entry, f"Catalog identity {key!r}")
        kind_text = _string(entry, "kind", f"Catalog identity {key!r}")
        try:
            kind = IdentityKind(kind_text)
            identity_id = IdentityId(_string(entry, "id", f"Catalog identity {key!r}"))
            IdentityNode(identity_id=identity_id, name="", kind=kind)
        except (TypeError, ValueError) as exc:
            raise WorldImportError(f"Catalog identity {key!r} is invalid: {exc}") from exc
        identities[key] = {"kind": kind.value, "id": str(identity_id)}
        _claim_id(str(identity_id), canonical_ids)

    for key, raw_id in associations_raw.items():
        _validate_catalog_key(key)
        if not isinstance(raw_id, str):
            raise WorldImportError(f"Catalog Association {key!r} ID must be a string.")
        try:
            association_id = AssociationId(raw_id)
        except ValueError as exc:
            raise WorldImportError(f"Catalog Association {key!r} is invalid: {exc}") from exc
        associations[key] = str(association_id)
        _claim_id(str(association_id), canonical_ids)

    for key, raw_id in occurrences_raw.items():
        _validate_catalog_key(key)
        if not isinstance(raw_id, str):
            raise WorldImportError(
                f"Catalog Historical Occurrence {key!r} ID must be a string."
            )
        try:
            occurrence_id = OccurrenceId(raw_id)
        except ValueError as exc:
            raise WorldImportError(
                f"Catalog Historical Occurrence {key!r} is invalid: {exc}"
            ) from exc
        occurrences[key] = str(occurrence_id)
        _claim_id(str(occurrence_id), canonical_ids)
    return {
        "identities": identities,
        "associations": associations,
        "historical_occurrences": occurrences,
    }


def _claim_id(identifier: str, claimed: set[str]) -> None:
    if identifier in claimed:
        raise WorldImportError(f"Catalog canonical ID {identifier} has conflicting mappings.")
    claimed.add(identifier)


def _validate_catalog_key(key: str) -> None:
    if not key or key != key.strip():
        raise WorldImportError(
            "Catalog package keys cannot be empty or have surrounding whitespace."
        )


def _reconcile(memory: ParsedMemory, catalog: PackageCatalog) -> None:
    family_keys = {
        "identities": set(catalog["identities"]),
        "associations": set(catalog["associations"]),
        "historical_occurrences": set(catalog["historical_occurrences"]),
    }
    for family, keys in family_keys.items():
        for other_family, other_keys in family_keys.items():
            if family < other_family and keys & other_keys:
                key = next(iter(keys & other_keys))
                raise WorldImportError(
                    f"Catalog package key {key!r} conflicts across object families."
                )

    prefixes: dict[IdentityKind, Literal["E", "P", "D"]] = {
        IdentityKind.ENTITY: "E",
        IdentityKind.PLACE: "P",
        IdentityKind.DESCRIBER: "D",
    }
    for identity_record in memory["identities"]:
        key, kind = identity_record["key"], identity_record["kind"]
        _reject_other_family(key, "identities", family_keys)
        existing = catalog["identities"].get(key)
        if existing is not None:
            if existing["kind"] != kind.value:
                raise WorldImportError(
                    f"Identity key {key!r} changed kind from {existing['kind']} to {kind.value}."
                )
        else:
            catalog["identities"][key] = {
                "kind": kind.value,
                "id": str(IdentityId.new(prefixes[kind])),
            }
            family_keys["identities"].add(key)
    for association_record in memory["associations"]:
        key = association_record["key"]
        _reject_other_family(key, "associations", family_keys)
        if key not in catalog["associations"]:
            catalog["associations"][key] = str(AssociationId.new())
            family_keys["associations"].add(key)
    for occurrence_record in memory["historical_occurrences"]:
        key = occurrence_record["key"]
        _reject_other_family(key, "historical_occurrences", family_keys)
        if key not in catalog["historical_occurrences"]:
            catalog["historical_occurrences"][key] = str(OccurrenceId.new())
            family_keys["historical_occurrences"].add(key)


def _reject_other_family(
    key: str, family: str, family_keys: dict[str, set[str]]
) -> None:
    if any(key in keys for name, keys in family_keys.items() if name != family):
        raise WorldImportError(
            f"Package key {key!r} conflicts with its cataloged object family."
        )


def _build_world(memory: ParsedMemory, catalog: PackageCatalog) -> ImportedWorld:
    nodes = IdentityCatalog()
    for identity_record in memory["identities"]:
        entry = catalog["identities"][identity_record["key"]]
        nodes.add(
            IdentityNode(
                identity_id=IdentityId(entry["id"]),
                name=identity_record["name"],
                kind=identity_record["kind"],
                description=identity_record["description"],
                synopsis=identity_record["synopsis"],
            )
        )

    vocabulary = RelationshipVocabulary.core()
    associations = AssociationCatalog(nodes=nodes, vocabulary=vocabulary)
    for association_record in memory["associations"]:
        added = associations.add(
            Association(
                association_id=AssociationId(
                    catalog["associations"][association_record["key"]]
                ),
                source=IdentityId(
                    catalog["identities"][association_record["source"]]["id"]
                ),
                relationship=vocabulary.require(association_record["relationship"]),
                target=IdentityId(
                    catalog["identities"][association_record["target"]]["id"]
                ),
            )
        )
        expected_id = catalog["associations"][association_record["key"]]
        if str(added.association_id) != expected_id:
            raise WorldImportError(
                f"Association {association_record['key']!r} duplicates another "
                "semantic assertion."
            )

    occurrences = OccurrenceCatalog(nodes=nodes, associations=associations)
    for occurrence_record in memory["historical_occurrences"]:
        occurrences.add(
            HistoricalOccurrence(
                occurrence_id=OccurrenceId(
                    catalog["historical_occurrences"][occurrence_record["key"]]
                ),
                stamp=ChronoStamp(
                    WorldTime(occurrence_record["world_time"]),
                    SystemTime(occurrence_record["system_time"]),
                ),
                synopsis=occurrence_record["synopsis"],
                story=occurrence_record["story"],
                participants=tuple(
                    IdentityId(catalog["identities"][key]["id"])
                    for key in occurrence_record["participants"]
                ),
                place=IdentityId(
                    catalog["identities"][occurrence_record["place"]]["id"]
                ),
                started_associations=tuple(
                    AssociationId(catalog["associations"][key])
                    for key in occurrence_record["started_associations"]
                ),
                ended_associations=tuple(
                    AssociationId(catalog["associations"][key])
                    for key in occurrence_record["ended_associations"]
                ),
            )
        )
    return ImportedWorld(nodes, associations, occurrences)


def _write_catalog(path: Path, catalog: PackageCatalog) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, prefix=".catalog-", suffix=".tmp", delete=False
        ) as destination:
            temporary_name = destination.name
            json.dump(catalog, destination, indent=2)
            destination.write("\n")
            destination.flush()
            os.fsync(destination.fileno())
        os.replace(temporary_name, path)
    except OSError as exc:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)
        raise WorldImportError(f"Could not atomically write Catalog: {path}.") from exc
