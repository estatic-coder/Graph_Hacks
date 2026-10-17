# Evaluator answer key (DO NOT INDEX)
1. No producer API has direct CALLS path to send. Worker: run_worker_once -> poll_once -> dispatch -> send; queue and saved-state handoffs.
2. queued, tokens normal 2, reserved i1, queue i1, queued event, no notices, no send calls.
3. Three calls and three send_timeout events, failed, tokens restored to 3, no reservation, failed notice.
4. Two calls, ticket:i1:2, queued/send_timeout/sent events, tokens 2, reservation consumed.
5. Critical review saved without reservation or queue; approval reserves critical token (2->1), queues; worker sends.
6. Severity 9 routes review, no immediate reservation.
7. Muted emitted but not saved/queued; get raises KeyError.
8. budget_denied emitted, no save/queue/notice, token stays 0.
9. Persistent five calls/five timeouts; immediate success one call/zero timeouts.
10. Persistent failure test detects. Reopen recovery test detects because final token count changes after mutation. Other tests require branch/assertion analysis.
11. Invalid status ValueError; insufficient budget sets no_budget, emits review_budget_denied, saves, no queue. Both untested directly.
12. No release, no token reserved before review rejection.
13. Initial three failures, reopen resets attempts to 0, then one successful call; cumulative calls 4, final attempts 1, tokens 2, reservation empty, sent; events queued, three send_timeout, failed, reopened, sent.
14. Only one reopen allowed; second after renewed failure raises reopen limit reached; if not failed, status check fails first.
15. Count increments before reserve, failed reserve emits reopen_budget_denied and does not enqueue; next attempt hits limit.
16. open_incident, approve, reopen_failed enqueue; poll_once dequeues; no scheduler.
17. No, pop happens but nonqueued incident returned without dispatch.
18. Submission test asserts CALLS empty.
19. RESERVED retains i1 and reservation flag remains true; worker success test asserts not-in RESERVED.
20. None in indexed code; in-memory store/queue only.
21. Initial no_budget unsaved; approval no_budget saved; exhausted failure saved and released with notice.
22. Destructive pop before dispatch creates loss window; no ack/requeue.
23. Six cumulative calls, six timeouts, two failed events, final failed, tokens 3, no reservation.
24. No, critical stays review and queue empty until approval.
