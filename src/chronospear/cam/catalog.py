from __future__ import annotations

from chronospear.cam.identifiers import IdentityId
from chronospear.cam.identity import IdentityNode


class IdentityCatalog:
    """Minimal in-memory Identity Node invariant keeper for Slice 1.

    This is deliberately not a repository abstraction or persistence layer.
    """

    def __init__(self) -> None:
        self._nodes: dict[IdentityId, IdentityNode] = {}

    def add(self, node: IdentityNode) -> IdentityNode:
        existing = self._nodes.get(node.identity_id)
        if existing is None:
            self._nodes[node.identity_id] = node
            return node
        if existing == node:
            return existing
        raise ValueError(f"Identity ID {node.identity_id} is already in use.")

    def get(self, identity_id: IdentityId) -> IdentityNode:
        try:
            return self._nodes[identity_id]
        except KeyError as exc:
            raise KeyError(f"Unknown Identity Node: {identity_id}.") from exc

    def contains(self, identity_id: IdentityId) -> bool:
        return identity_id in self._nodes

    def all(self) -> tuple[IdentityNode, ...]:
        return tuple(self._nodes.values())
