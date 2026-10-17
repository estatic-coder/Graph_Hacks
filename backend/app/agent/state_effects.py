"""
app/agent/state_effects.py - Interprocedural State-Effect and Operation Comparison Engine.

Builds reusable, source-backed summaries for functions mutating state and compares
operations (e.g. refund vs release_hold, reject vs approve) directly from AST facts.
"""

import os
import ast
import re
import logging
from typing import Dict, Any, List, Optional, Tuple, Set

from app.agent.models import StateEffectSummary

logger = logging.getLogger(__name__)


class StateEffectAnalyzer:
    """
    Analyzes AST state mutations, reads, writes, collections, exceptions, and side-effects.
    Composes summaries across callee boundaries to determine interprocedural financial effects.
    """

    def __init__(self, repo_path: str):
        self.repo_path = repo_path
        self._parsed_cache: Dict[str, ast.AST] = {}

    def _parse_file(self, rel_path: str) -> Optional[ast.AST]:
        clean = rel_path.lstrip("/").lstrip("\\")
        if clean in self._parsed_cache:
            return self._parsed_cache[clean]
        full_path = os.path.join(self.repo_path, clean)
        if not os.path.exists(full_path):
            return None
        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                tree = ast.parse(f.read())
                self._parsed_cache[clean] = tree
                return tree
        except Exception as e:
            logger.error(f"Failed to parse AST for {rel_path}: {e}")
            return None

    def find_function(self, func_name: str, rel_path: Optional[str] = None) -> Tuple[Optional[ast.FunctionDef], Optional[str], Optional[ast.AST]]:
        if rel_path:
            clean_rel = os.path.relpath(os.path.join(self.repo_path, rel_path), self.repo_path)
            tree = self._parse_file(clean_rel)
            if tree:
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
                        return node, clean_rel, tree

        for root, _, files in os.walk(self.repo_path):
            if any(ig in root for ig in [".git", ".venv", "__pycache__"]):
                continue
            for f in files:
                if not f.endswith(".py"):
                    continue
                cand_path = os.path.join(root, f)
                cand_rel = os.path.relpath(cand_path, self.repo_path)
                tree = self._parse_file(cand_rel)
                if not tree:
                    continue
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
                        return node, cand_rel, tree
        return None, None, None

    def analyze_function(self, func_name: str, rel_path_or_visited: Any = None, visited: Optional[Set[str]] = None) -> Optional[StateEffectSummary]:
        if isinstance(rel_path_or_visited, set):
            visited = rel_path_or_visited
            rel_path = None
        elif isinstance(rel_path_or_visited, str):
            rel_path = rel_path_or_visited
        else:
            rel_path = None

        # Handle swapped arguments like analyze_function("settlement.py", "release_escrow")
        if (func_name.endswith(".py") or "/" in func_name) and rel_path and not rel_path.endswith(".py"):
            func_name, rel_path = rel_path, func_name

        if visited is None:
            visited = set()
        if func_name in visited:
            return None
        visited.add(func_name)

        fn_node, fn_rel, tree = self.find_function(func_name, rel_path=rel_path)
        if not fn_node or not fn_rel:
            return None

        line_span = f"{fn_rel}:{fn_node.lineno}-{getattr(fn_node, 'end_lineno', fn_node.lineno)}"
        citations = [f"{fn_rel}:{fn_node.lineno}"]

        preconditions = []
        state_reads = []
        state_writes = []
        collection_mutations = []
        balance_restored = False
        balance_explanation = "No balance mutation identified."
        hold_effect = "none"
        status_transitions = []
        events = []
        notices = []

        quota_effect = "none"
        reservation_effect = "none"
        receipt_value = None
        queue_writes = []
        queue_reads = []

        # Analyze statements and nested blocks
        for stmt in fn_node.body:
            citations.append(f"{fn_rel}:{stmt.lineno}")
            if isinstance(stmt, ast.If):
                test_str = ast.unparse(stmt.test)
                for b_stmt in stmt.body:
                    if isinstance(b_stmt, ast.Raise):
                        preconditions.append(f"Requires NOT ({test_str}) else raises {ast.unparse(b_stmt.exc) if b_stmt.exc else 'Exception'}")
                    elif isinstance(b_stmt, ast.Return):
                        preconditions.append(f"Requires NOT ({test_str}) else returns early")

        for node in ast.walk(fn_node):
            if isinstance(node, ast.AugAssign):
                t_code = ast.unparse(node.target)
                v_code = ast.unparse(node.value)
                op_sym = "+=" if isinstance(node.op, ast.Add) else ("-=" if isinstance(node.op, ast.Sub) else "op=")
                mut_str = f"Mutates {t_code} {op_sym} {v_code}"
                if mut_str not in state_writes:
                    state_writes.append(mut_str)
                if any(k in t_code.lower() for k in ["balance", "account", "fund", "wallet"]) and isinstance(node.op, ast.Add):
                    balance_restored = True
                    balance_explanation = f"Increases balance via `{t_code} += {v_code}` at [{fn_rel}:{getattr(node, 'lineno', fn_node.lineno)}]."
                if any(k in t_code.lower() for k in ["credit", "quota", "token"]):
                    if isinstance(node.op, ast.Add):
                        quota_effect = "restored"
                    elif isinstance(node.op, ast.Sub):
                        quota_effect = "decremented"
                if "replay" in t_code.lower():
                    state_writes.append(f"Increments replay counter: `{t_code} {op_sym} {v_code}`")

            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    t_code = ast.unparse(target)
                    val_code = ast.unparse(node.value)
                    if "status" in t_code:
                        st_str = f"Sets {t_code} = {val_code}"
                        if st_str not in status_transitions:
                            status_transitions.append(st_str)
                    elif "receipt" in t_code:
                        receipt_value = val_code
                    elif "reservation" in t_code:
                        reservation_effect = "reserved" if val_code == "True" else "cleared"
                    elif "[" in t_code:
                        w_str = f"Writes {t_code} = {val_code}"
                        if w_str not in state_writes:
                            state_writes.append(w_str)
                        if "replay" in t_code.lower():
                            state_writes.append(f"Updates replay counter: `{t_code} = {val_code}`")

            elif isinstance(node, ast.Delete):
                for target in node.targets:
                    t_code = ast.unparse(target)
                    del_str = f"Removes item from `{t_code}` via del"
                    if del_str not in collection_mutations:
                        collection_mutations.append(del_str)
                    if any(k in t_code.lower() for k in ["hold", "escrow"]):
                        hold_effect = "removed_or_released"

            elif isinstance(node, ast.Call):
                c_code = ast.unparse(node)
                if isinstance(node.func, ast.Attribute):
                    attr = node.func.attr
                    obj_name = ast.unparse(node.func.value)
                    if attr == "pop":
                        pop_str = f"Removes item from `{obj_name}` via .pop()"
                        if pop_str not in collection_mutations:
                            collection_mutations.append(pop_str)
                        queue_reads.append(f"Pops from `{obj_name}`: `{c_code}`")
                        if any(k in obj_name.lower() for k in ["hold", "escrow"]):
                            hold_effect = "removed_or_released"
                    elif attr == "append":
                        app_str = f"Appends record to `{obj_name}`"
                        if app_str not in collection_mutations:
                            collection_mutations.append(app_str)
                        queue_writes.append(f"Appends to `{obj_name}`: `{c_code}`")
                    elif attr == "add":
                        add_str = f"Adds item to `{obj_name}` via .add()"
                        if add_str not in collection_mutations:
                            collection_mutations.append(add_str)
                        if any(k in obj_name.lower() for k in ["reserve", "held", "lock"]):
                            reservation_effect = "reserved"
                    elif attr in ("remove", "discard"):
                        rem_str = f"Removes item from `{obj_name}` via .{attr}()"
                        if rem_str not in collection_mutations:
                            collection_mutations.append(rem_str)
                        if any(k in obj_name.lower() for k in ["reserve", "held", "lock"]):
                            reservation_effect = "cleared"
                    elif attr == "clear":
                        clr_str = f"Clears collection `{obj_name}`"
                        if clr_str not in collection_mutations:
                            collection_mutations.append(clr_str)
                elif isinstance(node.func, ast.Name):
                    c_name = node.func.id
                    if c_name in ("record", "append_event", "emit") and c_code not in events:
                        events.append(c_code)
                    elif c_name in ("send_notice", "notify", "notify_customer") and c_code not in notices:
                        notices.append(c_code)
                    elif c_name in ("enqueue", "enqueue_job"):
                        queue_writes.append(f"Enqueues job via `{c_code}`")
                    elif c_name == "reserve":
                        reservation_effect = "reserved"
                        quota_effect = "decremented"
                    elif c_name == "release":
                        reservation_effect = "cleared"
                        quota_effect = "restored"
                    elif c_name == "consume":
                        reservation_effect = "cleared"
                        quota_effect = "consumed"
                    elif c_name == "release_hold":
                        hold_effect = "released"
                    elif c_name == "capture_hold":
                        hold_effect = "captured"

        # Check callees recursively for state effects
        callee_names = set()
        for call in ast.walk(fn_node):
            if isinstance(call, ast.Call):
                if isinstance(call.func, ast.Name):
                    callee_names.add(call.func.id)
                elif isinstance(call.func, ast.Attribute):
                    callee_names.add(call.func.attr)

        for callee in callee_names:
            if callee not in ("load", "save", "print", "len", "list", "set", "dict", "str"):
                callee_summary = self.analyze_function(callee, visited=visited.copy())
                if callee_summary:
                    if callee_summary.balance_restored:
                        balance_restored = True
                        balance_explanation = f"Transitively restores balance via callee `{callee}()`: {callee_summary.balance_effect_explanation}"
                    if callee_summary.hold_effect != "none" and hold_effect == "none":
                        hold_effect = callee_summary.hold_effect
                    if callee_summary.quota_effect != "none" and quota_effect == "none":
                        quota_effect = callee_summary.quota_effect
                    if callee_summary.reservation_effect != "none" and reservation_effect == "none":
                        reservation_effect = callee_summary.reservation_effect
                    if callee_summary.receipt_value and not receipt_value:
                        receipt_value = callee_summary.receipt_value
                    citations.extend(callee_summary.citations)
                    state_writes.extend(callee_summary.state_writes)
                    collection_mutations.extend(callee_summary.collection_mutations)
                    queue_writes.extend(callee_summary.queue_writes)
                    queue_reads.extend(callee_summary.queue_reads)
                    events.extend(callee_summary.events)
                    notices.extend(callee_summary.notices)

        # De-duplicate citations
        unique_cits = []
        for c in citations:
            if c not in unique_cits:
                unique_cits.append(c)

        return StateEffectSummary(
            function_name=func_name,
            file_path=fn_rel,
            line_span=line_span,
            preconditions=list(set(preconditions)),
            state_reads=list(set(state_reads)),
            state_writes=list(set(state_writes)),
            collection_mutations=list(set(collection_mutations)),
            balance_restored=balance_restored,
            balance_effect_explanation=balance_explanation,
            hold_effect=hold_effect,
            quota_effect=quota_effect,
            reservation_effect=reservation_effect,
            receipt_value=receipt_value,
            queue_writes=list(set(queue_writes)),
            queue_reads=list(set(queue_reads)),
            status_transitions=list(set(status_transitions)),
            events=list(set(events)),
            notices=list(set(notices)),
            citations=unique_cits,
        )

    def compare_operations(self, op1_name: str, op2_name: str) -> Dict[str, Any]:
        """
        Directly compares two operations (e.g. refund vs release_hold or reject vs release)
        based on AST-derived state effects.
        """
        s1 = self.analyze_function(op1_name)
        s2 = self.analyze_function(op2_name)

        if not s1 or not s2:
            return {
                "op1": op1_name,
                "op2": op2_name,
                "comparison_available": False,
                "summary": f"Could not locate one or both functions: '{op1_name}' ({bool(s1)}), '{op2_name}' ({bool(s2)})",
            }

        balance_diff = (
            f"`{op1_name}()` {'restores balance' if s1.balance_restored else 'does NOT restore balance'}, "
            f"whereas `{op2_name}()` {'restores balance' if s2.balance_restored else 'does NOT restore balance'}."
        )

        quota_diff = (
            f"`{op1_name}()` quota effect: `{s1.quota_effect}`; `{op2_name}()` quota effect: `{s2.quota_effect}`."
        )
        reservation_diff = (
            f"`{op1_name}()` reservation effect: `{s1.reservation_effect}`; `{op2_name}()` reservation effect: `{s2.reservation_effect}`."
        )

        hold_diff = f"`{op1_name}()` hold effect: `{s1.hold_effect}`; `{op2_name}()` hold effect: `{s2.hold_effect}`."
        status_diff = f"`{op1_name}()` status transitions: {s1.status_transitions or 'none'}; `{op2_name}()` status transitions: {s2.status_transitions or 'none'}."

        return {
            "op1": op1_name,
            "op2": op2_name,
            "op1_summary": s1,
            "op2_summary": s2,
            "comparison_available": True,
            "op1_restores_balance": s1.balance_restored,
            "op2_restores_balance": s2.balance_restored,
            "balance_comparison": balance_diff,
            "quota_comparison": quota_diff,
            "reservation_comparison": reservation_diff,
            "hold_comparison": hold_diff,
            "status_comparison": status_diff,
            "citations": list(set(s1.citations + s2.citations)),
            "summary": f"{balance_diff} {quota_diff} {hold_diff}",
        }
