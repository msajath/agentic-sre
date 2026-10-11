"""
Local Ollama LLM Adapter with Resilient Deterministic Fallback.
Connects to Ollama (http://localhost:11434) running open-source models (llama3.1),
with automatic fallback to the platform rule engine if Ollama is offline.
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
        self.timeout_sec = 15.0

    async def check_health(self) -> Dict[str, Any]:
        """Checks if local Ollama daemon is reachable and lists pulled models."""
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.get(f"{self.base_url}/api/tags")
                if res.status_code == 200:
                    models = [m.get("name") for m in res.json().get("models", [])]
                    has_llama = any(m.split(":")[0] == self.default_model.split(":")[0] for m in models)
                    active_model = next((m for m in models if m.split(":")[0] == self.default_model.split(":")[0]), models[0] if models else self.default_model)
                    self._active_model = active_model
                    return {
                        "is_online": True,
                        "base_url": self.base_url,
                        "available_models": models,
                        "has_default_model": has_llama,
                        "selected_model": active_model
                    }
        except Exception:
            pass

        return {
            "is_online": False,
            "base_url": self.base_url,
            "available_models": [],
            "has_default_model": False,
            "selected_model": self.default_model,
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
        If offline, gracefully returns None to trigger deterministic fallback.
        """
        target_model = model or getattr(self, "_active_model", self.default_model)
        payload = {
            "model": target_model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": 750
            }
        }
        if system_prompt:
            payload["system"] = system_prompt

        try:
            async with httpx.AsyncClient(timeout=self.timeout_sec) as client:
                res = await client.post(f"{self.base_url}/api/generate", json=payload)
                if res.status_code == 200:
                    data = res.json()
                    return {
                        "content": data.get("response", "").strip(),
                        "model": target_model,
                        "engine": f"Local Ollama ({target_model})",
                        "is_local_llm": True,
                        "eval_count": data.get("eval_count", 0)
                    }
        except Exception:
            # Fallback path
            pass

        return {
            "content": None,
            "model": target_model,
            "engine": "Deterministic Heuristic Synthesizer (Ollama Offline)",
            "is_local_llm": False,
            "error": "Ollama connection timeout or offline"
        }


ollama_adapter = OllamaAdapter()
