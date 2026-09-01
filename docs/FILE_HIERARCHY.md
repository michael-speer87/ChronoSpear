# Production CAM File Hierarchy Through Slice 2

```text
ChronoSpear/
├── AGENTS.md
├── README.md
├── pyproject.toml
├── .gitignore
├── docs/
│   ├── ARCHITECTURE_BOUNDARIES.md
│   ├── CODEX_NEXT_STEPS.md
│   ├── FILE_HIERARCHY.md
│   ├── GRAPH_OBJECT_TAXONOMY.md
│   ├── SLICE_1_CONTRACT.md
│   ├── SLICE_2_CONTRACT.md
│   └── VALIDATION.md
├── src/
│   └── chronospear/
│       ├── __init__.py
│       ├── py.typed
│       └── cam/
│           ├── __init__.py
│           ├── associations.py
│           ├── catalog.py
│           ├── identifiers.py
│           ├── identity.py
│           ├── occurrences.py
│           ├── relationships.py
│           └── time.py
└── tests/
    ├── test_public_api.py
    └── cam/
        ├── test_associations.py
        ├── test_architecture_guardrails.py
        ├── test_identifiers.py
        ├── test_identity.py
        ├── test_occurrences.py
        ├── test_relationships.py
        └── test_time.py
```

Research experiments live separately under `research/` and are not production CAM authority.

Do not create empty future-package scaffolding. Future slices add files/directories only when their responsibility is defined by an active contract.
