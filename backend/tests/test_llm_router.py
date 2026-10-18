import time
import json
import pytest

from app.services.llm_router import (
    CircuitBreaker,
    LLMRouter,
    LLMProvider,
    DeterministicFallbackProvider
)

class MockFailingProvider(LLMProvider):
    def __init__(self):
        super().__init__(name="mock_failing", model="mock-fail-v1")
        
    def is_available(self) -> bool:
        return True
        
    def generate(self, prompt: str, system_prompt=None, json_mode=False, temperature=0.2) -> str:
        raise ConnectionError("Upstream API is unreachable")


class MockSuccessProvider(LLMProvider):
    def __init__(self, name="mock_success"):
        super().__init__(name=name, model="mock-succ-v1")
        
    def is_available(self) -> bool:
        return True
        
    def generate(self, prompt: str, system_prompt=None, json_mode=False, temperature=0.2) -> str:
        return f"Synthesized response for: {prompt}"


def test_circuit_breaker_lifecycle():
    cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=0.1)
    assert cb.state == CircuitBreaker.CLOSED
    assert cb.can_attempt() is True
    
    # 2 failures - still closed
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitBreaker.CLOSED
    assert cb.can_attempt() is True
    
    # 3rd failure trips circuit
    cb.record_failure()
    assert cb.state == CircuitBreaker.OPEN
    assert cb.can_attempt() is False
    
    # Wait for cooldown
    time.sleep(0.12)
    assert cb.can_attempt() is True
    assert cb.state == CircuitBreaker.HALF_OPEN
    
    # Success resets to CLOSED
    cb.record_success()
    assert cb.state == CircuitBreaker.CLOSED
    assert cb.failure_count == 0


def test_deterministic_fallback():
    provider = DeterministicFallbackProvider()
    assert provider.is_available() is True
    
    # Text mode
    res_text = provider.generate("Analyze the impact of modifying worker.py")
    assert "Impact Analysis" in res_text
    
    # JSON mode
    res_json = provider.generate("Return impact summary", json_mode=True)
    parsed = json.loads(res_json)
    assert parsed["status"] == "success"
    assert parsed["is_deterministic"] is True


def test_router_cascade_on_failure():
    router = LLMRouter()
    failing = MockFailingProvider()
    router.register_provider(failing)
    
    # Force use of failing provider - should cascade to deterministic fallback
    res = router.generate(
        prompt="Who owns the worker module?",
        forced_provider="mock_failing",
        max_retries=1
    )
    assert res["is_fallback"] is True
    assert res["provider"] == "deterministic"
    assert len(res["attempts"]) >= 1
    assert res["attempts"][0]["provider"] == "mock_failing"
    assert res["attempts"][0]["status"] == "failed"


def test_router_success_with_custom_provider():
    router = LLMRouter()
    custom = MockSuccessProvider("custom_ai")
    router.register_provider(custom)
    
    res = router.generate(
        prompt="Explain the architecture",
        forced_provider="custom_ai"
    )
    assert res["is_fallback"] is False
    assert res["provider"] == "custom_ai"
    assert "Synthesized response" in res["text"]


def test_router_status():
    router = LLMRouter()
    status = router.get_status()
    assert "preferred_provider" in status
    assert "deterministic" in status["providers"]
    assert status["providers"]["deterministic"]["is_available"] is True
