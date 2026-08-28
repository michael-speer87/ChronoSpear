from __future__ import annotations

from dataclasses import dataclass

from chronospear.cam.catalog import IdentityCatalog
from chronospear.cam.identifiers import AssociationId, NodeId
from chronospear.cam.relationships import RelationshipType, RelationshipVocabulary


@dataclass(frozen=True, slots=True)
class Association:
    """An addressable directed semantic assertion between Identity Nodes.

    Association is not a generic graph edge and is not an Identity Node. Lifecycle,
    historical support, perspective knowledge, and cleanup policy are deliberately
    outside Slice 1.
    """

    association_id: AssociationId
    source: NodeId
    relationship: RelationshipType
    target: NodeId

    @property
    def semantic_key(self) -> tuple[NodeId, str, NodeId]:
        return (self.source, self.relationship.name, self.target)


class AssociationCatalog:
    """Minimal in-memory invariant keeper for Slice 1 Associations.

    This is not production persistence and performs no graph traversal. Its purpose
    is only to prove primitive invariants: endpoints exist, relationship semantics
    are approved, IDs are unique, and the same semantic assertion is not silently
    duplicated.
    """

    def __init__(
        self,
        *,
        nodes: IdentityCatalog,
        vocabulary: RelationshipVocabulary,
    ) -> None:
        self._nodes = nodes
        self._vocabulary = vocabulary
        self._by_id: dict[AssociationId, Association] = {}
        self._by_semantic_key: dict[tuple[NodeId, str, NodeId], AssociationId] = {}

    def add(self, association: Association) -> Association:
        if not self._nodes.contains(association.source):
            raise KeyError(f"Unknown source Node: {association.source}.")
        if not self._nodes.contains(association.target):
            raise KeyError(f"Unknown target Node: {association.target}.")
        if not self._vocabulary.contains(association.relationship):
            raise ValueError(
                f"Relationship Type {association.relationship.name!r} is not approved."
            )

        existing_by_id = self._by_id.get(association.association_id)
        if existing_by_id is not None:
            if existing_by_id == association:
                return existing_by_id
            raise ValueError(
                f"Association ID {association.association_id} is already in use."
            )

        existing_id = self._by_semantic_key.get(association.semantic_key)
        if existing_id is not None:
            return self._by_id[existing_id]

        self._by_id[association.association_id] = association
        self._by_semantic_key[association.semantic_key] = association.association_id
        return association

    def get(self, association_id: AssociationId) -> Association:
        try:
            return self._by_id[association_id]
        except KeyError as exc:
            raise KeyError(f"Unknown Association: {association_id}.") from exc

    def all(self) -> tuple[Association, ...]:
        return tuple(self._by_id.values())
