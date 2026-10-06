import os
import time
from dotenv import load_dotenv
from groq import Groq
from typing import Any, Dict, List

from agents import ai_observability

load_dotenv()

class GroqChatClient:
    """Wrapper for Groq chat completions."""

    def __init__(self):
        self.api_key = os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError("GROQ_API_KEY not found in environment variables")

        self.model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
        self.client = Groq(api_key=self.api_key)
        print(f"[OK] GroqChatClient initialized with model: {self.model}")

    def create_chat_completion(self, messages: List[Dict[str, str]], max_tokens: int = 1024, temperature: float = 0.7) -> str:
        # E7 (D42): o usage de cada chamada é persistido aqui, com latência e custo. O contexto (canal,
        # usuário, sessão, tipo de chamada) vem por contextvars. A exceção do SDK é relançada como antes
        # (o contrato da E6 continua) e o texto dela nunca é gravado.
        inicio = time.perf_counter()
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_completion_tokens=max_tokens,
                top_p=1,
                reasoning_effort="medium",
                stream=False,
                stop=None,
            )
        except Exception:
            ai_observability.registrar_uso(self.model, "error", self._latencia_ms(inicio))
            raise
        prompt_tokens, completion_tokens, total_tokens = ai_observability.tokens_do_usage(response)
        ai_observability.registrar_uso(
            self.model, "ok", self._latencia_ms(inicio), prompt_tokens, completion_tokens, total_tokens
        )
        return self._extract_text(response)

    @staticmethod
    def _latencia_ms(inicio: float) -> int:
        return int(round((time.perf_counter() - inicio) * 1000))

    def _extract_text(self, response: Any) -> str:
        if hasattr(response, "choices"):
            choices = response.choices
            if choices:
                first_choice = choices[0]
                if hasattr(first_choice, "message"):
                    message = first_choice.message
                    if isinstance(message, dict):
                        return message.get("content", "")
                    if hasattr(message, "get"):
                        return message.get("content", "")
                    return getattr(message, "content", "")
                if hasattr(first_choice, "text"):
                    return getattr(first_choice, "text", "")
        if isinstance(response, dict):
            # Fallback for dict-like responses
            first_choice = response.get("choices", [{}])[0]
            message = first_choice.get("message") if isinstance(first_choice, dict) else None
            if isinstance(message, dict):
                return message.get("content", "")
            return first_choice.get("text", "") if isinstance(first_choice, dict) else ""
        return str(response)
