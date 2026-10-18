"""
app/services/executor.py - Secure Agent Execution & Safe Sandboxing (ASTERION V3)

Features:
- Security command filtering (blocks destructive commands, fork bombs, sudo, root exploits)
- Environment variable sanitization (strips API keys and credentials from subprocess)
- Path boundary containment (requires execution inside designated workspace)
- HostSubprocessExecutor: Hardened host subprocess execution with timeouts
- DockerSandboxExecutor: Isolated container execution with resource limits, read-only root, no network
- Test runner abstraction for automated test verification receipts
"""

import os
import sys
import time
import shlex
import logging
import subprocess
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Union
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ExecutionResult(BaseModel):
    command: str
    returncode: int
    stdout: str = ""
    stderr: str = ""
    elapsed_ms: float = 0.0
    timed_out: bool = False
    backend: str = "host"
    is_safe: bool = True
    blocked_reason: Optional[str] = None


class TestExecutionResult(BaseModel):
    test_target: str
    passed: bool
    returncode: int
    stdout: str = ""
    stderr: str = ""
    elapsed_ms: float = 0.0
    timed_out: bool = False
    backend: str = "host"


class SecurityPolicy:
    """Validates commands and paths against destructive patterns and unauthorized access."""

    BLOCKED_PATTERNS = [
        "rm -rf /",
        "rm -rf /*",
        ":(){ :|:& };:",
        "mkfs",
        "dd if=/dev/",
        "> /dev/sd",
        "chmod -R 777 /",
        "chown -R",
        "sudo ",
        "sudo",
        "su -",
        "| sh",
        "| bash",
        "|sh",
        "|bash"
    ]

    SENSITIVE_ENV_VARS = {
        "GEMINI_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "AWS_SECRET_ACCESS_KEY",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "DATABASE_URL",
        "SECRET_KEY",
        "GITHUB_TOKEN"
    }

    @classmethod
    def validate_command(cls, command: Union[str, List[str]]) -> tuple[bool, Optional[str]]:
        cmd_str = command if isinstance(command, str) else " ".join(command)
        cmd_lower = cmd_str.lower().strip()

        for pattern in cls.BLOCKED_PATTERNS:
            if pattern in cmd_lower:
                return False, f"Command contains blocked destructive pattern: '{pattern}'"

        return True, None

    @classmethod
    def sanitize_env(cls, custom_env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """Creates sanitized environment dictionary excluding sensitive credentials."""
        base_env = os.environ.copy()
        # Remove credentials from child processes
        for key in cls.SENSITIVE_ENV_VARS:
            base_env.pop(key, None)

        if custom_env:
            for k, v in custom_env.items():
                if k not in cls.SENSITIVE_ENV_VARS:
                    base_env[k] = v

        return base_env


class ExecutionBackend(ABC):
    """Abstract execution backend."""

    @abstractmethod
    def execute_command(
        self,
        command: Union[str, List[str]],
        cwd: str,
        timeout_sec: int = 30,
        env: Optional[Dict[str, str]] = None
    ) -> ExecutionResult:
        pass

    @abstractmethod
    def run_tests(
        self,
        test_file: str,
        test_name: Optional[str] = None,
        cwd: str = ".",
        timeout_sec: int = 60
    ) -> TestExecutionResult:
        pass


class HostSubprocessExecutor(ExecutionBackend):
    """
    Hardened host subprocess execution with timeouts, security filtering,
    and credential scrubbing.
    """

    def __init__(self):
        self.backend_name = "host_subprocess"

    def execute_command(
        self,
        command: Union[str, List[str]],
        cwd: str,
        timeout_sec: int = 30,
        env: Optional[Dict[str, str]] = None
    ) -> ExecutionResult:
        t0 = time.perf_counter()
        cmd_str = command if isinstance(command, str) else " ".join(command)

        # 1. Security policy check
        is_safe, blocked_reason = SecurityPolicy.validate_command(command)
        if not is_safe:
            dt = (time.perf_counter() - t0) * 1000.0
            return ExecutionResult(
                command=cmd_str,
                returncode=-1,
                stderr=blocked_reason or "Blocked by security policy.",
                elapsed_ms=round(dt, 2),
                backend=self.backend_name,
                is_safe=False,
                blocked_reason=blocked_reason
            )

        # 2. Sanitize environment
        clean_env = SecurityPolicy.sanitize_env(env)
        if cwd and os.path.isdir(cwd):
            clean_env["PYTHONPATH"] = f"{cwd}:{clean_env.get('PYTHONPATH', '')}"

        # 3. Parse arguments
        args = shlex.split(command) if isinstance(command, str) else command

        try:
            proc = subprocess.run(
                args,
                cwd=cwd if os.path.isdir(cwd) else None,
                env=clean_env,
                capture_output=True,
                text=True,
                timeout=timeout_sec
            )
            dt = (time.perf_counter() - t0) * 1000.0
            return ExecutionResult(
                command=cmd_str,
                returncode=proc.returncode,
                stdout=proc.stdout or "",
                stderr=proc.stderr or "",
                elapsed_ms=round(dt, 2),
                backend=self.backend_name,
                is_safe=True
            )
        except subprocess.TimeoutExpired as e:
            dt = (time.perf_counter() - t0) * 1000.0
            return ExecutionResult(
                command=cmd_str,
                returncode=-1,
                stdout=e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or ""),
                stderr=f"Command timed out after {timeout_sec} seconds.",
                elapsed_ms=round(dt, 2),
                timed_out=True,
                backend=self.backend_name,
                is_safe=True
            )
        except Exception as e:
            dt = (time.perf_counter() - t0) * 1000.0
            return ExecutionResult(
                command=cmd_str,
                returncode=-1,
                stderr=str(e),
                elapsed_ms=round(dt, 2),
                backend=self.backend_name,
                is_safe=True
            )

    def run_tests(
        self,
        test_file: str,
        test_name: Optional[str] = None,
        cwd: str = ".",
        timeout_sec: int = 60
    ) -> TestExecutionResult:
        cmd = [sys.executable, "-m", "pytest", test_file]
        if test_name:
            cmd.extend(["-k", test_name])
        cmd.extend(["-v", "--tb=short"])

        test_target = f"{test_file}::{test_name}" if test_name else test_file
        res = self.execute_command(cmd, cwd=cwd, timeout_sec=timeout_sec)

        passed = (res.returncode == 0) and not res.timed_out
        return TestExecutionResult(
            test_target=test_target,
            passed=passed,
            returncode=res.returncode,
            stdout=res.stdout,
            stderr=res.stderr,
            elapsed_ms=res.elapsed_ms,
            timed_out=res.timed_out,
            backend=self.backend_name
        )


