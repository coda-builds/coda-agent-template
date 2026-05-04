"""
OpenRouter API service wrapper.

Provides two methods:
  - chat_completion : multi-turn conversation generation
  - text_completion : single-prompt classification (state transition classifier)

Both methods are async and raise on non-recoverable errors.
OpenRouter exposes an OpenAI-compatible API; this wrapper uses the
official openai Python client pointed at https://openrouter.ai/api/v1.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from openai import AsyncOpenAI
from openai import APIConnectionError, APIStatusError, RateLimitError

from app.config import Settings

logger = logging.getLogger(__name__)


class OpenRouterService:
    """
    Thin async wrapper around the OpenAI client configured for OpenRouter.

    Instantiate once and share across the application lifetime.
    """

    BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(self, settings: Settings) -> None:
        self._client = AsyncOpenAI(
            api_key=settings.openrouter_api_key,
            base_url=self.BASE_URL,
        )
        self._model = settings.llm_model
        self._temperature = settings.llm_temperature
        self._max_tokens = settings.llm_max_tokens

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Generate a conversational reply.

        Args:
            messages:    List of {role, content} dicts (system + history + user).
            temperature: Override the default temperature.
            max_tokens:  Override the default max_tokens.

        Returns:
            The assistant reply as a plain string.

        Raises:
            RuntimeError: On API errors that are not automatically retried.
        """
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,  # type: ignore[arg-type]
                temperature=temperature if temperature is not None else self._temperature,
                max_tokens=max_tokens if max_tokens is not None else self._max_tokens,
            )
            content = response.choices[0].message.content
            if content is None:
                raise RuntimeError("OpenRouter returned an empty response content.")
            return content.strip()

        except RateLimitError as exc:
            logger.error("OpenRouter rate limit exceeded: %s", exc)
            raise RuntimeError("The AI service is temporarily busy. Please try again in a moment.") from exc

        except APIConnectionError as exc:
            logger.error("OpenRouter connection error: %s", exc)
            raise RuntimeError("Could not connect to the AI service. Please check connectivity.") from exc

        except APIStatusError as exc:
            logger.error("OpenRouter API error %d: %s", exc.status_code, exc.message)
            raise RuntimeError(f"AI service error (HTTP {exc.status_code}).") from exc

    async def text_completion(
        self,
        prompt: str,
        *,
        max_tokens: int = 32,
    ) -> str:
        """
        Single-turn completion used for the transition classifier.

        Wraps the prompt in a minimal messages list and uses a lower
        temperature for deterministic classification output.
        """
        messages = [{"role": "user", "content": prompt}]
        return await self.chat_completion(
            messages=messages,
            temperature=0.0,
            max_tokens=max_tokens,
        )

    async def health_check(self) -> bool:
        """
        Return True if OpenRouter is reachable, False otherwise.
        Used by the /health endpoint.
        """
        try:
            await self.text_completion("Reply with the single word: ok", max_tokens=4)
            return True
        except Exception:
            return False
