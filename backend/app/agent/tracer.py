"""
app/agent/tracer.py - Comprehensive Request Lifecycle & Capability Execution Tracer.

Instruments the entire request lifecycle from API ingress to frontend response:
Frontend input -> API payload -> Repository selection -> Intent classification ->
Entity resolution -> Capability selection -> Plan generation -> Tool dispatch ->
Tool execution -> Tool output normalization -> Evidence retrieval ->
Answer synthesis -> Verification -> API response.

Assigns a unique trace ID per request and records timestamps, arguments,
output schemas, field names, error states, and inter-stage data flow.
"""

import time
import uuid
import logging
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class StageTrace(BaseModel):
    stage_name: str
    started_at: float
    finished_at: Optional[float] = None
    duration_ms: float = 0.0
    selected_capability: Optional[str] = None
    input_arguments: Dict[str, Any] = Field(default_factory=dict)
    output_object_type: Optional[str] = None
    output_field_names: List[str] = Field(default_factory=list)
    execution_status: str = "IN_PROGRESS"
    error_details: Optional[str] = None
    passed_to_next_stage: bool = True

    def complete(
        self,
        output_object: Any = None,
        execution_status: str = "SUCCESS",
        error_details: Optional[str] = None,
        passed_to_next_stage: bool = True
    ):
        self.finished_at = time.perf_counter()
        self.duration_ms = round((self.finished_at - self.started_at) * 1000.0, 3)
        self.execution_status = execution_status
        self.error_details = error_details
        self.passed_to_next_stage = passed_to_next_stage

        if output_object is not None:
            self.output_object_type = type(output_object).__name__
            if isinstance(output_object, dict):
                self.output_field_names = list(output_object.keys())
            elif hasattr(output_object, "__dict__"):
                self.output_field_names = list(output_object.__dict__.keys())
            elif isinstance(output_object, (list, tuple)):
                self.output_field_names = [f"item_{i}" for i in range(min(len(output_object), 5))]
            elif isinstance(output_object, str):
                self.output_field_names = ["str_length", "str_preview"]


class RequestLifecycleTracer:
    """
    Maintains the end-to-end trace of a single request across all pipeline stages.
    """

    def __init__(self, trace_id: Optional[str] = None, repo_id: str = "", query: str = ""):
        self.trace_id = trace_id or f"trace_{uuid.uuid4().hex[:8]}"
        self.repo_id = repo_id
        self.query = query
        self.created_at = time.time()
        self.start_perf = time.perf_counter()
        self.stages: List[StageTrace] = []
        self._active_stages: Dict[str, StageTrace] = {}

    def start_stage(
        self,
        stage_name: str,
        input_arguments: Optional[Dict[str, Any]] = None,
        selected_capability: Optional[str] = None
    ) -> StageTrace:
        stage = StageTrace(
            stage_name=stage_name,
            started_at=time.perf_counter(),
            selected_capability=selected_capability,
            input_arguments=input_arguments or {}
        )
        self.stages.append(stage)
        self._active_stages[stage_name] = stage
        return stage

    def end_stage(
        self,
        stage_name: str,
        output_object: Any = None,
        execution_status: str = "SUCCESS",
        error_details: Optional[str] = None,
        passed_to_next_stage: bool = True
    ) -> Optional[StageTrace]:
        stage = self._active_stages.pop(stage_name, None)
        if stage:
            stage.complete(
                output_object=output_object,
                execution_status=execution_status,
                error_details=error_details,
                passed_to_next_stage=passed_to_next_stage
            )
        return stage

    def to_dict(self) -> Dict[str, Any]:
        total_duration = round((time.perf_counter() - self.start_perf) * 1000.0, 3)
        return {
            "trace_id": self.trace_id,
            "repo_id": self.repo_id,
            "query": self.query,
            "total_duration_ms": total_duration,
            "stage_count": len(self.stages),
            "stages": [s.model_dump() for s in self.stages]
        }
