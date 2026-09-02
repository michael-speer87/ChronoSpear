from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from chronospear.cam import (
    Association,
    AssociationCatalog,
    AssociationId,
    IdentityCatalog,
    IdentityId,
    IdentityKind,
    IdentityNode,
    RelationshipType,
    RelationshipVocabulary,
)
from chronospear.experiments.cam_llm import ContextMetrics, ExperimentLimits
from chronospear.experiments.groq_natural_provider import GroqNaturalLanguageProvider
from chronospear.experiments.natural_language_cam import (
    NaturalExperimentReport,
    NaturalLanguageProvider,
    NaturalLanguageResolver,
    NaturalResolution,
    run_natural_language_experiment,
)

EXPERIMENT_3_ACTION = (
    "Nera must deliver a sealed dispatch directly to Archivist Sol. "
    "Which city should Nera travel to?"
)


def _metrics(records: tuple[str, ...]) -> ContextMetrics:
    rendered = "\n".join(records)
    return ContextMetrics(len(records), len(rendered), len(rendered.encode("utf-8")))


def _identity_record(node: IdentityNode) -> str:
    return f"{node.kind} | {node.name} | {node.description}"


@dataclass(frozen=True, slots=True)
class WorldAssociation:
    association: Association
    source_name: str
    target_name: str

    @property
    def record(self) -> str:
        return f"{self.source_name} --{self.association.relationship}--> {self.target_name}"


@dataclass(frozen=True, slots=True)
class RelevanceWorld:
    identities: tuple[IdentityNode, ...]
    associations: tuple[WorldAssociation, ...]


@dataclass(frozen=True, slots=True)
class FixtureMetrics:
    identity_nodes: int
    associations: int
    evidence_records: int


