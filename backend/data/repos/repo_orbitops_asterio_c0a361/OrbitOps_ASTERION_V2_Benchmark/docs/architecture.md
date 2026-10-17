# OrbitOps Architecture Notes
The public API exposes create/approve/reject/run/reopen/get operations.
The list `PENDING` is an in-process queue, not a durable broker. A worker is driven by explicit `run_agent_once()` calls.
Pager calls happen only in worker delivery, after queue consumption.
There is no automatic scheduler or background worker in the benchmark package.
This document is contextual, not a replacement for verifying executable code.
