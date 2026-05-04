import os
from dotenv import load_dotenv
from groq import Groq
from typing import Any, Dict, List

load_dotenv()

class GroqChatClient:
    """Wrapper for Groq chat completions."""

    def __init__(self):
        self.api_key = os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError("GROQ_API_KEY not found in environment variables")

        self.model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
        self.client = Groq(api_key=self.api_key)
        print(f"✅ GroqChatClient initialized with model: {self.model}")

    def create_chat_completion(self, messages: List[Dict[str, str]], max_tokens: int = 1024, temperature: float = 0.7) -> str:
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
        return self._extract_text(response)

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
