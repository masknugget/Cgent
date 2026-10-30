"""OpenAI SDK client lifecycle and chat model construction."""

from openai import AsyncOpenAI

from cgent.config import Settings
from cgent.models.openai_chat import OpenAIChatModel


class ModelFactory:
    def __init__(self, settings: Settings) -> None:
        self._client = AsyncOpenAI(
            api_key=settings.model_api_key,
            base_url=settings.model_base_url,
            timeout=settings.model_timeout_seconds,
            max_retries=settings.model_max_retries,
        )
        self.model = OpenAIChatModel(client=self._client, model_name=settings.model)

    async def aclose(self) -> None:
        await self._client.close()
