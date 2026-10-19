"""Official Hermes Agent API Server Client for Project EUREKA.

Provides programmatic integration with the documented Hermes API Server
(https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server)
serving OpenAI-compatible HTTP + Server-Sent Events endpoints on port 8642 by default.

Supported Endpoints:
- GET  /health and /health/detailed
- GET  /v1/capabilities
- GET  /v1/models
- POST /v1/chat/completions (with X-Hermes-Session-Id and X-Hermes-Session-Key)
- POST /v1/responses (OpenAI Responses API with server-side tool results)
- POST /v1/runs (asynchronous run submission)
- GET  /v1/runs/{id}
"""

import json
import logging
import os
import shutil
import subprocess
import time
from typing import Any, Dict, List, Optional
import httpx

logger = logging.getLogger("eureka.hermes.client")


class HermesError(Exception):
    """Base exception for Hermes integration errors."""
    pass


class HermesUnavailableError(HermesError):
    """Raised when the Hermes API Server or CLI is unreachable or offline."""
    pass


class HermesTimeoutError(HermesError):
    """Raised when a Hermes request exceeds the configured deadline."""
    pass


class HermesAPIError(HermesError):
    """Raised when Hermes returns an HTTP error status."""
    def __init__(self, status_code: int, message: str, payload: Optional[Any] = None):
        super().__init__(f"Hermes API HTTP {status_code}: {message}")
        self.status_code = status_code
        self.message = message
        self.payload = payload


