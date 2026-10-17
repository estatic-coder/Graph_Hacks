import os
import tempfile
from unittest.mock import MagicMock
import pytest

from app.agent.control_flow import ControlFlowAnalyzer

# 12 Synthetic Functions covering all required loop & exception control flow scenarios
SYNTHETIC_LOOP_CODE = """
# 1. While loop with inclusive comparison (<=)
def fn_while_inclusive(service):
    attempts = 0
    MAX_RETRIES = 2
    while attempts <= MAX_RETRIES:
        attempts += 1
        try:
            service.call()
        except Exception:
            service.record("retry_audit")
    service.cleanup("exhausted")

# 2. While loop with exclusive comparison (<)
def fn_while_exclusive(service):
    attempts = 0
    MAX_RETRIES = 2
    while attempts < MAX_RETRIES:
        attempts += 1
        try:
            service.call()
        except Exception:
            service.record("retry_audit")
    service.cleanup("exhausted")

# 3. Counter increment before call
def fn_increment_before_call(service):
    attempts = 0
    MAX_RETRIES = 2
    while attempts < MAX_RETRIES:
        attempts += 1
        service.record("inc_before")
        try:
            service.call()
        except Exception:
            pass

# 4. Counter increment after call
def fn_increment_after_call(service):
    attempts = 0
    MAX_RETRIES = 2
    while attempts < MAX_RETRIES:
        try:
            service.call()
        except Exception:
            pass
        service.record("inc_after")
        attempts += 1

# 5. Exception handler that continues
def fn_handler_continues(service):
    attempts = 0
    MAX_RETRIES = 2
    while attempts <= MAX_RETRIES:
        attempts += 1
        try:
            service.call()
        except Exception:
            service.record("continue_audit")
            continue

# 6. Exception handler that returns
def fn_handler_returns(service):
    attempts = 0
    MAX_RETRIES = 2
    while attempts <= MAX_RETRIES:
        attempts += 1
        try:
            service.call()
        except Exception:
            service.record("handler_return")
            return "failed_in_handler"
    return "exhausted"

# 7. Exception handler that breaks
def fn_handler_breaks(service):
    attempts = 0
    MAX_RETRIES = 2
    while attempts <= MAX_RETRIES:
        attempts += 1
        try:
            service.call()
        except Exception:
            service.record("handler_break")
            break
    service.cleanup("loop_broken")

# 8. Exception handler that re-raises
def fn_handler_reraises(service):
    attempts = 0
    MAX_RETRIES = 2
    while attempts <= MAX_RETRIES:
        attempts += 1
        try:
            service.call()
        except Exception:
            service.record("handler_reraise")
            raise

# 9. Successful return during first attempt
def fn_success_first_attempt(service):
    attempts = 0
    MAX_RETRIES = 2
    while attempts <= MAX_RETRIES:
        attempts += 1
        try:
            res = service.call()
            return res
        except Exception:
            pass
    return None

# 10. Successful return after multiple failures
def fn_success_after_multiple_failures(service):
    attempts = 0
    MAX_RETRIES = 3
    while attempts <= MAX_RETRIES:
        attempts += 1
        try:
            res = service.call()
            return res
        except Exception:
            service.record("retry_event")
    return None

# 11. Failure cleanup after loop exhaustion
def fn_exhaustion_cleanup(service):
    attempts = 0
    MAX_RETRIES = 2
    while attempts <= MAX_RETRIES:
        attempts += 1
        try:
            service.call()
        except Exception:
            service.record("retry")
    service.release_stock("item_1")
    service.notify_failure("customer_1")

# 12. Failure cleanup inside exception handler
def fn_handler_cleanup(service):
    attempts = 0
    MAX_RETRIES = 2
    while attempts <= MAX_RETRIES:
        attempts += 1
        try:
            service.call()
        except Exception:
            service.release_in_handler("cleaned_in_handler")
            return False
    return True
"""


