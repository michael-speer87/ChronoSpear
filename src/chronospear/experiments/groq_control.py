from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from chronospear.cam import (
    Association,
    AssociationCatalog,
    AssociationId,
    IdentityCatalog,
    IdentityKind,
    IdentityNode,
    NodeId,
    RelationshipType,
    RelationshipVocabulary,
)
from chronospear.experiments.cam_llm import (
    EvidenceBundle,
    ExperimentReport,
    WhitelistExpansionResolver,
    run_action_experiment,
)
from chronospear.experiments.groq_natural_provider import GroqNaturalLanguageProvider
from chronospear.experiments.groq_provider import GroqProvider
from chronospear.experiments.natural_language_cam import (
    NaturalExperimentReport,
    NaturalLanguageResolver,
    run_natural_language_experiment,
)


@dataclass(frozen=True, slots=True)
class ControlScenario:
    action: str
    initial_evidence: EvidenceBundle
    resolver: WhitelistExpansionResolver
    expansion_selectors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class NaturalControlScenario:
    action: str
    initial_evidence: tuple[str, ...]
    resolver: NaturalLanguageResolver


def _node_record(node: IdentityNode) -> str:
    return f"NODE {node.node_id} | {node.kind} | {node.name} | {node.description}"


def _association_record(association: Association) -> str:
    return (
        f"ASSOC {association.association_id} | {association.source} "
        f"--{association.relationship}--> {association.target}"
    )


def build_control_scenario() -> ControlScenario:
    """Build a sufficient initial context plus valid, irrelevant expansions."""

    nodes = IdentityCatalog()
    nera = nodes.add(
        IdentityNode(NodeId("nera"), "Nera", IdentityKind.ENTITY, "A trusted courier.")
    )
    sol = nodes.add(
        IdentityNode(
            NodeId("archivist_sol"),
            "Archivist Sol",
            IdentityKind.ENTITY,
            "A keeper of civic records.",
        )
    )
    lumenport = nodes.add(
        IdentityNode(
            NodeId("lumenport"),
            "Lumenport",
            IdentityKind.PLACE,
            "A harbor city known for its beacon towers.",
        )
    )
    stonebridge = nodes.add(
        IdentityNode(
            NodeId("stonebridge"),
            "Stonebridge",
            IdentityKind.PLACE,
            "A mountain town built around an old crossing.",
        )
    )
    compass = nodes.add(
        IdentityNode(
            NodeId("brass_compass"),
            "Brass Compass",
            IdentityKind.ENTITY,
            "A well-made navigation instrument.",
        )
    )

    vocabulary = RelationshipVocabulary()
    based_in = vocabulary.register(RelationshipType("BASED_IN"))
    owns = vocabulary.register(RelationshipType("OWNS"))
    associations = AssociationCatalog(nodes=nodes, vocabulary=vocabulary)
    sol_base = associations.add(
        Association(AssociationId("A1"), sol.node_id, based_in, lumenport.node_id)
    )
    nera_compass = associations.add(
        Association(AssociationId("A2"), nera.node_id, owns, compass.node_id)
    )

    initial = EvidenceBundle(
        "control-initial",
        (
            _node_record(nera),
            _node_record(sol),
            _node_record(lumenport),
            _association_record(sol_base),
        ),
    )
    irrelevant_place = EvidenceBundle(
        "node:stonebridge",
        (_node_record(stonebridge),),
    )
    irrelevant_possession = EvidenceBundle(
        "association:A2",
        (_node_record(compass), _association_record(nera_compass)),
    )
    selectors = (irrelevant_place.bundle_id, irrelevant_possession.bundle_id)
    return ControlScenario(
        action=(
            "Nera must deliver a sealed dispatch directly to Archivist Sol. "
            "Which city should Nera travel to?"
        ),
        initial_evidence=initial,
        resolver=WhitelistExpansionResolver(
            {
                irrelevant_place.bundle_id: irrelevant_place,
                irrelevant_possession.bundle_id: irrelevant_possession,
            }
        ),
        expansion_selectors=selectors,
    )


def build_expansion_control_scenario() -> NaturalControlScenario:
    """Build Experiment 2 with one necessary fact behind a whitelist selector."""

    baseline = build_control_scenario()
    return NaturalControlScenario(
        action=baseline.action,
        initial_evidence=baseline.initial_evidence.records[:-1],
        resolver=NaturalLanguageResolver(
            location_evidence=("Archivist Sol --BASED_IN--> Lumenport",),
            equipment_evidence=("Nera --OWNS--> Brass Compass",),
        ),
    )


def build_decoy_expansion_control_scenario() -> NaturalControlScenario:
    """Build Experiment 2B by adding neutral Place candidates to 2A."""

    experiment_two_a = build_expansion_control_scenario()
    decoy_places = (
        "NODE stonebridge | PLACE | Stonebridge | A city beside an old stone crossing.",
        "NODE redhaven | PLACE | Redhaven | A walled city with red-roofed markets.",
        "NODE willowmere | PLACE | Willowmere | A lakeside city bordered by willow groves.",
    )
    return NaturalControlScenario(
        action=experiment_two_a.action,
        initial_evidence=experiment_two_a.initial_evidence + decoy_places,
        resolver=experiment_two_a.resolver,
    )


def build_redhaven_replication_scenario() -> NaturalControlScenario:
    """Build Experiment 2C with reordered Places and a Redhaven hidden answer."""

    experiment_two_a = build_expansion_control_scenario()
    nera, archivist_sol, lumenport = experiment_two_a.initial_evidence
    reordered_places = (
        "NODE willowmere | PLACE | Willowmere | A lakeside city bordered by willow groves.",
        lumenport,
        "NODE redhaven | PLACE | Redhaven | A walled city with red-roofed markets.",
        "NODE stonebridge | PLACE | Stonebridge | A city beside an old stone crossing.",
    )
    return NaturalControlScenario(
        action=experiment_two_a.action,
        initial_evidence=(nera, archivist_sol) + reordered_places,
        resolver=NaturalLanguageResolver(
            location_evidence=("Archivist Sol --BASED_IN--> Redhaven",),
            equipment_evidence=("Nera --OWNS--> Brass Compass",),
        ),
    )


def run_live_control() -> ExperimentReport:
    scenario = build_control_scenario()
    provider = GroqProvider(expansion_selectors=scenario.expansion_selectors)
    return run_action_experiment(
        scenario.action,
        scenario.initial_evidence,
        scenario.resolver,
        provider,
    )


def run_live_expansion_control() -> NaturalExperimentReport:
    scenario = build_expansion_control_scenario()
    return run_natural_language_experiment(
        action=scenario.action,
        initial_evidence=scenario.initial_evidence,
        resolver=scenario.resolver,
        provider=GroqNaturalLanguageProvider(),
    )


def run_live_decoy_expansion_control() -> NaturalExperimentReport:
    scenario = build_decoy_expansion_control_scenario()
    return run_natural_language_experiment(
        action=scenario.action,
        initial_evidence=scenario.initial_evidence,
        resolver=scenario.resolver,
        provider=GroqNaturalLanguageProvider(),
    )


def run_live_redhaven_replication() -> NaturalExperimentReport:
    scenario = build_redhaven_replication_scenario()
    return run_natural_language_experiment(
        action=scenario.action,
        initial_evidence=scenario.initial_evidence,
        resolver=scenario.resolver,
        provider=GroqNaturalLanguageProvider(),
    )


def main() -> None:
    print(json.dumps(asdict(run_live_control()), indent=2))


if __name__ == "__main__":
    main()
