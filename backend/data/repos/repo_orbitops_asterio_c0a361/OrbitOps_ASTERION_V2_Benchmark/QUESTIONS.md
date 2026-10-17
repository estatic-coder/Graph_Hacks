# OrbitOps V2 Benchmark Questions

Index `orbitops/`, `tests/`, `docs/`, `metadata/` only. NEVER index `ANSWER_KEY.md`, `GRAPH.md`, or `QUESTIONS.md`.

Ask ASTERION these questions verbatim. For agent-action questions, require real execution artifacts, not narratives.

1. **[Graph & routing]** Enumerate all static CALLS paths from create_alert(), approve_alert(), and retry_failed_alert() to send_page(). Identify any shared-state handoffs.
2. **[Graph & routing]** Enumerate the complete static CALLS chain starting at run_agent_once() and ending at send_page(). Identify the guard that may prevent reaching send_page().
3. **[Graph & routing]** Which functions enqueue into PENDING, and which function removes an entry? Is there any automatic worker or scheduler?
4. **[Graph & routing]** Find all static callers of hold(), distinguishing submission, approval, and reopening branches.
5. **[State & execution]** After a normal create_alert() returns, give status, BALANCE, HELD, PENDING, ordered EVENTS, pager CALLS, and NOTICES.
6. **[State & execution]** For a security-team alert, trace creation, approval, and one worker iteration. Distinguish distinct API entrypoints, persistence, and queue handoffs.
7. **[State & execution]** For severity 9 with team core, does it reserve credits or enqueue on creation? Why?
8. **[State & execution]** For source synthetic, is the alert saved? What happens when get_alert() is called?
9. **[State & execution]** With MAX_ATTEMPTS=2 and persistent pager timeouts, report pager calls, timeouts, final status, balance, reservation, events, and notices.
10. **[State & execution]** With a single initial timeout and then success, report calls, incident key, events, final balance, reservation, and notices.
11. **[State & execution]** If MAX_ATTEMPTS changes to 4, give maximum pager calls and timeout events for permanent failure, and calls for immediate success.
12. **[State & execution]** After a failure is reopened and the pager recovers, calculate total pager calls, attempt reset, final attempts, events, balance, reservation, and notices.
13. **[State & execution]** Can a failed reopen consume the reopen budget even without enqueue? Explain ordering and next-attempt behavior.
14. **[State & execution]** Compare no_credit on initial submit vs no_credit during authorize vs failed after delivery exhaustion.
15. **[State & execution]** What happens if PENDING contains an alert whose status is no longer pending when drain_one() pops it?
16. **[Impact & tests]** If release() is removed from the exhaustion branch of deliver(), which tests detect it and which merely execute related code? Explain assertion chains.
17. **[Impact & tests]** If commit() is removed on successful delivery, what state leaks and which existing test detects the regression?
18. **[Impact & tests]** What branch outcomes of authorize() have no direct test coverage? Give their precise effects.
19. **[Impact & tests]** If send_page() raises TimeoutError indefinitely, which call sites and callers are involved, and what is the precise failure cleanup order?
20. **[Impact & tests]** Which test proves create_alert() does not synchronously call the pager? Provide its assertion.
21. **[Reliability & architecture]** A worker crashes after PENDING.pop(0) but before deliver(). Describe the loss window and distinguish actual code from hypothetical recovery.
22. **[Reliability & architecture]** Does sweep_holds() run automatically? On normal delivery exhaustion, would it restore any additional credits?
23. **[Reliability & architecture]** Do the indexed files contain evidence of a durable broker, Celery, Kafka, Redis-backed queue, or HTTP paging transport? Scope negative claims.
24. **[Reliability & architecture]** Which team and lead own worker delivery, and which ADR explains security-team manual review? Trace document/metadata evidence.
25. **[Reliability & architecture]** Which owner and ADR are relevant to the destructive queue pop? Explain why this is a risk rather than proof of observed data loss.
26. **[Agent challenge]** Using only the code graph and tests, select the minimum reasonable set of tests to run if deliver() failure cleanup changes. Explain selection and evidence.
27. **[Agent challenge]** Store a verified finding about the queue-loss window. In a new independent session, retrieve it, include provenance and revision, and revalidate it if code changes.
28. **[Agent challenge]** Perform a multi-agent investigation of why an alert is stuck in review. Show a graph investigator, execution analyst, test analyst, and evidence reviewer sharing state and handing off.
29. **[Agent challenge]** Demonstrate that adding or removing a verified dependency edge changes your agent’s graph-driven tool choice or test selection, without changing the user query.
30. **[Agent challenge]** Using a Git diff that removes release() from deliver(), produce a blast-radius graph, select and execute tests in an isolated environment, and clearly distinguish real results from predictions.