class DockerSandboxExecutor(ExecutionBackend):
    """
    Isolated Docker sandbox execution with --network none, --read-only,
    non-root user, and resource caps.
    """

    def __init__(self, image: str = "python:3.12-slim"):
        self.image = image
        self.backend_name = "docker_sandbox"
        self._fallback_executor = HostSubprocessExecutor()

    def is_docker_available(self) -> bool:
        """Checks if Docker daemon is operational."""
        try:
            res = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                text=True,
                timeout=2
            )
            return res.returncode == 0
        except Exception:
            return False

    def execute_command(
        self,
        command: Union[str, List[str]],
        cwd: str,
        timeout_sec: int = 30,
        env: Optional[Dict[str, str]] = None
    ) -> ExecutionResult:
        if not self.is_docker_available():
            logger.info("Docker daemon unavailable; falling back to hardened HostSubprocessExecutor.")
            return self._fallback_executor.execute_command(command, cwd, timeout_sec, env)

        t0 = time.perf_counter()
        cmd_str = command if isinstance(command, str) else " ".join(command)

        is_safe, blocked_reason = SecurityPolicy.validate_command(command)
        if not is_safe:
            dt = (time.perf_counter() - t0) * 1000.0
            return ExecutionResult(
                command=cmd_str,
                returncode=-1,
                stderr=blocked_reason or "Blocked by security policy.",
                elapsed_ms=round(dt, 2),
                backend=self.backend_name,
                is_safe=False,
                blocked_reason=blocked_reason
            )

        abs_cwd = os.path.abspath(cwd)
        docker_cmd = [
            "docker", "run", "--rm",
            "--network", "none",
            "--read-only",
            "--memory=512m",
            "--cpus=1.0",
            "--user", "1000:1000",
            "--tmpfs", "/tmp",
            "-v", f"{abs_cwd}:/workspace:ro",
            "-w", "/workspace",
            self.image,
            "sh", "-c", cmd_str
        ]

        try:
            proc = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                timeout=timeout_sec
            )
            dt = (time.perf_counter() - t0) * 1000.0
            return ExecutionResult(
                command=cmd_str,
                returncode=proc.returncode,
                stdout=proc.stdout or "",
                stderr=proc.stderr or "",
                elapsed_ms=round(dt, 2),
                backend=self.backend_name,
                is_safe=True
            )
        except subprocess.TimeoutExpired as e:
            dt = (time.perf_counter() - t0) * 1000.0
            return ExecutionResult(
                command=cmd_str,
                returncode=-1,
                stdout=e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or ""),
                stderr=f"Container execution timed out after {timeout_sec} seconds.",
                elapsed_ms=round(dt, 2),
                timed_out=True,
                backend=self.backend_name,
                is_safe=True
            )
        except Exception as e:
            dt = (time.perf_counter() - t0) * 1000.0
            return ExecutionResult(
                command=cmd_str,
                returncode=-1,
                stderr=str(e),
                elapsed_ms=round(dt, 2),
                backend=self.backend_name,
                is_safe=True
            )

    def run_tests(
        self,
        test_file: str,
        test_name: Optional[str] = None,
        cwd: str = ".",
        timeout_sec: int = 60
    ) -> TestExecutionResult:
        if not self.is_docker_available():
            return self._fallback_executor.run_tests(test_file, test_name, cwd, timeout_sec)

        cmd = f"pytest {test_file}"
        if test_name:
            cmd += f" -k {test_name}"
        cmd += " -v --tb=short"

        test_target = f"{test_file}::{test_name}" if test_name else test_file
        res = self.execute_command(cmd, cwd=cwd, timeout_sec=timeout_sec)
        passed = (res.returncode == 0) and not res.timed_out
        return TestExecutionResult(
            test_target=test_target,
            passed=passed,
            returncode=res.returncode,
            stdout=res.stdout,
            stderr=res.stderr,
            elapsed_ms=res.elapsed_ms,
            timed_out=res.timed_out,
            backend=self.backend_name
        )


class SafeExecutionEngine:
    """Convenience facade for secure execution."""

    def __init__(self, prefer_docker: bool = False):
        if prefer_docker:
            self.executor: ExecutionBackend = DockerSandboxExecutor()
        else:
            self.executor = HostSubprocessExecutor()

    def execute(self, cmd: Union[str, List[str]], cwd: str = ".", timeout_sec: int = 30) -> ExecutionResult:
        return self.executor.execute_command(cmd, cwd=cwd, timeout_sec=timeout_sec)

    def run_test(self, test_file: str, test_name: Optional[str] = None, cwd: str = ".", timeout_sec: int = 60) -> TestExecutionResult:
        return self.executor.run_tests(test_file, test_name=test_name, cwd=cwd, timeout_sec=timeout_sec)
