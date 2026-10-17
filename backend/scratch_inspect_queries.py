from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
repo_id = "repo_orbitops_asterio_c0a361"

queries = [
    ("Q1", "Enumerate all static CALLS paths from create_alert(), approve_alert(), and retry_failed_alert() to send_page(). Identify any shared-state handoffs."),
    ("Q5", "After a normal create_alert() returns, give status, BALANCE, HELD, PENDING, ordered EVENTS, pager CALLS, and NOTICES."),
    ("Q6", "For a security-team alert, trace creation, approval, and one worker iteration. Distinguish distinct API entrypoints, persistence, and queue handoffs."),
    ("Q9", "With MAX_ATTEMPTS=2 and persistent pager timeouts, report pager calls, timeouts, final status, balance, reservation, events, and notices."),
    ("Q12", "After a failure is reopened and the pager recovers, calculate total pager calls, attempt reset, final attempts, events, balance, reservation, and notices."),
    ("Q13", "Can a failed reopen consume the reopen budget even without enqueue? Explain ordering and next-attempt behavior."),
    ("Q16", "If release() is removed from the exhaustion branch of deliver(), which tests detect it and which merely execute related code? Explain assertion chains."),
    ("Q21", "A worker crashes after PENDING.pop(0) but before deliver(). Describe the loss window and distinguish actual code from hypothetical recovery."),
    ("Q27", "Store a verified finding about the queue-loss window. In a new independent session, retrieve it, include provenance and revision, and revalidate it if code changes."),
    ("Q28", "Perform a multi-agent investigation of why an alert is stuck in review. Show a graph investigator, execution analyst, test analyst, and evidence reviewer sharing state and handing off."),
    ("Q30", "Using a Git diff that removes release() from deliver(), produce a blast-radius graph, select and execute tests in an isolated environment, and clearly distinguish real results from predictions."),
    ("Combined", "After a failure is reopened and the pager recovers, calculate total pager calls, attempt reset, final attempts, events, balance, reservation, and notices. AND If release() is removed from the exhaustion branch of deliver(), which tests detect it and which merely execute related code? Explain assertion chains.")
]

for name, q in queries:
    res = client.post("/api/investigate", json={"repo_id": repo_id, "query": q})
    data = res.json()
    ver = data["verification"]
    is_v = ver["is_verified"]
    summary = ver.get("summary", "")
    print(f"[{name}] is_verified={is_v}")
    if not is_v:
        print(f"   Summary: {summary}")
        if ver.get("fabricated_paths"):
            print(f"   Fab Paths: {ver.get('fabricated_paths')}")
        if ver.get("fabricated_citations"):
            print(f"   Fab Cits: {ver.get('fabricated_citations')}")
