# ASTERION Architecture

## Data Flow
Repository → Parser → Extracted entities and relationships → FalkorDB → Graph retrieval and traversal → Evidence-backed agent response → UI.

## Components
- **FalkorDB**: Primary knowledge graph and relationship store. Serves as the central source of truth.
- **Backend (FastAPI)**: Orchestrates data ingestion, provides graph queries, runs the AI agent.
- **Frontend (React)**: Graph workspace and investigation UI.
- **Ingestion**: Parses source files and extracts symbols/relationships.

## Rules
- FalkorDB is the primary knowledge graph and relationship store.
- AI must not fabricate dependencies, source locations, test coverage, or evidence.
- Extracted relationships and inferred relationships must be distinguished.
