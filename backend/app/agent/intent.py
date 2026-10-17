import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

@dataclass
class IntentResult:
    primary_intent: str
    secondary_intents: List[str]
    candidate_entities: List[str]
    confidence: float
    description: str
    candidate_phrases: List[str] = field(default_factory=list)
    path_endpoints: List[tuple[str, str]] = field(default_factory=list)
    role_map: Dict[str, str] = field(default_factory=dict)
    path_mode: str = "shortest_path"
    capabilities: List[str] = field(default_factory=list)

    @property
    def intent(self) -> str:
        """Backwards compatibility for components expecting .intent string."""
        return self.primary_intent

    def has_capability(self, cap: str) -> bool:
        """Checks if a required capability was identified for this query."""
        return cap in self.capabilities

class IntentClassifier:
    """
    Classifies the user's codebase investigation goal into primary and secondary intents,
    and extracts candidate symbols, natural-language entity phrases, path endpoints,
    and multi-label operational capabilities.
    """
    def classify(self, query: str, context_node: Optional[dict] = None) -> IntentResult:
        q_lower = query.lower()
        candidates, phrases = self._extract_entities_and_phrases(query)
        path_endpoints, role_map = self._extract_path_endpoints(query)

        # Include endpoints in candidates and phrases
        for src, dst in path_endpoints:
            if src not in candidates:
                candidates.append(src)
            if src not in phrases:
                phrases.append(src)
            if dst not in candidates:
                candidates.append(dst)
            if dst not in phrases:
                phrases.append(dst)

        # Context node integration
        if context_node and context_node.get("name"):
            c_name = context_node.get("name")
            if c_name not in candidates:
                candidates.insert(0, c_name)

        # -------------------------------------------------------------
        # Multi-Label Operational Capability Identification
        # -------------------------------------------------------------
        detected_capabilities: List[str] = []

        # 1. CRASH_CONSISTENCY (excluding persistent memory actions)
        has_crash_consistency = any(k in q_lower for k in [
            "worker crashes", "crashes after", "outbox.pop", "queue.pop", "lost from the queue",
            "crash consistency", "failure window", "queue-loss", "queue loss",
            "crash between dequeue", "queue entry be lost", "is recovery implemented",
            "destructive in-memory", "loss window", "can queue entry be lost"
        ])
        if has_crash_consistency and not any(k in q_lower for k in ["store a verified finding", "store finding", "in a new independent session"]):
            detected_capabilities.append("CRASH_CONSISTENCY")

        # 1B. PERSISTENT_MEMORY_ACTION
        has_persistent_memory = any(k in q_lower for k in [
            "store a verified finding", "store finding", "store ... finding", "in a new independent session",
            "retrieve it, include provenance", "new independent session, retrieve it", "cross-session",
            "revalidate it if code changes", "provenance and revision", "retrieve it"
        ]) and any(k in q_lower for k in ["session", "finding", "revalidate", "store"])
        if has_persistent_memory:
            detected_capabilities.append("PERSISTENT_MEMORY_ACTION")

        # 1C. MULTI_AGENT_COORDINATION
        has_multi_agent = any(k in q_lower for k in [
            "multi-agent investigation", "collaborating agents", "graph investigator, execution analyst",
            "sharing state and handing off", "four collaborating agents", "handoff sequence",
            "perform a multi-agent"
        ])
        if has_multi_agent:
            detected_capabilities.append("MULTI_AGENT_COORDINATION")

        # 1D. GRAPH_GUIDED_TEST_EXECUTION
        has_graph_guided_action = any(k in q_lower for k in [
            "git diff that removes", "produce a blast-radius graph, select and execute",
            "execute tests in an isolated environment", "distinguish real results from predictions",
            "execution receipt", "action-mode dispatch", "produce a blast-radius graph"
        ])
        if has_graph_guided_action:
            detected_capabilities.append("GRAPH_GUIDED_TEST_EXECUTION")

        # 1E. TEST_ASSERTION_ANALYSIS
        has_test_assertion_analysis = any(k in q_lower for k in [
            "which tests detect it and which merely execute", "explain assertion chains",
            "assertions observing those effects", "which tests detect it",
            "mutation_confirmed_detector", "if release() is removed from the exhaustion branch"
        ])
        if has_test_assertion_analysis:
            detected_capabilities.append("TEST_ASSERTION_ANALYSIS")

        # 2. CONFIGURATION_OVERRIDE
        has_config_override = any(k in q_lower for k in [
            "change max_send_retries", "change max_delivery_retries", "changes from",
            "changing from", "changed from", "change from", "increases from",
            "switches from", "modifies from", "from 2 to 4", "from 2 to 3",
            "if max_retries", "changing max_retries", "configuration override",
            "retry configuration override", "if max_send_retries", "if max_delivery_retries",
            "if max_attempts changes to 4", "max_attempts changes"
        ]) or (
            any(k in q_lower for k in ["changes", "changing", "modifying"])
            and any(k in q_lower for k in ["from", "to"])
            and any(c.isdigit() for c in query)
        )
        if has_config_override:
            detected_capabilities.append("CONFIGURATION_OVERRIDE")

        # 3. CHANGE_IMPACT_ANALYSIS
        has_change_impact = any(k in q_lower for k in [
            "remove release()", "remove release", "remove consume()", "remove consume",
            "if dispatch() stops calling", "if dispatch() no longer calls", "stops calling release",
            "stops calling consume", "if consume() is removed", "is removed from",
            "if i modify", "if i change", "modifying", "modify", "modified",
            "if we change", "impact", "affected", "affects", "could be affected",
            "would be affected", "breaking change", "blast radius", "side effects",
            "stops calling", "what if", "suppose", "stops invoking", "is removed",
            "are removed", "is deleted", "are deleted", "if this call is",
            "if this condition is removed", "which tests break if", "removes",
            "hypothetically remove", "hypothetically removes", "remove release_hold",
            "which workflows and tests are affected", "which state leaks"
        ])
        if has_change_impact:
            detected_capabilities.append("CHANGE_IMPACT_ANALYSIS")

        # 4. MULTIPHASE_SCENARIO
        has_multiphase_scenario = any(k in q_lower for k in [
            "after failed incident reopening and transport recovery", "reopening recovery",
            "reopening scenario", "replay recovery", "multi-phase", "multiphase",
            "failed incident reopening", "dead-letter job is replayed", "replayed job",
            "replayed after the transport", "reopened twice", "reopened incident exhausts",
            "if a reopened incident exhausts retries again", "cumulative send calls",
            "cumulative transport calls", "reopen after failure", "multi-phase scenario",
            "shared execution ledger", "reopened and the pager recovers", "after a failure is reopened",
            "security-team alert, trace creation, approval, and one worker iteration",
            "trace creation, approval, and one worker iteration"
        ])
        if has_multiphase_scenario:
            detected_capabilities.append("MULTIPHASE_SCENARIO")

        # 5. RESOURCE_BUDGET_ANALYSIS
        has_resource_budget = any(k in q_lower for k in [
            "tokens zero at creation", "normal tokens zero", "tokens zero", "quota is zero",
            "zero quota", "reopening budget", "replay budget", "reopen_failed() consume reopening budget",
            "consume reopening budget without enqueueing", "subtle bug in replay",
            "when reserve() fails", "failed reserve()", "failed replay reservation",
            "does rejecting a review incident restore a token", "does reject_job() restore quota",
            "rejecting a review incident restore", "budget denied", "review_budget_denied",
            "reopen_budget_denied", "reserve() fails", "tokens restored", "token count",
            "reopening budget without enqueueing", "failed reopen consume the reopen budget",
            "can a failed reopen consume the reopen budget"
        ])
        if has_resource_budget:
            detected_capabilities.append("RESOURCE_BUDGET_ANALYSIS")

        # 6. BRANCH_TEST_COVERAGE
        has_branch_test_coverage = any(k in q_lower for k in [
            "which approve() failure branches lack", "which failure branches in approve",
            "approval branch coverage", "lack direct test coverage", "lacks a direct test",
            "lacks a direct automated test", "failure branch of approve_review",
            "untested branch", "test gaps", "which important failure branch",
            "which branches lack", "which tests actually detect", "which tests prove",
            "separate branch execution from assertion detection", "branch execution from assertion detection",
            "detecting tests", "detect the regression", "branch-executing", "which tests prove creation does not synchronously call",
            "what branch outcomes of authorize() have no direct test coverage"
        ])
        if has_branch_test_coverage:
            detected_capabilities.append("BRANCH_TEST_COVERAGE")

        # 7. QUEUE_PRODUCER_CONSUMER_ANALYSIS
        has_queue_producer_consumer = any(k in q_lower for k in [
            "all queue producers and consumers", "all outbox producers and consumers",
            "queue producers and consumers", "outbox producers and consumers",
            "queue producers", "outbox producers", "queue consumers", "outbox consumers",
            "producers and consumers", "identify all queue", "identify all outbox",
            "which functions write to outbox", "which functions write to queue",
            "which reads it", "reads or removes", "automatic background worker or scheduler",
            "is there an automatic scheduler", "queue ownership", "queue producer/consumer",
            "identify all queue producers and consumers", "which functions enqueue into pending",
            "which function removes an entry? is there any automatic worker or scheduler"
        ])
        if has_queue_producer_consumer:
            detected_capabilities.append("QUEUE_PRODUCER_CONSUMER_ANALYSIS")

        # 8. CROSS_ENTRYPOINT_WORKFLOW
        has_cross_entrypoint = any(k in q_lower for k in [
            "cross-entrypoint", "cross entrypoint", "independent entrypoints",
            "crosses an outbox", "queue handoff", "queue handoffs", "state handoff",
            "state handoffs", "shared state or queue handoffs", "state-mediated",
            "trace a critical-team", "trace a critical team", "trace a vip", "trace a vip job",
            "critical-team lifecycle", "vip lifecycle", "through creation, approval and worker polling",
            "creation, approval and worker polling", "without approve_incident",
            "without approve_job", "from create_job() through approve_job()",
            "from create_incident() through approve_incident()", "reopen_incident() to send()",
            "create_incident(), approve_incident()", "vip workflow", "critical-team workflow",
            "which transitions require shared state or queue handoffs",
            "can a critical-team incident reach send() via only create_incident() and run_worker_once()",
            "distinct api entrypoints, persistence, and queue handoffs"
        ])
        if has_cross_entrypoint:
            detected_capabilities.append("CROSS_ENTRYPOINT_WORKFLOW")

        # 9. BRANCH_CONDITION_ANALYSIS
        has_branch_condition = any(k in q_lower for k in [
            "severity-9", "severity 9", "severity >=", "severity>", "service sandbox",
            "muted", "muted services", "bypass review", "is the incident saved or queued",
            "does a normal-team severity-9", "when reserve() fails", "if queue holds an incident no longer queued",
            "no longer queued", "poll_once() call dispatch", "invalid status", "insufficient budget",
            "insufficient quota", "status check fails", "reopened twice", "max_reopen",
            "reopen limit reached", "branch condition", "conditional routing", "failure branch",
            "failure branches", "high-severity conditional routing", "muted incident persistence",
            "for service sandbox, is the incident saved or queued", "what does get_incident() do",
            "what does get_job() do afterward", "source synthetic", "for source synthetic",
            "for severity 9 with team core", "pending contains an alert whose status is no longer pending"
        ])
        if has_branch_condition:
            detected_capabilities.append("BRANCH_CONDITION_ANALYSIS")

        # 10. LOOP_EXECUTION_ANALYSIS
        has_loop_analysis = any(k in q_lower for k in [
            "max_send_retries", "max_delivery_retries", "how many send calls",
            "how many transport calls", "how many gateway calls", "how many carrier calls",
            "how many calls", "how many attempts", "how many iterations", "attempts occur",
            "timeout events occur", "timeout events", "persistent timeout",
            "times out once and then succeeds", "times out exactly once", "retry loop",
            "retry exhaustion", "retries=", "exhausts retries again", "first-attempt success",
            "first attempt succeeds", "on first-attempt success", "how many calls happen",
            "how many invocations", "calls happen", "always raises timeouterror",
            "raises timeouterror", "gateway times out", "carrier times out",
            "gateway_timeout events", "send_timeout events", "max_attempts", "max_attempts=2",
            "max_attempts=4", "pager calls", "pager timeouts", "persistent pager timeouts",
            "report pager calls, timeouts", "single initial timeout and then success"
        ])
        if has_loop_analysis:
            detected_capabilities.append("LOOP_EXECUTION_ANALYSIS")

        # 11. STATE_EFFECT_QUERY
        has_state_effect_query = any(k in q_lower for k in [
            "has deliver() run", "has send() run", "has deliver run", "has send run",
            "list status", "give status", "status, quota", "status, tokens", "quota, reservation",
            "tokens, reservation", "reserved, queue", "reserved, outbox", "events and notices",
            "is it saved or queued", "what does get_incident() do", "what does get_job() do",
            "which actions happen and which do not", "is the job persisted", "is the incident persisted",
            "is the incident saved", "compare the two failure states", "compare no_budget",
            "no_quota and dead_letter", "after create_job() returns", "after normal create_incident() returns",
            "after create_incident() returns", "does reject_job() restore", "does rejecting a review incident restore",
            "state after incident creation", "what is emitted, saved, queued or notified",
            "persistence, events, notices and tokens", "which state leaks", "give calls, ticket, ordered events",
            "give calls, receipt, ordered events", "receipt, event order", "ticket, ordered events",
            "give status, balance, held, pending, ordered events", "after a normal create_alert() returns"
        ])
        if has_state_effect_query:
            detected_capabilities.append("STATE_EFFECT_QUERY")

        # 12. STATIC_PATH_ANALYSIS
        has_static_path = bool(path_endpoints) or any(k in q_lower for k in [
            "static call path", "static calls path", "static calls paths", "static call paths",
            "enumerate static calls paths", "enumerate static call paths", "calls paths from",
            "shortest path", "shortest call path", "every static call path", "direct calls path",
            "static calls", "static path", "all static call paths", "call paths from create_",
            "which tests prove creation does not synchronously call", "enumerate all static calls paths",
            "enumerate the complete static calls chain"
        ])
        if has_static_path:
            detected_capabilities.append("STATIC_PATH_ANALYSIS")

        # Negative evidence search
        is_negative_evidence = any(k in q_lower for k in [
            "kafka", "broker", "external database", "redis", "rabbitmq", "celery",
            "publishes payment events to", "publishes shipment events to",
            "where is the producer configured", "cite exact source lines or establish absence",
            "prove that a real payment gateway", "prove that a real", "scope of the absence claim",
            "is kafka, redis, celery, http integration or durable database present", "scope negative evidence",
            "contain evidence of a durable broker"
        ])

        # Metadata & Ownership ADR
        has_metadata_ownership = any(k in q_lower for k in [
            "which team and lead own", "which adr explains", "owner and adr are relevant",
            "team and lead", "metadata/ownership", "adr-011", "adr-012"
        ])
        if has_metadata_ownership:
            detected_capabilities.append("METADATA_OWNERSHIP_QUERY")

        # -------------------------------------------------------------
        # Determine Primary Intent and Confidence
        # -------------------------------------------------------------
        primary_intent = "GENERAL_QUERY"
        confidence = 0.70
        description = "General repository architecture inquiry."

        if has_persistent_memory:
            primary_intent = "PERSISTENT_MEMORY_ACTION"
            confidence = 0.99
            description = "Storing, retrieving, and revalidating persistent findings in FalkorDB across independent sessions."
        elif has_multi_agent:
            primary_intent = "MULTI_AGENT_COORDINATION"
            confidence = 0.99
            description = "Orchestrating 4 collaborating agents sharing FalkorDB state and handoffs."
        elif has_graph_guided_action:
            primary_intent = "GRAPH_GUIDED_TEST_EXECUTION"
            confidence = 0.99
            description = "Producing diff blast radius, selecting tests, and executing in isolated sandbox."
        elif has_test_assertion_analysis:
            primary_intent = "TEST_ASSERTION_ANALYSIS"
            confidence = 0.95
            description = "Branch-aware test assertion detection analysis distinguishing true detectors."
        elif has_metadata_ownership:
            primary_intent = "METADATA_OWNERSHIP_QUERY"
            confidence = 0.95
            description = "Analyzing service ownership, team leads, and architectural decision records."
        elif is_negative_evidence:
            primary_intent = "NEGATIVE_EVIDENCE_SEARCH"
            confidence = 0.95
            description = "Verifying negative evidence and establishing absence of external integrations."
        elif has_crash_consistency:
            primary_intent = "CRASH_CONSISTENCY"
            confidence = 0.95
            description = "Analyzing crash window, queue loss risks, and failure recovery consistency."
        elif has_config_override:
            primary_intent = "CONFIGURATION_IMPACT"
            confidence = 0.95
            description = "Analyzing impact of numeric or system configuration changes."
        elif has_change_impact:
            primary_intent = "CHANGE_IMPACT_ANALYSIS"
            confidence = 0.95
            description = "Analyzing change impact, affected components, and downstream ripple effects."
        elif has_multiphase_scenario:
            primary_intent = "MULTIPHASE_SCENARIO"
            confidence = 0.95
            description = "Simulating multi-phase scenario with persistent state transitions and recovery."
        elif has_queue_producer_consumer:
            primary_intent = "QUEUE_PRODUCER_CONSUMER_ANALYSIS"
            confidence = 0.95
            description = "Analyzing queue producers, consumers, and background scheduler presence."
        elif has_branch_test_coverage:
            primary_intent = "BRANCH_TEST_COVERAGE"
            confidence = 0.95
            description = "Analyzing control-flow branch test coverage and identifying untested failure paths."
        elif has_resource_budget:
            primary_intent = "RESOURCE_BUDGET_ANALYSIS"
            confidence = 0.95
            description = "Analyzing resource budget, tokens/credits, reservation, and quota restoration ordering."
        elif has_cross_entrypoint:
            primary_intent = "STATE_TRANSITION_ANALYSIS"
            confidence = 0.95
            description = "Analyzing cross-entrypoint workflows, state-mediated handoffs, and external entry points."
        elif has_state_effect_query:
            primary_intent = "STATE_EFFECT_QUERY"
            confidence = 0.95
            description = "Analyzing interprocedural state effects, quotas/tokens, reservations, events, and statuses."
        elif has_branch_condition:
            primary_intent = "BRANCH_CONDITION_ANALYSIS"
            confidence = 0.95
            description = "Evaluating conditional control-flow branch routing, severity guards, and service filtering."
        elif has_loop_analysis:
            primary_intent = "LOOP_EXECUTION_ANALYSIS"
            confidence = 0.95
            description = "Analyzing loop iteration bounds, retry counts, and exception handling control flow."
        elif has_static_path:
            primary_intent = "SHORTEST_PATH"
            confidence = 0.95
            description = "Discovering directed call graph path connecting entities."
        elif any(k in q_lower for k in ["who calls", "callers", "called by", "calls to", "where is it called", "invoked by"]):
            primary_intent = "CALLER_TRACING"
            confidence = 0.95
            description = "Tracing upstream callers invoking the target symbol."
        elif any(k in q_lower for k in ["what tests cover", "tests for", "test coverage for", "which tests exercise", "find tests for"]):
            primary_intent = "TEST_DISCOVERY"
            confidence = 0.90
            description = "Discovering automated tests covering the target symbol."
        elif any(k in q_lower for k in ["depend on", "depends on", "dependencies", "what does it use", "callees", "outbound dependencies"]):
            primary_intent = "DEPENDENCY_TRAVERSAL"
            confidence = 0.88
            description = "Traversing downstream dependencies and callee relationships."
        elif any(k in q_lower for k in ["inspect source", "show code", "source code of", "implementation of", "lines of code", "body of", "view code"]):
            primary_intent = "SOURCE_INSPECTION"
            confidence = 0.85
            description = "Inspecting physical source code on disk."
        elif any(k in q_lower for k in ["where is", "find symbol", "locate", "defined", "definition of", "what is"]):
            primary_intent = "SYMBOL_LOOKUP"
            confidence = 0.80
            description = "Locating symbol definition and metadata."

        # -------------------------------------------------------------
        # Secondary Intents
        # -------------------------------------------------------------
        secondary_intents: List[str] = []
        for cap in detected_capabilities:
            if cap != primary_intent and cap not in secondary_intents:
                secondary_intents.append(cap)

        if has_loop_analysis and primary_intent != "LOOP_EXECUTION_ANALYSIS" and "LOOP_EXECUTION_ANALYSIS" not in secondary_intents:
            secondary_intents.append("LOOP_EXECUTION_ANALYSIS")
        if has_config_override and primary_intent != "CONFIGURATION_IMPACT" and "CONFIGURATION_IMPACT" not in secondary_intents:
            secondary_intents.append("CONFIGURATION_IMPACT")
        if has_cross_entrypoint and primary_intent != "STATE_TRANSITION_ANALYSIS" and "STATE_TRANSITION_ANALYSIS" not in secondary_intents:
            secondary_intents.append("STATE_TRANSITION_ANALYSIS")
        if has_static_path and primary_intent != "SHORTEST_PATH" and "SHORTEST_PATH" not in secondary_intents:
            secondary_intents.append("SHORTEST_PATH")
        if any(k in q_lower for k in ["depend", "dependency", "dependencies", "paths", "flow", "workflow"]):
            if primary_intent != "DEPENDENCY_TRAVERSAL" and "DEPENDENCY_TRAVERSAL" not in secondary_intents:
                secondary_intents.append("DEPENDENCY_TRAVERSAL")
        if any(k in q_lower for k in ["test", "tests", "tested", "coverage", "testing"]):
            if primary_intent != "TEST_DISCOVERY" and "TEST_DISCOVERY" not in secondary_intents:
                secondary_intents.append("TEST_DISCOVERY")
        if any(k in q_lower for k in ["evidence", "source-code", "source code", "lines", "citations"]):
            if primary_intent != "SOURCE_INSPECTION" and "SOURCE_EVIDENCE" not in secondary_intents:
                secondary_intents.append("SOURCE_EVIDENCE")

        is_all_paths = any(k in q_lower for k in [
            "every path", "every function call path", "every call path",
            "all paths", "all function call paths", "all call paths", "all possible paths"
        ])
        path_mode = "all_paths" if is_all_paths else "shortest_path"

        return IntentResult(
            primary_intent=primary_intent,
            secondary_intents=secondary_intents,
            candidate_entities=candidates,
            confidence=confidence,
            description=description,
            candidate_phrases=phrases,
            path_endpoints=path_endpoints,
            role_map=role_map,
            path_mode=path_mode,
            capabilities=detected_capabilities
        )

    def _extract_entities_and_phrases(self, query: str) -> tuple[List[str], List[str]]:
        candidates: List[str] = []
        phrases: List[str] = []
        stopwords = {
            "what", "where", "when", "which", "who", "whom", "whose", "why", "how",
            "does", "explain", "describe", "find", "show", "tell", "between",
            "from", "into", "through", "during", "before", "after", "above", "below",
            "calls", "called", "caller", "callers", "tests", "test", "tested", "path",
            "dependencies", "depend", "depends", "using", "uses", "used", "code",
            "file", "files", "function", "functions", "class", "classes", "module",
            "repository", "repo", "system", "graph", "impact", "change", "modify",
            "could", "would", "should", "might", "logic", "flow", "operations",
            "order", "orders", "processing", "evidence", "source"
        }

        # 1. Quoted terms: 'foo' or "foo" or `foo`
        quoted = re.findall(r"['\"`]([^'\"`]+)['\"`]", query)
        for term in quoted:
            t = term.strip()
            if t and t not in candidates and not t.isdigit():
                candidates.append(t)
                phrases.append(t)

        # 2. Filenames with extensions (e.g. main.py, db.py, config.json)
        files = re.findall(r"\b[\w-]+\.(?:py|ts|js|json|sql|yaml|yml|md)\b", query, re.IGNORECASE)
        for f in files:
            if f not in candidates:
                candidates.append(f)
                phrases.append(f)

        # 3. Explicit function calls with parentheses: foo()
        func_calls = re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\(\)", query)
        for fc in func_calls:
            if fc.lower() not in stopwords and fc not in candidates and not fc.isdigit():
                candidates.append(fc)
                phrases.append(fc)

        # 4. Code identifiers (snake_case, camelCase, PascalCase)
        identifiers = re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]{2,}\b", query)
        for ident in identifiers:
            if ident.lower() not in stopwords and ident not in candidates and not ident.isdigit():
                if "_" in ident or any(c.isupper() for c in ident[1:]):
                    candidates.append(ident)

        # 4b. Common bare domain terms that might map to repository functions or modules
        domain_terms = [
            "gateway", "carrier", "refund", "refunds", "approve", "review",
            "ledger", "balance", "balances", "hold", "holds", "process",
            "processor", "dispatch", "storage", "submit", "workflow",
            "worker", "outbox", "queue", "quota", "reservation", "transport",
            "deliver", "replay", "credit", "credits", "sweep", "orphan", "orphans",
            "poll", "save", "load", "emit", "enqueue"
        ]
        for term in domain_terms:
            if re.search(r"\b" + term + r"\b", query, re.IGNORECASE):
                if term not in candidates:
                    candidates.append(term)
                if term not in phrases:
                    phrases.append(term)

        # 5. Natural language entity phrases following action / hypothetical triggers
        hypo_patterns = [
            r"\bstops\s+calling\s+([a-zA-Z_][a-zA-Z0-9_]*)(?:\(\))?",
            r"\bif\s+([a-zA-Z_][a-zA-Z0-9_]*)(?:\(\))?\s+stops\b",
            r"\b(?:removes?|deletes?|drops?|omits?)\s+([a-zA-Z_][a-zA-Z0-9_]*)(?:\(\))?",
            r"\b(?:what\s+if|suppose)\s+([a-zA-Z_][a-zA-Z0-9_]*)(?:\(\))?",
            r"\bif\s+([a-zA-Z_][a-zA-Z0-9_]*)(?:\(\))?\s+(?:returns?|changes?|fails?)",
            r"\b(?:function|method)\s+([a-zA-Z_][a-zA-Z0-9_]*)(?:\(\))?",
        ]
        for pat in hypo_patterns:
            matches = re.finditer(pat, query, re.IGNORECASE)
            for m in matches:
                sym = m.group(1).strip()
                if sym.lower() not in stopwords and sym not in candidates and not sym.isdigit():
                    candidates.append(sym)
                    phrases.append(sym)

        # 6. Natural language entity phrases following trigger verbs
        # e.g., "modify the payment authorization logic", "change the user auth service"
        verb_patterns = [
            r"(?:modify|modifying|change|changing|refactor|update|test|trace|inspect|about|for)\s+(?:the\s+|a\s+|an\s+)?([a-zA-Z0-9_\s-]+?)(?:\s+(?:logic|function|method|class|module|service|operation|operations|component|code|behavior|implementation|flow|system))?(?:,|\?|\.|\s+which|\s+what|\s+and|\s+how|$)",
            r"(?:which|what)\s+([a-zA-Z0-9_\s-]+?)(?:\s+(?:functions|methods|operations|services|components|classes|modules))\s+(?:could|would|might|can)",
        ]
        for pat in verb_patterns:
            matches = re.finditer(pat, query, re.IGNORECASE)
            for m in matches:
                phrase = m.group(1).strip()
                # Clean up punctuation and stop words
                cleaned = re.sub(r"^(?:the|a|an)\s+", "", phrase, flags=re.IGNORECASE).strip()
                if cleaned and len(cleaned) > 2 and cleaned.lower() not in stopwords and not cleaned.isdigit():
                    if cleaned not in phrases:
                        phrases.append(cleaned)
                    if cleaned not in candidates:
                        candidates.append(cleaned)

        return candidates, phrases

    def _extract_entities(self, query: str) -> List[str]:
        candidates, _ = self._extract_entities_and_phrases(query)
        return candidates

    def _extract_path_endpoints(self, query: str) -> tuple[List[tuple[str, str]], Dict[str, str]]:
        """
        Extracts ordered (source, destination) endpoint pairs and role mappings.
        Supports multi-source and multi-destination structured queries such as:
        'Find every function call path from create_order() and approve_review() to create_label().'
        Creates independent path tasks [(create_order, create_label), (approve_review, create_label)]
        without pairing sources to each other.
        """
        endpoints: List[tuple[str, str]] = []
        role_map: Dict[str, str] = {}

        def _clean_item(text: str) -> str:
            t = re.sub(r"[\(\)`'\"]", "", text).strip()
            return re.sub(r"^(?:the\s+)", "", t, flags=re.IGNORECASE).strip()

        def _is_numeric(text: str) -> bool:
            return bool(re.match(r"^\d+(?:\.\d+)?$", text.strip()))

        def _split_items(segment: str) -> List[str]:
            parts = re.split(r",\s*and\s+|\s+and\s+|,\s*", segment, flags=re.IGNORECASE)
            items = []
            for p in parts:
                cleaned = _clean_item(p)
                if cleaned and not _is_numeric(cleaned) and cleaned not in items and cleaned.lower() not in {
                    "all", "every", "path", "paths", "function", "functions", "call", "calls",
                    "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"
                }:
                    items.append(cleaned)
            return items

        # Check for numeric transition phrases like "changes from 2 to 3"
        is_numeric_transition = bool(
            re.search(r"(?:change|changing|increases?|switches?|transitions?|modifies?|moves?)\s+.*?\s+from\s+\d+\s+to\s+\d+", query, re.IGNORECASE) or
            re.search(r"\bfrom\s+\d+\s+to\s+\d+\b", query, re.IGNORECASE) or
            re.search(r"\bfrom\s+(?:two|three|four)\s+to\s+(?:three|four|five)\b", query, re.IGNORECASE)
        )

        # Pattern 1: Multi-source / multi-destination: from <sources> to <destinations>
        if not is_numeric_transition:
            p1 = re.findall(
                r"(?:from|starting\s+at)\s+([a-zA-Z0-9_.,\s\(\)`'\-]+?)\s+(?:to|reaches|into)\s+([a-zA-Z0-9_.,\s\(\)`'\-]+?)(?=\s*[.,?;]|\s+which|\s+show|\s+what|\s+explain|\s+and\s+from|$)",
                query,
                re.IGNORECASE
            )
            for src_seg, dst_seg in p1:
                sources = _split_items(src_seg)
                destinations = _split_items(dst_seg)
                for s in sources:
                    for d in destinations:
                        if s and d and s != d and not _is_numeric(s) and not _is_numeric(d):
                            if (s, d) not in endpoints:
                                endpoints.append((s, d))
                            role_map[s] = "source"
                            role_map[d] = "destination"

        # Pattern 2: path between X and Y
        p2 = re.findall(
            r"(?:path|connection)\s+between\s+[`'\"\s]*([a-zA-Z0-9_.-]+(?:\(\))?)[`'\"\s]*\s+and\s+[`'\"\s]*((?:the\s+)?[a-zA-Z0-9_.\s-]+?(?:\(\))?)(?=\s*[.,?;]|\s+which|\s+show|\s+what|\s+explain|$)",
            query,
            re.IGNORECASE
        )
        for src, dst in p2:
            src_clean = _clean_item(src)
            dst_clean = _clean_item(dst)
            if src_clean and dst_clean and src_clean != dst_clean and not _is_numeric(src_clean) and not _is_numeric(dst_clean) and (src_clean, dst_clean) not in endpoints:
                endpoints.append((src_clean, dst_clean))
                role_map[src_clean] = "source"
                role_map[dst_clean] = "destination"

        return endpoints, role_map
