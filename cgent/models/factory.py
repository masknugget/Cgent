"""Chat model construction and owned client lifecycle."""

from openai import AsyncOpenAI

from cgent.config import Settings
from cgent.models.custom_chat import CustomChatModel
from cgent.models.http_chat import OpenAICompatibleHTTPModel
from cgent.models.openai_chat import OpenAIChatModel


class ModelFactory:
    def __init__(self, settings: Settings) -> None:
        self._client: AsyncOpenAI | None = None
        if settings.model_adapter == "http":
            self.model = OpenAICompatibleHTTPModel(
                api_key=settings.model_api_key,
                base_url=settings.model_base_url,
                model_name=settings.model,
                timeout_seconds=settings.model_timeout_seconds,
            )
            return
        if settings.model_adapter == "custom":
            self.model = CustomChatModel(timeout_seconds=settings.model_timeout_seconds)
            return
        self._client = AsyncOpenAI(
            api_key=settings.model_api_key,
            base_url=settings.model_base_url,
            timeout=settings.model_timeout_seconds,
            max_retries=settings.model_max_retries,
        )
        self.model = OpenAIChatModel(client=self._client, model_name=settings.model)

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.close()
