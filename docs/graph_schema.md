# ASTERION Graph Schema and FalkorDB Integration

## Graph Isolation
Graphs are isolated by repository. Each repository gets its own FalkorDB graph, named `workspace_{repo_id}`. This ensures strong isolation for queries and impact analysis.

## Node Types
- `Repository`, `Directory`, `File`, `Module`, `Class`, `Function`, `Method`, `Import`, `Endpoint`, `Table`, `Config`, `Test`, `Concept`, `Decision`, `Investigation`, `Finding`, `AgentTask`

## Relationship Types
- `CONTAINS`, `IMPORTS`, `CALLS`, `DEFINES`, `INHERITS`, `IMPLEMENTS`, `READS_FROM`, `WRITES_TO`, `EXPOSES`, `TESTS`, `DOCUMENTS`, `DEPENDS_ON`, `AFFECTS`, `SUPPORTED_BY`, `OBSERVED_IN`, `SUPERSEDES`

## Attributes
- **Nodes**: `id` (stable ID), `repository_id`, `name`, `source_path`, `start_line`, `end_line`, plus arbitrary properties.
- **Relationships**: `source_id`, `target_id`, `type`, `provenance`, `confidence` (float 0.0-1.0), `is_inferred` (boolean), plus arbitrary properties.

## Cypher Limitations in FalkorDB
1. **Shortest Path**: Standard OpenCypher `MATCH p=shortestPath((a)-[*]-(b))` is not natively supported in FalkorDB right now. We work around this by using bounded breadth-first variable length paths: `MATCH p=(a)-[*1..5]-(b) LIMIT 1`. This prevents runaway queries while finding paths.
2. **Upserts**: We use `MERGE` to implement idempotent upserts for both nodes and relationships.

## Security & Reliability
- Queries are strictly parameterized to avoid Cypher injection.
- Traversals have a hard limit on depth (`max_depth = 3`) or limits to bound uncontrolled graph expansion.
- The `FalkorClient` checks health status on startup and tests automatically skip integration suites when the database is unavailable, resorting to unit-mock testing.
