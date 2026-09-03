"""Read-only presentation adapter over the existing CAM catalogs."""

from __future__ import annotations

from typing import Literal, TypedDict

from chronospear.cam import Association, HistoricalOccurrence, IdentityNode
from chronospear.playground.model import DemoWorld
from chronospear.world_import import ImportedWorld

ObjectType = Literal["identity", "association", "occurrence"]


class ObjectRef(TypedDict):
    type: ObjectType
    id: str
    label: str


class Detail(TypedDict):
    type: ObjectType
    id: str
    label: str
    fields: list[tuple[str, str]]
    groups: list[tuple[str, list[ObjectRef]]]


class PlaygroundSnapshot(TypedDict):
    objects: dict[ObjectType, list[ObjectRef]]
    details: list[Detail]


class PlaygroundAdapter:
    """Resolve CAM objects and their immediate connections without mutating CAM."""

    def __init__(self, world: DemoWorld | ImportedWorld) -> None:
        self._world = world

    def identity(self, object_id: str) -> Detail:
        node = self._identity(object_id)
        outgoing = [
            self._association_ref(item)
            for item in self._world.associations.all()
            if item.source == node.identity_id
        ]
        incoming = [
            self._association_ref(item)
            for item in self._world.associations.all()
            if item.target == node.identity_id
        ]
        participant_occurrences = [
            self._occurrence_ref(item)
            for item in self._world.occurrences.all()
            if node.identity_id in item.participants
        ]
        place_occurrences = [
            self._occurrence_ref(item)
            for item in self._world.occurrences.all()
            if item.place == node.identity_id
        ]
        return {
            "type": "identity",
            "id": str(node.identity_id),
            "label": node.name,
            "fields": [
                ("IdentityId", str(node.identity_id)),
                ("Name", node.name),
                ("IdentityKind", node.kind.value),
                ("Synopsis", node.synopsis),
                ("Description", node.description),
            ],
            "groups": [
                ("Outgoing Associations", outgoing),
                ("Incoming Associations", incoming),
                ("Participant in History", participant_occurrences),
                ("Place of History", place_occurrences),
            ],
        }

    def association(self, object_id: str) -> Detail:
        association = self._association(object_id)
        source = self._world.identities.get(association.source)
        target = self._world.identities.get(association.target)
        started_by = [
            self._occurrence_ref(item)
            for item in self._world.occurrences.all()
            if association.association_id in item.started_associations
        ]
        ended_by = [
            self._occurrence_ref(item)
            for item in self._world.occurrences.all()
            if association.association_id in item.ended_associations
        ]
        return {
            "type": "association",
            "id": str(association.association_id),
            "label": f"{source.name} — {association.relationship.name} → {target.name}",
            "fields": [
                ("AssociationId", str(association.association_id)),
                ("Relationship Type", association.relationship.name),
            ],
            "groups": [
                ("Source Identity", [self._identity_ref(source)]),
                ("Target Identity", [self._identity_ref(target)]),
                ("Started By", started_by),
                ("Ended By", ended_by),
            ],
        }

    def occurrence(self, object_id: str) -> Detail:
        occurrence = self._occurrence(object_id)
        participants = [
            self._identity_ref(self._world.identities.get(identity_id))
            for identity_id in occurrence.participants
        ]
        place = self._identity_ref(self._world.identities.get(occurrence.place))
        started_associations = [
            self._association_ref(self._world.associations.get(association_id))
            for association_id in occurrence.started_associations
        ]
        ended_associations = [
            self._association_ref(self._world.associations.get(association_id))
            for association_id in occurrence.ended_associations
        ]
        return {
            "type": "occurrence",
            "id": str(occurrence.occurrence_id),
            "label": occurrence.synopsis,
            "fields": [
                ("OccurrenceId", str(occurrence.occurrence_id)),
                ("WorldTime", str(occurrence.stamp.world_time.value)),
                ("SystemTime", str(occurrence.stamp.system_time.value)),
                ("Synopsis", occurrence.synopsis),
                ("Story", occurrence.story),
            ],
            "groups": [
                ("Participants", participants),
                ("Place", [place]),
                ("Started Associations", started_associations),
                ("Ended Associations", ended_associations),
            ],
        }

    def detail(self, object_type: ObjectType, object_id: str) -> Detail:
        if object_type == "identity":
            return self.identity(object_id)
        if object_type == "association":
            return self.association(object_id)
        return self.occurrence(object_id)

    def snapshot(self) -> PlaygroundSnapshot:
        """Return the complete, JSON-ready read model consumed by the browser."""

        identities = [self._identity_ref(item) for item in self._world.identities.all()]
        associations = [
            self._association_ref(item) for item in self._world.associations.all()
        ]
        occurrences = [self._occurrence_ref(item) for item in self._world.occurrences.all()]
        return {
            "objects": {
                "identity": identities,
                "association": associations,
                "occurrence": occurrences,
            },
            "details": [
                *(self.identity(item["id"]) for item in identities),
                *(self.association(item["id"]) for item in associations),
                *(self.occurrence(item["id"]) for item in occurrences),
            ],
        }

    def _identity(self, object_id: str) -> IdentityNode:
        for item in self._world.identities.all():
            if str(item.identity_id) == object_id:
                return item
        raise KeyError(f"Unknown playground Identity: {object_id!r}.")

    def _association(self, object_id: str) -> Association:
        for item in self._world.associations.all():
            if str(item.association_id) == object_id:
                return item
        raise KeyError(f"Unknown playground Association: {object_id!r}.")

    def _occurrence(self, object_id: str) -> HistoricalOccurrence:
        for item in self._world.occurrences.all():
            if str(item.occurrence_id) == object_id:
                return item
        raise KeyError(f"Unknown playground Historical Occurrence: {object_id!r}.")

    def _identity_ref(self, node: IdentityNode) -> ObjectRef:
        return {"type": "identity", "id": str(node.identity_id), "label": node.name}

    def _association_ref(self, association: Association) -> ObjectRef:
        source = self._world.identities.get(association.source)
        target = self._world.identities.get(association.target)
        return {
            "type": "association",
            "id": str(association.association_id),
            "label": f"{source.name} — {association.relationship.name} → {target.name}",
        }

    @staticmethod
    def _occurrence_ref(occurrence: HistoricalOccurrence) -> ObjectRef:
        return {
            "type": "occurrence",
            "id": str(occurrence.occurrence_id),
            "label": occurrence.synopsis,
        }
