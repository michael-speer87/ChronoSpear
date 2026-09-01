from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from chronospear.cam.identifiers import IdentityId


class IdentityKind(StrEnum):
    """Currently locked Identity Node families.

    This enum is intentionally about Identity Nodes only. Historical Occurrences,
    Amend, Void, Audit, Calendar, and Language objects are separate families and
    must not be added here merely because they are graph-addressable.
    """

    ENTITY = "ENTITY"
    PLACE = "PLACE"
    DESCRIBER = "DESCRIBER"


@dataclass(frozen=True, slots=True)
class IdentityNode:
    """An enduring addressable thing or concept known to CAM.

    Description answers what the identity *is*. Mutable, secret, temporal, or
    perspective-dependent world facts belong in Associations/History, not here.
    That semantic rule is architectural and cannot be completely enforced by a
    Python validator.
    """

    identity_id: IdentityId
    name: str
    kind: IdentityKind
    description: str = ""

    def __post_init__(self) -> None:
        name = self.name.strip()
        if not name:
            raise ValueError("Identity Node name cannot be empty.")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "description", self.description.strip())
