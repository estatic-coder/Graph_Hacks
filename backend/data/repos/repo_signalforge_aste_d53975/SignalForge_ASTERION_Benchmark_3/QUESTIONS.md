# SignalForge Benchmark Questions (DO NOT INDEX)

1. Enumerate static CALLS paths from create_incident(), approve_incident(), and reopen_incident() to send(). Which transitions require shared state or queue handoffs?
2. After normal create_incident() returns, has send() run? Give status, tokens, RESERVED, QUEUE, EVENTS and NOTICES.
3. With MAX_SEND_RETRIES=2 and persistent timeout, how many send calls and timeout events occur? Give final status, tokens, reservation and notices.
4. If send() times out once and then succeeds, give calls, ticket, ordered events, final tokens and reservation.
5. Trace a critical-team incident through creation, approval and worker polling. Distinguish static calls, persistence and queue handoffs.
6. Does a normal-team severity-9 incident bypass review or reserve a token immediately?
7. For service sandbox, is the incident saved or queued? What does get_incident() do?
8. With normal tokens zero at creation, what is emitted, saved, queued or notified?
9. Change MAX_SEND_RETRIES from 2 to 4. Give maximum calls/timeouts under persistent failure and calls on first-attempt success.
10. Remove release() from exhausted dispatch(). Which tests actually detect the regression? Separate branch execution from assertion detection.
11. Which approve() failure branches lack direct test coverage? Explain invalid status and insufficient budget effects.
12. Does rejecting a review incident restore a token? Explain.
13. After failed incident reopening and transport recovery, give attempts, cumulative send calls, tokens, reservation, status and complete events.
14. What happens if a failed incident is reopened twice? Explain MAX_REOPEN.
15. Can a failed reserve() in reopen_failed() consume reopening budget without enqueueing? What happens next?
16. Identify all QUEUE producers and consumers. Is there an automatic scheduler?
17. If QUEUE holds an incident no longer queued, does poll_once() call dispatch()?
18. Which tests prove creation does not synchronously call send()?
19. If consume() is removed from successful dispatch(), which state leaks and which tests detect it?
20. Is Kafka, Redis, Celery, HTTP integration or durable database present? Scope negative evidence.
21. Compare no_budget on creation, no_budget on approval, and failed after retry exhaustion: persistence, events, notices and tokens.
22. If worker crashes after QUEUE.pop(0) before dispatch(), can queue entry be lost? Is recovery implemented?
23. If a reopened incident exhausts retries again, give cumulative send calls, timeout events, final state and tokens.
24. Can a critical-team incident reach send() via only create_incident() and run_worker_once(), without approve_incident()?
