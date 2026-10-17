# AegisOps ASTERION Evaluation Questions

Ask these in ASTERION after importing and indexing this repository. Expected results below are a manual ground truth for checking the agent. **Do not feed these answers into the agent's repository ingestion** if you want a blind evaluation; omit this file from indexing or use it only after testing.

## Q1: Complete multi-hop path
**Ask:** Trace the function call path from `ingest_alert()` to `isolate_host()`. Which conditions must be true for isolation to occur? Show source file and line evidence.
**Expected:** `ingest_alert -> process_event -> open_incident -> execute_response -> isolate_host`. The event must classify as critical; `execute_response` requires critical priority, non-trusted host, and `AUTO_ISOLATE=True`. `classify_event` requires severity >= threshold and suspicious kind, except trusted hosts become review. Mention branch conditions.

## Q2: Impact analysis
**Ask:** If `classify_event()` incorrectly labels all malware as `ignore`, which functions, incident records, notifications, remediation actions, audit logs, and tests could be affected? Separate operations that are skipped from operations still executed.
**Expected:** `process_event` gets `ignore`, calls `record_audit('ignored', host)` and returns `None`. It does not call `open_incident`, so `save_incident`, `notify_security_team`, `execute_response`, `notify_operations`, and incident creation audit are skipped. Tests in `test_rules.py`, `test_pipeline.py`, and `test_api.py` can be affected. `normalize_event` still runs before classification.

## Q3: Trusted-host control flow
**Ask:** A critical-severity malware event arrives from `core-db`. Will AegisOps isolate it? Trace the exact reason and list which notifications occur.
**Expected:** No. `core-db` is trusted, so `classify_event` returns `review` before the critical branch. `open_incident` saves incident, sends security notification, sets manual_review, does not call `execute_response`, and does not notify operations. It writes incident_created audit.

## Q4: Branch order
**Ask:** For a benign `cpu_spike` event with severity 9, which operations run, and which operations are skipped?
**Expected:** `normalize_event` and `classify_event` run, then `record_audit('ignored', host)`. No incident, notifications, or remediation.

## Q5: Test discovery
**Ask:** Which tests directly verify `classify_event()` and which test its effects indirectly through `process_event()` or `ingest_alert()`? Show graph paths.
**Expected:** Direct: four tests in `tests/test_rules.py`. Indirect: five tests in `tests/test_pipeline.py` and `test_ingest_and_list` in `tests/test_api.py`. `test_release` does not exercise classification.

## Q6: Remediation switch impact
**Ask:** If `AUTO_ISOLATE` is set to False, what changes in critical-incident processing, and which actions still happen?
**Expected:** Critical incidents still saved, security and operations notifications sent, incident_created audit recorded; `execute_response` returns awaiting_approval before `isolate_host` and isolated audit. `process_event` still runs normally.

## Q7: Recovery path
**Ask:** Trace the call path from `release_host()` to the audit log. Does releasing a host delete its incident record?
**Expected:** `release_host -> restore_host`, then if success `record_audit('restored', host)`. `restore_host` removes host from BLOCKED_HOSTS; it does not remove entries in INCIDENTS.

## Q8: Repository graph reasoning
**Ask:** What are the shortest call paths from `ingest_alert()` to `notify_operations()` and from `ingest_alert()` to `record_audit()`? Explain why shortest graph paths alone do not prove execution for every input.
**Expected:** `ingest_alert -> process_event -> open_incident -> notify_operations`; `ingest_alert -> process_event -> record_audit` is a short path for ignored events, while other audit paths exist. Branch predicates determine execution.

## Q9: Cross-module impact
**Ask:** If `save_incident()` fails before returning, what downstream operations inside `open_incident()` are prevented? Which tests are most relevant?
**Expected:** Notifications, remediation, and incident_created audit are not reached when an exception interrupts `open_incident` at save_incident. Tests in pipeline and API cover related flows but do not directly test this injected failure; recommend a new failure test.

## Q10: Evidence honesty
**Ask:** Which function sends a Slack message to the on-call engineer, and what is its exact line number?
**Expected:** No Slack integration exists. `notify_security_team` only appends a string to in-memory `MESSAGES`. Agent must not invent a Slack function, network call, or source citation.

## Q11: Memory freshness
**Ask:** Save a verified investigation of the critical alert isolation path, then retrieve it in a new session. After modifying the relevant source file, does ASTERION flag the old finding as potentially stale?
**Expected:** Persistent, repo-scoped investigation and evidence; stale status after source revision changes, if memory freshness is implemented.

## Q12: Repository isolation
**Ask:** In AegisOps, which function authorizes customer card payments?
**Expected:** None. This repository has no payment authorization. A response naming SentinelShop's `authorize_payment` indicates repository cross-contamination.