class HermesClient:
    """Documented HTTP client for the NousResearch Hermes Agent API Server."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout_seconds: float = 30.0,
    ):
        # Prefer HERMES_API_BASE_URL, fallback to HERMES_SERVER_URL, default 127.0.0.1:8642
        self.base_url = (
            base_url
            or os.environ.get("HERMES_API_BASE_URL")
            or os.environ.get("HERMES_SERVER_URL")
            or "http://127.0.0.1:8642"
        ).rstrip("/")
        self.api_key = (
            api_key
            or os.environ.get("HERMES_API_KEY")
            or os.environ.get("API_SERVER_KEY")
            or ""
        )
        self.timeout_seconds = float(
            os.environ.get("HERMES_TIMEOUT_SECONDS") or timeout_seconds
        )
        self.cli_bin = shutil.which("hermes")

    def _get_headers(
        self,
        session_id: Optional[str] = None,
        session_key: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, str]:
        headers: Dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if session_id:
            headers["X-Hermes-Session-Id"] = session_id
        if session_key:
            headers["X-Hermes-Session-Key"] = session_key
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return headers

    def check_health(self) -> Dict[str, Any]:
        """Queries /health on the Hermes API server. Returns health status dict."""
        url = f"{self.base_url}/health"
        start_time = time.time()
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(url, headers=self._get_headers())
                latency_ms = round((time.time() - start_time) * 1000, 2)
                if resp.status_code == 200:
                    return {
                        "status": "online",
                        "base_url": self.base_url,
                        "latency_ms": latency_ms,
                        "http_code": resp.status_code,
                    }
                return {
                    "status": "unhealthy",
                    "base_url": self.base_url,
                    "latency_ms": latency_ms,
                    "http_code": resp.status_code,
                    "message": resp.text[:200],
                }
        except httpx.TimeoutException:
            return {
                "status": "timeout",
                "base_url": self.base_url,
                "error": f"Hermes API health check timed out after 5.0s",
            }
        except Exception as exc:
            return {
                "status": "offline",
                "base_url": self.base_url,
                "error": str(exc),
            }

    def get_capabilities(self) -> Dict[str, Any]:
        """Queries /v1/capabilities for machine-readable feature flags."""
        url = f"{self.base_url}/v1/capabilities"
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                resp = client.get(url, headers=self._get_headers())
                if resp.status_code == 200:
                    return resp.json()
                raise HermesAPIError(resp.status_code, resp.text)
        except (httpx.ConnectError, httpx.NetworkError) as exc:
            raise HermesUnavailableError(f"Cannot reach Hermes API Server at {self.base_url}: {exc}") from exc
        except httpx.TimeoutException as exc:
            raise HermesTimeoutError(f"Hermes API request to /v1/capabilities timed out") from exc

    def chat_completions(
        self,
        messages: List[Dict[str, str]],
        model: str = "hermes-agent",
        stream: bool = False,
        session_id: Optional[str] = None,
        session_key: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        temperature: float = 0.0,
    ) -> Dict[str, Any]:
        """Calls POST /v1/chat/completions (documented OpenAI-compatible format)."""
        url = f"{self.base_url}/v1/chat/completions"
        headers = self._get_headers(
            session_id=session_id,
            session_key=session_key,
            idempotency_key=idempotency_key,
        )
        payload = {
            "model": model,
            "messages": messages,
            "stream": stream,
            "temperature": temperature,
        }

        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                resp = client.post(url, headers=headers, json=payload)
                if resp.status_code == 200:
                    return resp.json()
                if resp.status_code == 409:
                    raise HermesAPIError(409, "Hermes Idempotency Conflict / Admission Conflict", resp.text)
                raise HermesAPIError(resp.status_code, resp.text)
        except (httpx.ConnectError, httpx.NetworkError) as exc:
            raise HermesUnavailableError(
                f"Hermes API Server is offline or unreachable at {self.base_url}: {exc}"
            ) from exc
        except httpx.TimeoutException as exc:
            raise HermesTimeoutError(
                f"Hermes API chat completion timed out after {self.timeout_seconds}s"
            ) from exc

    def create_response(
        self,
        input_text: str,
        instructions: Optional[str] = None,
        previous_response_id: Optional[str] = None,
        conversation: Optional[str] = None,
        model: str = "hermes-agent",
    ) -> Dict[str, Any]:
        """Calls POST /v1/responses (OpenAI Responses API format with server-side tools)."""
        url = f"{self.base_url}/v1/responses"
        headers = self._get_headers()
        payload: Dict[str, Any] = {
            "model": model,
            "input": input_text,
            "store": True,
        }
        if instructions:
            payload["instructions"] = instructions
        if previous_response_id:
            payload["previous_response_id"] = previous_response_id
        if conversation:
            payload["conversation"] = conversation

        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                resp = client.post(url, headers=headers, json=payload)
                if resp.status_code in [200, 201]:
                    return resp.json()
                raise HermesAPIError(resp.status_code, resp.text)
        except (httpx.ConnectError, httpx.NetworkError) as exc:
            raise HermesUnavailableError(
                f"Hermes API Server is offline or unreachable at {self.base_url}: {exc}"
            ) from exc
        except httpx.TimeoutException as exc:
            raise HermesTimeoutError(
                f"Hermes API response creation timed out after {self.timeout_seconds}s"
            ) from exc

    def execute_cli_oneshot(self, prompt: str, timeout_sec: Optional[float] = None) -> str:
        """Executes a single prompt via the official `hermes -z <prompt>` CLI option.

        Note: `hermes -z` prints ONLY the final response text to stdout.
        """
        if not self.cli_bin:
            raise HermesUnavailableError("Hermes CLI executable 'hermes' not found on PATH.")

        timeout = timeout_sec or self.timeout_seconds
        cmd = [self.cli_bin, "-z", prompt]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            if proc.returncode == 0 and proc.stdout.strip():
                return proc.stdout.strip()
            err_msg = proc.stderr.strip() or f"Process exited with code {proc.returncode}"
            raise HermesAPIError(proc.returncode, err_msg)
        except subprocess.TimeoutExpired as exc:
            raise HermesTimeoutError(f"Hermes CLI execution timed out after {timeout}s") from exc
        except Exception as exc:
            raise HermesUnavailableError(f"Hermes CLI invocation failed: {exc}") from exc


_client_instance: Optional[HermesClient] = None


def get_hermes_client() -> HermesClient:
    global _client_instance
    if _client_instance is None:
        _client_instance = HermesClient()
    return _client_instance
