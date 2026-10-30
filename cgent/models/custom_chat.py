"""HSBC GAIP chat completion adapter with hardcoded B2B service account auth.

Configuration is intentionally hardcoded in this module instead of living in
``.env``/``Settings``: the target gateway, credentials and identity are fixed
for this deployment. Only the generic request timeout comes from ``Settings``.
"""

import asyncio
import ssl
import uuid
from typing import Any

import httpx
import requests
import truststore
from langchain_core.callbacks import AsyncCallbackManagerForLLMRun
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatResult

from cgent.errors import ModelUnavailableError
from cgent.models.http_chat import OpenAICompatibleHTTPModel
from cgent.models.openai_messages import to_openai_messages

# ====================
# Hardcoded Configuration
# ====================
MODEL = "GPT-4.1-nano"
# Full chat completion endpoint; NOT suffixed with /chat/completions.
# TODO: tmp.py 中该地址被截断，部署前补全完整 URL。
BASE_URL = "https://gaip-api-uat.hsbc-12152296-gaipuat-dev.dev.gcp.cloud.hk.hsbc/etiv-ssvc-aigateway-ea-chatcompletion-uat-int..."
# e.g. UCXXXXXXX
USER_ID = "UC0003983"

# B2B Service Account Credentials
SERVICE_ACCOUNT = "HK-SVCAT-IPO-DEV"
PASSWORD = "75FJ1-f88dCD482"
TOKEN_URL = "https://cmb-i2b2-dsp-pprod-ap.hk.hsbc:8443/dsp/rest-sts/DSP_I2B2/token?sBC=864;action=translate"

MAX_TOKENS = 10000

_TOKEN_CLIENT: httpx.Client | None = None


def _token_client() -> httpx.Client:
    global _TOKEN_CLIENT
    if _TOKEN_CLIENT is None:
        ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        _TOKEN_CLIENT = httpx.Client(http2=True, verify=ctx)
    return _TOKEN_CLIENT


def _get_service_account_jwt() -> str:
    """Fetches a JWT from the B2B DSP service."""
    payload = {
        "input_token_state": {
            "token_type": "CREDENTIAL",
            "username": SERVICE_ACCOUNT,
            "password": PASSWORD,
        },
        "output_token_state": {"token_type": "JWT"},
    }
    try:
        response = _token_client().post(TOKEN_URL, json=payload, timeout=300)
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ModelUnavailableError("The token request failed") from exc
    jwt = data.get("issued_token") if isinstance(data, dict) else None
    if not jwt:
        raise ModelUnavailableError(f"JWT not found in response: {data}")
    return jwt


class CustomChatModel(OpenAICompatibleHTTPModel):
    """GAIP chat completion client using B2B service account JWT auth.

    Reuses the OpenAI-compatible payload/response handling from
    :class:`OpenAICompatibleHTTPModel`; only authentication and the endpoint
    differ.
    """

    api_key: str = ""  # Unused: the gateway trusts the DSP JWT instead.
    base_url: str = BASE_URL
    model_name: str = MODEL
    timeout_seconds: float = 600

    @property
    def _llm_type(self) -> str:
        return "cgent-custom"

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        request: dict[str, Any] = {
            "model": self.model_name,
            "messages": to_openai_messages(messages),
            "max_tokens": MAX_TOKENS,
            "user": USER_ID,
            "stream": False,
            **kwargs,
        }
        if stop:
            request["stop"] = stop

        jwt = await asyncio.to_thread(_get_service_account_jwt)
        headers = {
            "X-HSBC-E2E-Trust-Token": jwt,
            "Content-Type": "application/json",
            "x-correlation-id": str(uuid.uuid4()),
            "x-usersession-id": str(uuid.uuid4()),
        }

        def call_provider() -> requests.Response:
            return requests.post(
                url=self.base_url,
                headers=headers,
                json=request,
                timeout=self.timeout_seconds,
            )

        try:
            response = await asyncio.to_thread(call_provider)
        except requests.RequestException as exc:
            raise ModelUnavailableError("The model request failed") from exc
        if response.status_code >= 400:
            raise ModelUnavailableError(f"The model provider returned HTTP {response.status_code}")
        try:
            data = response.json()
        except ValueError as exc:
            raise ModelUnavailableError("The model provider returned invalid JSON") from exc
        return self._result_from_payload(data)
