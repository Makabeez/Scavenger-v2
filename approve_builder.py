import os
import json
import requests
from dotenv import load_dotenv
from signing import get_keypair, get_public_key, sign_payload

load_dotenv()

PRIVATE_KEY = os.getenv("PRIVATE_KEY", "")
ENVIRONMENT = os.getenv("ENVIRONMENT", "testnet")

if ENVIRONMENT == "testnet":
    REST_URL = "https://test-api.pacifica.fi/api/v1"
else:
    REST_URL = "https://api.pacifica.fi/api/v1"

keypair = get_keypair(PRIVATE_KEY)
public_key = get_public_key(keypair)

BUILDER_CODE = "makabeez"
MAX_FEE_RATE = "0.001"

print(f"Approving builder code {BUILDER_CODE} for {public_key[:12]}...")

operation_data = {
    "builder_code": BUILDER_CODE,
    "max_fee_rate": MAX_FEE_RATE,
}

signed_request = sign_payload(
    keypair=keypair,
    operation_type="approve_builder_code",
    operation_data=operation_data,
)

url = f"{REST_URL}/account/builder_codes/approve"
resp = requests.post(url, json=signed_request, headers={"Content-Type": "application/json"}, timeout=10)

print(f"Status: {resp.status_code}")
print(json.dumps(resp.json(), indent=2))
