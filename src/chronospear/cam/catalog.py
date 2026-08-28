from __future__ import annotations

from chronospear.cam.identifiers import NodeId
from chronospear.cam.identity import IdentityNode


class IdentityCatalog:
    """Minimal in-memory Identity Node invariant keeper for Slice 1.

    This is deliberately not a repository abstraction or persistence layer.
    """

    def __init__(self) -> None:
        self._nodes: dict[NodeId, IdentityNode] = {}

    def add(self, node: IdentityNode) -> IdentityNode:
        existing = self._nodes.get(node.node_id)
        if existing is None:
            self._nodes[node.node_id] = node
            return node
        if existing == node:
            return existing
        raise ValueError(f"Node ID {node.node_id} is already in use.")

    def get(self, node_id: NodeId) -> IdentityNode:
        try:
            return self._nodes[node_id]
        except KeyError as exc:
            raise KeyError(f"Unknown Identity Node: {node_id}.") from exc

    def contains(self, node_id: NodeId) -> bool:
        return node_id in self._nodes

    def all(self) -> tuple[IdentityNode, ...]:
        return tuple(self._nodes.values())
