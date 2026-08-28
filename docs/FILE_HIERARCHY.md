# Slice 1 File Hierarchy

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
│   └── SLICE_1_CONTRACT.md
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
│           ├── relationships.py
│           └── time.py
└── tests/
    ├── test_public_api.py
    └── cam/
        ├── test_associations.py
        ├── test_identifiers.py
        ├── test_identity.py
        ├── test_relationships.py
        └── test_time.py
```

Do not create empty future-package scaffolding. Future slices add directories only when their responsibility is defined.
