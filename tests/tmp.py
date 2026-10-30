# )
import os
import ssl
import uuid

import httpx
import requests
import truststore
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage

# ====================
# User Configuration Section
# ====================
# Fill in these values before running the script
load_dotenv()

# The base URL should point to the root of the API, not the /v1/api/v1 path
# MODEL = "Gemini-2.5-pro"
# MODEL = "Gemini-3.5-flash"
MODEL = "GPT-4.1-nano"
# MODEL = "Gemini-2.5-flash-lite"
# e.g. UAT GCP Chat Completion URL: "https://gaip-api-uat.hsbc-12152296-gaipuat-dev.dev.gcp.cloud.hk.hsbc/etiv-ssvc-aigateway-..."
BASE_URL = "https://gaip-api-uat.hsbc-12152296-gaipuat-dev.dev.gcp.cloud.hk.hsbc/etiv-ssvc-aigateway-ea-chatcompletion-uat-int..."

# e.g. UCXXXXXXX
USER_ID = "UC0003983"
# USER_ID = "UC000047xx"
AUTH_METHOD = os.getenv("AUTH_METHOD", "B2B")  # Default to B2B

# B2B Service Account Credentials
SERVICE_ACCOUNT = "HK-SVCAT-IPO-DEV"
PASSWORD = "75FJ1-f88dCD482"
I2B2_DSP_URL = "https://cmb-i2b2-dsp-pprod-ap.hk.hsbc:8443/dsp/rest-sts/DSP_I2B2/token?sBC=864;action=translate"

# S2B Session Token
AWSTOKEN = os.getenv("AWSTOKEN", "")
# ====================
# HTTP Client Setup
# ====================
ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
httpx_client = httpx.Client(http2=True, verify=ctx)

# ====================
# HTTP Client Setup
# ====================
ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
httpx_client = httpx.Client(http2=True, verify=ctx)


def _get_service_account_jwt(service_account: str, password: str):
    """Fetches a JWT from the B2B DSP service."""

    print("here jwt")
    payload = {
        "input_token_state": {
            "token_type": "CREDENTIAL",
            "username": service_account,
            "password": password,
        },
        "output_token_state": {"token_type": "JWT"},
    }
    resp = httpx_client.post(I2B2_DSP_URL, json=payload, timeout=300)
    resp.raise_for_status()
    data = resp.json()
    jwt = data.get("issued_token")
    if not jwt:
        raise RuntimeError(f"JWT not found in response: {data}")
    print("this is jwt")
    return jwt


jwt = _get_service_account_jwt(SERVICE_ACCOUNT, PASSWORD)

# Service Account Authentication
headers = {
    "X-HSBC-E2E-Trust-Token": jwt,
    "Content-Type": "application/json",
    "x-correlation-id": str(uuid.uuid4()),
    "x-usersession-id": str(uuid.uuid4()),
}

# ====================
# Request Data
# ====================
# Replace with your model name and content
data = {
    "model": MODEL,
    "messages": [{"role": "user", "content": "歌词, 给一首热门歌曲的歌词，用中文"}],
    "max_tokens": 10000,
    "user": USER_ID,
    "stream": True,
}

response = requests.post(BASE_URL, headers=headers, json=data)
