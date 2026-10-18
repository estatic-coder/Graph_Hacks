# ASTERION V3 complex synthetic dependency graph

This fixture contains 471 nodes and 1018 directed typed edges across 20 microservices. It is SYNTHETIC, not extracted from real source code.

Files: graph.json, nodes.csv, edges.csv, questions.txt, questions.json, README.md.

## Import
Graph JSON: {"nodes": [{"id", "label", "type", "service", ...}], "edges": [{"source", "target", "type", ...}]}. CSV equivalents have the same identifiers.
Your ASTERION ingestion API may require an adapter; these are neutral interchange formats, not a guaranteed native ASTERION upload schema.

## Relationship direction
A CALLS B means A calls B. A DEPENDS_ON B means A depends on B; impact flows backward from B to its dependents. TESTS means test -> symbol.

## Intentionally planted conditions
- payments -> billing -> payments service dependency cycle
- catalog -> search -> catalog service dependency cycle
- public payment webhook with policy node marked missing_in_fixture (illustrative metadata, not proof of a vulnerability)
- order event queue with two consumers
- service-scoped Postgres and Redis instances

Do not confuse metadata flags with proven runtime vulnerabilities. For queries requiring real code or runtime traces, answer that the fixture alone is insufficient.
