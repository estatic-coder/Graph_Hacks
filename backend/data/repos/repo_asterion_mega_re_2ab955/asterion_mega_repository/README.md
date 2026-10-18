# Asterion Mega Repository (synthetic source-code fixture)

This is a real Python source tree, not a JSON graph import. It contains 24 service packages, 288 service modules, 24 test modules, and 2304 top-level operation functions, plus classes/methods and import/call relationships.

## Ingest
Extract the ZIP and point Asterion's **repository ingestion** to the extracted `asterion_mega_repository` directory. Do not upload `graph.json` as a repository. The web UI may require a local path or Git URL; if it only accepts Git URLs, initialize a Git repository in this extracted directory and provide its accessible URL.

## Notes
- This fixture is intentionally synthetic and stresses graph size, cycles, transitive dependencies and cross-package imports.
- Some operation functions form recursive cycles. **Do not execute the operation functions**; index them statically.
- See QUESTIONS.md for 20 evaluation questions.
- Node/edge counts shown in the UI depend on which symbol and relationship types Asterion indexes.
- The graph should not be expected to show exactly one node per source symbol unless Asterion is configured for that.
