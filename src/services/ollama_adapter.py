"""
Local Ollama LLM Adapter with Resilient Deterministic Fallback.
Connects to Ollama and selects an installed local model for optional narration,
with automatic fallback to deterministic diagnostics when generation is unavailable.
"""

from typing import Any, Dict, Optional
import httpx

from src.config import settings

OLLAMA_BASE_URL = settings.ollama_base_url
DEFAULT_MODEL = settings.ollama_model


class OllamaAdapter:
    def __init__(self, base_url: str = OLLAMA_BASE_URL, default_model: str = DEFAULT_MODEL):
        self.base_url = base_url
        self.default_model = default_model
        self.timeout_sec = 35.0

    async def check_health(self) -> Dict[str, Any]:
        """Checks if local Ollama daemon is reachable and lists pulled models."""
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.get(f"{self.base_url}/api/tags")
                if res.status_code == 200:
                    data = res.json()
                    if not isinstance(data, dict) or not isinstance(data.get("models"), list):
                        raise ValueError("Invalid model inventory")
                    models = [m["name"] for m in data["models"]
                              if isinstance(m, dict) and isinstance(m.get("name"), str) and m["name"].strip()]
                    expected_model = self.default_model if ":" in self.default_model else f"{self.default_model}:latest"
                    active_model = next((m for m in models if m == expected_model or m == self.default_model), models[0] if models else self.default_model)
                    has_default_model = active_model in {self.default_model, expected_model} and bool(models)
                    return {
                        "is_online": True,
                        "base_url": self.base_url,
                        "available_models": models,
                        "has_default_model": has_default_model,
                        "selected_model": active_model,
                        "can_generate": bool(models),
                        "note": None if models else "Ollama is reachable but has no installed models; deterministic diagnostics remain available."
                    }
        except Exception:
            pass

        return {
            "is_online": False,
            "base_url": self.base_url,
            "available_models": [],
            "has_default_model": False,
            "selected_model": self.default_model,
            "can_generate": False,
            "note": "Local Ollama daemon is offline or unreachable. Platform will use high-speed Deterministic Heuristic Synthesizer."
        }

    async def generate_response(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.1
    ) -> Dict[str, Any]:
        """
        Sends prompt to Ollama /api/generate.
        If unavailable or invalid, returns empty content to trigger deterministic fallback.
        """
        target_model = model or (await self.check_health())["selected_model"]
        payload = {
            "model": target_model,
            "prompt": prompt,
            "stream": False,
            "think": False,
            "options": {
                "temperature": temperature,
                "num_predict": 96
            }
        }
        if system_prompt:
            payload["system"] = system_prompt

        error_kind = "unavailable"
        try:
            async with httpx.AsyncClient(timeout=self.timeout_sec) as client:
                res = await client.post(f"{self.base_url}/api/generate", json=payload)
                if res.status_code == 200:
                    data = res.json()
                    content = data.get("response") if isinstance(data, dict) else None
                    if (not isinstance(content, str) or not content.strip() or data.get("done") is False
                            or data.get("done_reason") == "length" or data.get("error")):
                        raise ValueError("Incomplete or invalid model response")
                    return {
                        "content": content.strip(),
                        "model": target_model,
                        "engine": f"Local Ollama ({target_model})",
                        "is_local_llm": True,
                        "eval_count": data.get("eval_count", 0)
                    }
                error_kind = f"http_{res.status_code}"
        except httpx.TimeoutException:
            error_kind = "timeout"
        except httpx.RequestError:
            error_kind = "connection_error"
        except (ValueError, TypeError):
            error_kind = "invalid_response"

        return {
            "content": None,
            "model": target_model,
            "engine": "Deterministic Heuristic Synthesizer (Ollama unavailable)",
            "is_local_llm": False,
            "error": "Ollama narration unavailable; using deterministic diagnostics.",
            "error_kind": error_kind
        }


ollama_adapter = OllamaAdapter()