@dataclass(frozen=True, slots=True)
class RelevanceLimits:
    max_initial_records: int = 2
    max_initial_utf8_bytes: int = 1_000
    max_expansion_candidates: int = 8
    max_expansion_records: int = 2

    def __post_init__(self) -> None:
        for name in (
            "max_initial_records",
            "max_initial_utf8_bytes",
            "max_expansion_candidates",
            "max_expansion_records",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer.")


@dataclass(frozen=True, slots=True)
class InitialRecallTelemetry:
    action_anchors: tuple[str, ...]
    semantic_families_considered: tuple[str, ...]
    candidate_records_examined: int
    selected_records: tuple[str, ...]
    records_selected: int
    records_rejected: int
    packet: ContextMetrics


@dataclass(frozen=True, slots=True)
class ExpansionTelemetry:
    raw_context_request: str
    language_surface_activations: tuple[str, ...]
    cam_targets: tuple[str, ...]
    candidate_records_examined: int
    records_returned: tuple[str, ...]
    records_rejected: int
    duplicate_records_suppressed: int
    expansion: ContextMetrics


@dataclass(frozen=True, slots=True)
class RelevanceScenario:
    world: RelevanceWorld
    fixture_metrics: FixtureMetrics
    initial_recall: InitialRecallTelemetry
    initial_evidence: tuple[str, ...]
    resolver: RelevanceExpansionResolver
    limits: RelevanceLimits


@dataclass(frozen=True, slots=True)
class RelevanceExperimentReport:
    fixture: FixtureMetrics
    initial_recall: InitialRecallTelemetry
    expansions: tuple[ExpansionTelemetry, ...]
    llm: NaturalExperimentReport
    total_cam_candidates_examined: int
    total_cam_records_exposed: int
    exposed_fixture_fraction: float
    total_evidence_bytes_exposed: int


def build_relevance_world() -> RelevanceWorld:
    """Construct the validated synthetic CAM world used only by Experiment 3."""

    nodes = IdentityCatalog()
    next_node_id = 0

    def add_node(
        identity_id: str,
        name: str,
        kind: IdentityKind,
        description: str,
    ) -> IdentityNode:
        nonlocal next_node_id
        del identity_id
        next_node_id += 1
        prefix = {
            IdentityKind.ENTITY: "E",
            IdentityKind.PLACE: "P",
            IdentityKind.DESCRIBER: "D",
        }[kind]
        typed_id = IdentityId(
            f"{prefix}-00000000-0000-4000-8000-{next_node_id:012d}"
        )
        return nodes.add(IdentityNode(typed_id, name, kind, description))

    nera = add_node("nera", "Nera", IdentityKind.ENTITY, "A trusted courier.")
    sol = add_node(
        "archivist_sol",
        "Archivist Sol",
        IdentityKind.ENTITY,
        "A keeper of civic records.",
    )
    lumenport = add_node(
        "lumenport",
        "Lumenport",
        IdentityKind.PLACE,
        "A harbor city known for its beacon towers.",
    )
    stonebridge = add_node(
        "stonebridge",
        "Stonebridge",
        IdentityKind.PLACE,
        "A city beside an old stone crossing.",
    )
    redhaven = add_node(
        "redhaven",
        "Redhaven",
        IdentityKind.PLACE,
        "A walled city with red-roofed markets.",
    )
    willowmere = add_node(
        "willowmere",
        "Willowmere",
        IdentityKind.PLACE,
        "A lakeside city bordered by willow groves.",
    )
    archive = add_node(
        "meridian_archive",
        "Meridian Archive",
        IdentityKind.ENTITY,
        "An institution preserving regional records.",
    )
    compass = add_node(
        "brass_compass",
        "Brass Compass",
        IdentityKind.ENTITY,
        "A well-made navigation instrument.",
    )
    key = add_node(
        "silver_key",
        "Silver Key",
        IdentityKind.ENTITY,
        "A small key made from pale metal.",
    )
    circle = add_node(
        "ashen_circle",
        "Ashen Circle",
        IdentityKind.ENTITY,
        "A private society of antiquarians.",
    )
    guild = add_node(
        "couriers_guild",
        "Couriers Guild",
        IdentityKind.ENTITY,
        "An organization coordinating trusted messengers.",
    )
    north = add_node(
        "northern_reach",
        "Northern Reach",
        IdentityKind.DESCRIBER,
        "A regional classification used by mapmakers.",
    )

    vocabulary = RelationshipVocabulary()
    relationships = {
        name: vocabulary.register(RelationshipType(name))
        for name in ("BASED_IN", "MEMBER_OF", "OPPOSES", "OWNS", "PART_OF")
    }
    catalog = AssociationCatalog(nodes=nodes, vocabulary=vocabulary)
    world_associations: list[WorldAssociation] = []
    next_association_id = 0

    def add_association(
        association_id: str,
        source: IdentityNode,
        relationship: str,
        target: IdentityNode,
    ) -> None:
        nonlocal next_association_id
        del association_id
        next_association_id += 1
        association = catalog.add(
            Association(
                AssociationId(
                    f"A-00000000-0000-4000-8000-{next_association_id:012d}"
                ),
                source.identity_id,
                relationships[relationship],
                target.identity_id,
            )
        )
        world_associations.append(WorldAssociation(association, source.name, target.name))

    # Sol's local neighborhood intentionally contains several irrelevant facts.
    add_association("E3-A1", sol, "MEMBER_OF", archive)
    add_association("E3-A2", sol, "OWNS", key)
    add_association("E3-A3", sol, "BASED_IN", redhaven)
    add_association("E3-A4", sol, "OPPOSES", circle)
    add_association("E3-A5", nera, "OWNS", compass)
    add_association("E3-A6", nera, "BASED_IN", stonebridge)
    add_association("E3-A7", nera, "MEMBER_OF", guild)
    add_association("E3-A8", archive, "BASED_IN", lumenport)
    add_association("E3-A9", circle, "BASED_IN", willowmere)
    add_association("E3-A10", guild, "BASED_IN", lumenport)
    add_association("E3-A11", stonebridge, "PART_OF", north)
    add_association("E3-A12", redhaven, "PART_OF", north)

    return RelevanceWorld(nodes.all(), tuple(world_associations))


def _initial_recall(
    world: RelevanceWorld,
    action: str,
    limits: RelevanceLimits,
) -> InitialRecallTelemetry:
    normalized_action = action.casefold()
    anchors: list[str] = []
    selected: list[str] = []
    for node in world.identities:
        if node.name.casefold() not in normalized_action:
            continue
        anchors.append(node.name)
        record = _identity_record(node)
        prospective = _metrics(tuple(selected + [record]))
        if (
            len(selected) < limits.max_initial_records
            and prospective.utf8_bytes <= limits.max_initial_utf8_bytes
        ):
            selected.append(record)
    return InitialRecallTelemetry(
        action_anchors=tuple(anchors),
        semantic_families_considered=("IDENTITY",),
        candidate_records_examined=len(world.identities),
        selected_records=tuple(selected),
        records_selected=len(selected),
        records_rejected=len(world.identities) - len(selected),
        packet=_metrics(tuple(selected)),
    )


class RelevanceExpansionResolver:
    """Language activation followed by bounded, indexed CAM neighborhood retrieval."""

    __slots__ = ("_limits", "_source_index", "_traces")

    def __init__(self, world: RelevanceWorld, limits: RelevanceLimits) -> None:
        index: dict[str, list[WorldAssociation]] = {}
        for association in world.associations:
            index.setdefault(association.source_name.casefold(), []).append(association)
        self._source_index = {key: tuple(value) for key, value in index.items()}
        self._limits = limits
        self._traces: list[ExpansionTelemetry] = []

    @property
    def traces(self) -> tuple[ExpansionTelemetry, ...]:
        return tuple(self._traces)

    def resolve(
        self,
        request: str,
        *,
        seen_evidence: frozenset[str],
        remaining_records: int,
        remaining_utf8_bytes: int,
    ) -> NaturalResolution:
        normalized = request.casefold()
        location_words = (
            "where",
            "located",
            "location",
            "based",
            "whereabouts",
            "resides",
            "city",
            "find",
            "address",
            "stationed",
        )
        equipment_words = ("equipment", "carry", "carries", "owns", "possession")
        activations: list[str] = []
        targets: list[tuple[str, str, str]] = []
        if ("archivist sol" in normalized or " sol" in normalized) and any(
            word in normalized for word in location_words
        ):
            activations.append("Archivist Sol location")
            targets.append(
                (
                    "archivist sol",
                    "BASED_IN",
                    "Identity Archivist Sol / relationship family BASED_IN",
                )
            )
        if "nera" in normalized and any(word in normalized for word in equipment_words):
            activations.append("Nera equipment")
            targets.append(
                ("nera", "OWNS", "Identity Nera / relationship family OWNS")
            )

        candidates: list[WorldAssociation] = []
        for source, _relationship, _label in targets:
            candidates.extend(self._source_index.get(source, ()))
        candidates = candidates[: self._limits.max_expansion_candidates]
        returned: list[str] = []
        duplicates = 0
        for candidate in candidates:
            if not any(
                candidate.source_name.casefold() == source
                and candidate.association.relationship.name == relationship
                for source, relationship, _label in targets
            ):
                continue
            record = candidate.record
            if record in seen_evidence:
                duplicates += 1
                continue
            prospective = _metrics(tuple(returned + [record]))
            record_limit = min(remaining_records, self._limits.max_expansion_records)
            if (
                len(returned) >= record_limit
                or prospective.utf8_bytes > remaining_utf8_bytes
            ):
                continue
            returned.append(record)

        trace = ExpansionTelemetry(
            raw_context_request=request,
            language_surface_activations=tuple(activations),
            cam_targets=tuple(label for _source, _relationship, label in targets),
            candidate_records_examined=len(candidates),
            records_returned=tuple(returned),
            records_rejected=len(candidates) - len(returned),
            duplicate_records_suppressed=duplicates,
            expansion=_metrics(tuple(returned)),
        )
        self._traces.append(trace)
        return NaturalResolution(tuple(activations), tuple(returned))


def prepare_relevance_experiment(
    limits: RelevanceLimits | None = None,
    *,
    world: RelevanceWorld | None = None,
) -> RelevanceScenario:
    active_world = world or build_relevance_world()
    active_limits = limits or RelevanceLimits()
    recall = _initial_recall(active_world, EXPERIMENT_3_ACTION, active_limits)
    fixture = FixtureMetrics(
        identity_nodes=len(active_world.identities),
        associations=len(active_world.associations),
        evidence_records=len(active_world.identities) + len(active_world.associations),
    )
    return RelevanceScenario(
        world=active_world,
        fixture_metrics=fixture,
        initial_recall=recall,
        initial_evidence=recall.selected_records,
        resolver=RelevanceExpansionResolver(active_world, active_limits),
        limits=active_limits,
    )


def run_relevance_experiment(
    *,
    provider: NaturalLanguageProvider,
    world: RelevanceWorld | None = None,
    relevance_limits: RelevanceLimits | None = None,
    experiment_limits: ExperimentLimits | None = None,
) -> RelevanceExperimentReport:
    scenario = prepare_relevance_experiment(relevance_limits, world=world)
    llm = run_natural_language_experiment(
        action=EXPERIMENT_3_ACTION,
        initial_evidence=scenario.initial_evidence,
        resolver=cast(NaturalLanguageResolver, scenario.resolver),
        provider=provider,
        limits=experiment_limits,
    )
    expansion_traces = tuple(
        trace
        for call, trace in zip(llm.calls, scenario.resolver.traces, strict=True)
        if call.interpretation != "conclusion"
    )
    exposed_records = list(scenario.initial_evidence)
    for trace in expansion_traces:
        for record in trace.records_returned:
            if record not in exposed_records:
                exposed_records.append(record)
    total_exposed = len(exposed_records)
    return RelevanceExperimentReport(
        fixture=scenario.fixture_metrics,
        initial_recall=scenario.initial_recall,
        expansions=expansion_traces,
        llm=llm,
        total_cam_candidates_examined=(
            scenario.initial_recall.candidate_records_examined
            + sum(trace.candidate_records_examined for trace in expansion_traces)
        ),
        total_cam_records_exposed=total_exposed,
        exposed_fixture_fraction=total_exposed / scenario.fixture_metrics.evidence_records,
        total_evidence_bytes_exposed=_metrics(tuple(exposed_records)).utf8_bytes,
    )


def run_live_relevance_experiment() -> RelevanceExperimentReport:
    return run_relevance_experiment(provider=GroqNaturalLanguageProvider())
