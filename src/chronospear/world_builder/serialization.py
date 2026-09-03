"""Current memory.json serializer for logical World Builder objects."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, cast

from chronospear.world_builder.model import (
    AssociationDraft,
    AuthoringWorld,
    HistoricalOccurrenceDraft,
    IdentityDraft,
)
from chronospear.world_import import parse_memory_document, validate_memory_document


class MemoryJsonSerializer:
    """Load and atomically save the current single-file Memory representation."""

    def load(self, package_directory: Path) -> AuthoringWorld:
        path = package_directory / "memory.json"
        if not path.exists():
            return AuthoringWorld()
        try:
            with path.open(encoding="utf-8") as source:
                raw = cast(object, json.load(source))
        except json.JSONDecodeError as exc:
            raise ValueError(f"memory.json is malformed JSON: {exc}") from exc
        return self.from_document(raw)

    def from_document(self, raw: object) -> AuthoringWorld:
        parsed = parse_memory_document(raw)
        return AuthoringWorld(
            identities=[IdentityDraft(**record) for record in parsed["identities"]],
            associations=[AssociationDraft(**record) for record in parsed["associations"]],
            historical_occurrences=[
                HistoricalOccurrenceDraft(
                    key=record["key"],
                    participants=list(record["participants"]),
                    place=record["place"],
                    world_time=record["world_time"],
                    system_time=record["system_time"],
                    synopsis=record["synopsis"],
                    story=record["story"],
                    started_associations=list(record["started_associations"]),
                    ended_associations=list(record["ended_associations"]),
                )
                for record in parsed["historical_occurrences"]
            ],
        )

    def to_document(self, world: AuthoringWorld) -> dict[str, Any]:
        return {
            "identities": [
                {
                    "key": item.key,
                    "kind": item.kind.value,
                    "name": item.name,
                    "synopsis": item.synopsis,
                    "description": item.description,
                }
                for item in world.identities
            ],
            "associations": [
                {
                    "key": item.key,
                    "source": item.source,
                    "relationship": item.relationship,
                    "target": item.target,
                }
                for item in world.associations
            ],
            "historical_occurrences": [
                {
                    "key": item.key,
                    "participants": item.participants,
                    "place": item.place,
                    "world_time": item.world_time,
                    "system_time": item.system_time,
                    "synopsis": item.synopsis,
                    "story": item.story,
                    "started_associations": item.started_associations,
                    "ended_associations": item.ended_associations,
                }
                for item in world.historical_occurrences
            ],
        }

    def save(self, package_directory: Path, world: AuthoringWorld) -> None:
        document = self.to_document(world)
        validate_memory_document(document)
        package_directory.mkdir(parents=True, exist_ok=True)
        destination = package_directory / "memory.json"
        temporary_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=package_directory,
                prefix=".memory-",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_name = temporary.name
                json.dump(document, temporary, indent=2)
                temporary.write("\n")
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_name, destination)
        except OSError:
            if temporary_name is not None:
                Path(temporary_name).unlink(missing_ok=True)
            raise
