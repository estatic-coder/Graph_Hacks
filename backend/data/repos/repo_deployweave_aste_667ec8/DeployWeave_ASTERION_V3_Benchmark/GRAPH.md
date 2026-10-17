# DeployWeave conceptual graph (EVALUATOR REFERENCE: do not index)

```mermaid
flowchart TD
  CREATE[create_rollout] --> SUBMIT[submit]
  SUBMIT --> POLICY{classify / dependencies_healthy}
  POLICY -->|sandbox| MUTED[muted, unsaved]
  POLICY -->|missing dependency| BLOCKED[blocked, saved]
  POLICY -->|critical or production| REVIEW[review, saved]
  POLICY -->|ready| ACQUIRE[acquire slot]
  ACQUIRE -->|no slot| NOSLOT[no_slot, unsaved]
  ACQUIRE -->|slot acquired| QUEUE[(READY queue)]
  APPROVE[approve_rollout] --> APPROVER[approve]
  APPROVER --> ACQUIRE2[acquire slot]
  ACQUIRE2 --> QUEUE
  RETRY[retry_rollout] --> REOPEN[retry_rollback]
  REOPEN --> ACQUIRE3[acquire slot]
  ACQUIRE3 --> QUEUE
  QUEUE -. state/queue handoff .-> POLL[poll_once]
  RUN[run_worker_once] --> POLL
  POLL --> EXEC[execute]
  EXEC --> INSTALL[install version]
  INSTALL --> PROBE[probe health]
  PROBE -->|good| COMMIT[commit slot, deployed]
  PROBE -->|bad, retries remain| PROBE
  PROBE -->|exhausted| RESTORE[restore version]
  RESTORE --> REFUND[refund slot, rolled_back]
  LEDGER[ledger] --> AUTH[auth]
  LEDGER --> GATEWAY[gateway]
  AUTH --> GATEWAY
```

The QUEUE connection is **not** a synchronous CALLS edge. The three service links indicate dependency impact, not function calls.