@pytest.fixture(scope="module")
def synthetic_env():
    """Sets up a temporary Python file containing all 12 synthetic functions."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as tf:
        tf.write(SYNTHETIC_LOOP_CODE)
        temp_path = tf.name

    cf = ControlFlowAnalyzer(repo_path=os.path.dirname(temp_path))
    file_name = os.path.basename(temp_path)

    # Load module dynamically to execute functions for comparison
    import importlib.util
    spec = importlib.util.spec_from_file_location("synthetic_module", temp_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    yield cf, file_name, mod

    try:
        os.remove(temp_path)
    except Exception:
        pass


def test_scenario_1_while_inclusive_comparison(synthetic_env):
    cf, file_name, mod = synthetic_env
    # 1. Actual execution
    mock_service = MagicMock()
    mock_service.call.side_effect = RuntimeError("timeout")
    mod.fn_while_inclusive(mock_service)
    actual_attempts = mock_service.call.call_count
    assert actual_attempts == 3

    # 2. Analyzer prediction
    pred = cf.analyze_loop_and_retry(file_name, "fn_while_inclusive")
    assert pred["status"] == "success"
    assert pred["loop_type"] == "while"
    assert "<=" in pred["loop_condition"]
    assert pred["max_possible_iterations"] == 3
    assert pred["attempt_count"] == actual_attempts
    assert pred["retry_count"] == 2
    assert pred["has_early_exit_in_handler"] is False


def test_scenario_2_while_exclusive_comparison(synthetic_env):
    cf, file_name, mod = synthetic_env
    # 1. Actual execution
    mock_service = MagicMock()
    mock_service.call.side_effect = RuntimeError("timeout")
    mod.fn_while_exclusive(mock_service)
    actual_attempts = mock_service.call.call_count
    assert actual_attempts == 2

    # 2. Analyzer prediction
    pred = cf.analyze_loop_and_retry(file_name, "fn_while_exclusive")
    assert pred["status"] == "success"
    assert "<" in pred["loop_condition"]
    assert pred["max_possible_iterations"] == 2
    assert pred["attempt_count"] == actual_attempts
    assert pred["retry_count"] == 1


def test_scenario_3_counter_increment_before_call(synthetic_env):
    cf, file_name, mod = synthetic_env
    pred = cf.analyze_loop_and_retry(file_name, "fn_increment_before_call")
    assert pred["status"] == "success"
    assert pred["counter_update_position"] == "before_call"


def test_scenario_4_counter_increment_after_call(synthetic_env):
    cf, file_name, mod = synthetic_env
    pred = cf.analyze_loop_and_retry(file_name, "fn_increment_after_call")
    assert pred["status"] == "success"
    assert pred["counter_update_position"] == "after_call"


def test_scenario_5_handler_continues(synthetic_env):
    cf, file_name, mod = synthetic_env
    mock_service = MagicMock()
    mock_service.call.side_effect = RuntimeError("timeout")
    mod.fn_handler_continues(mock_service)
    actual_attempts = mock_service.call.call_count
    assert actual_attempts == 3

    pred = cf.analyze_loop_and_retry(file_name, "fn_handler_continues")
    assert pred["status"] == "success"
    assert pred["exception_handlers"][0]["action"] == "continue"
    assert pred["attempt_count"] == actual_attempts


def test_scenario_6_handler_returns(synthetic_env):
    cf, file_name, mod = synthetic_env
    mock_service = MagicMock()
    mock_service.call.side_effect = RuntimeError("timeout")
    ret = mod.fn_handler_returns(mock_service)
    actual_attempts = mock_service.call.call_count
    assert actual_attempts == 1
    assert ret == "failed_in_handler"

    pred = cf.analyze_loop_and_retry(file_name, "fn_handler_returns")
    assert pred["status"] == "success"
    assert pred["exception_handlers"][0]["action"] == "return"
    assert pred["has_early_exit_in_handler"] is True
    assert pred["attempt_count"] == actual_attempts


def test_scenario_7_handler_breaks(synthetic_env):
    cf, file_name, mod = synthetic_env
    mock_service = MagicMock()
    mock_service.call.side_effect = RuntimeError("timeout")
    mod.fn_handler_breaks(mock_service)
    actual_attempts = mock_service.call.call_count
    assert actual_attempts == 1
    mock_service.cleanup.assert_called_once_with("loop_broken")

    pred = cf.analyze_loop_and_retry(file_name, "fn_handler_breaks")
    assert pred["status"] == "success"
    assert pred["exception_handlers"][0]["action"] == "break"
    assert pred["has_early_exit_in_handler"] is True
    assert pred["attempt_count"] == actual_attempts


def test_scenario_8_handler_reraises(synthetic_env):
    cf, file_name, mod = synthetic_env
    mock_service = MagicMock()
    mock_service.call.side_effect = RuntimeError("timeout")
    with pytest.raises(RuntimeError):
        mod.fn_handler_reraises(mock_service)
    actual_attempts = mock_service.call.call_count
    assert actual_attempts == 1

    pred = cf.analyze_loop_and_retry(file_name, "fn_handler_reraises")
    assert pred["status"] == "success"
    assert pred["exception_handlers"][0]["action"] == "reraise"
    assert pred["has_early_exit_in_handler"] is True
    assert pred["attempt_count"] == actual_attempts


def test_scenario_9_successful_return_first_attempt(synthetic_env):
    cf, file_name, mod = synthetic_env
    mock_service = MagicMock()
    mock_service.call.return_value = "success_obj"
    res = mod.fn_success_first_attempt(mock_service)
    actual_attempts = mock_service.call.call_count
    assert actual_attempts == 1
    assert res == "success_obj"

    pred = cf.analyze_loop_and_retry(file_name, "fn_success_first_attempt")
    assert pred["status"] == "success"
    assert len(pred["early_exits"]) > 0
    assert any(ee["type"] == "return" for ee in pred["early_exits"])


def test_scenario_10_successful_return_after_multiple_failures(synthetic_env):
    cf, file_name, mod = synthetic_env
    mock_service = MagicMock()
    # Fails on attempts 1 and 2, succeeds on attempt 3
    mock_service.call.side_effect = [RuntimeError("err1"), RuntimeError("err2"), "success_on_3"]
    res = mod.fn_success_after_multiple_failures(mock_service)
    actual_attempts = mock_service.call.call_count
    assert actual_attempts == 3
    assert res == "success_on_3"

    pred = cf.analyze_loop_and_retry(file_name, "fn_success_after_multiple_failures")
    assert pred["status"] == "success"
    assert pred["max_possible_iterations"] == 4


def test_scenario_11_exhaustion_cleanup(synthetic_env):
    cf, file_name, mod = synthetic_env
    mock_service = MagicMock()
    mock_service.call.side_effect = RuntimeError("timeout")
    mod.fn_exhaustion_cleanup(mock_service)
    mock_service.release_stock.assert_called_once_with("item_1")
    mock_service.notify_failure.assert_called_once_with("customer_1")

    pred = cf.analyze_loop_and_retry(file_name, "fn_exhaustion_cleanup")
    assert pred["status"] == "success"
    exhaustion_stmts = [se["statement"] for se in pred["side_effects"] if se.get("timing") == "on_exhaustion"]
    assert any("release_stock" in s for s in exhaustion_stmts)
    assert any("notify_failure" in s for s in exhaustion_stmts)


def test_scenario_12_handler_cleanup(synthetic_env):
    cf, file_name, mod = synthetic_env
    mock_service = MagicMock()
    mock_service.call.side_effect = RuntimeError("timeout")
    mod.fn_handler_cleanup(mock_service)
    mock_service.release_in_handler.assert_called_once_with("cleaned_in_handler")

    pred = cf.analyze_loop_and_retry(file_name, "fn_handler_cleanup")
    assert pred["status"] == "success"
    handler_stmts = [se["statement"] for se in pred["side_effects"] if se.get("timing") == "in_exception_handler"]
    assert any("release_in_handler" in s for s in handler_stmts)
    assert pred["attempt_count"] == 1
