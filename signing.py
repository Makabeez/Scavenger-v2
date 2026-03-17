"""
Pacifica Ed25519 Signing Implementation
Based on: https://docs.pacifica.fi/api-documentation/api/signing/implementation
"""

import json
import time
import base58
from solders.keypair import Keypair


def get_keypair(private_key_b58: str) -> Keypair:
    """Generate keypair from Base58 private key."""
    return Keypair.from_bytes(base58.b58decode(private_key_b58))


def get_public_key(keypair: Keypair) -> str:
    """Get Base58 public key string from keypair."""
    return str(keypair.pubkey())


def sort_json_keys(value):
    """Recursively sort all JSON keys alphabetically."""
    if isinstance(value, dict):
        sorted_dict = {}
        for key in sorted(value.keys()):
            sorted_dict[key] = sort_json_keys(value[key])
        return sorted_dict
    elif isinstance(value, list):
        return [sort_json_keys(item) for item in value]
    else:
        return value


def sign_payload(keypair: Keypair, operation_type: str, operation_data: dict, expiry_window: int = 5000) -> dict:
    """
    Create a signed request payload for Pacifica API.
    
    Steps (from docs):
    1. Create signature header with timestamp
    2. Combine header + data
    3. Recursively sort JSON keys
    4. Create compact JSON (no whitespace)
    5. Sign UTF-8 bytes with Ed25519
    6. Build final request
    """
    # Step 1: Signature header
    timestamp = int(time.time() * 1000)
    signature_header = {
        "timestamp": timestamp,
        "expiry_window": expiry_window,
        "type": operation_type,
    }

    # Step 2: Combine header and payload
    data_to_sign = {
        **signature_header,
        "data": operation_data,
    }

    # Step 3: Recursively sort
    sorted_message = sort_json_keys(data_to_sign)

    # Step 4: Compact JSON
    compact_json = json.dumps(sorted_message, separators=(",", ":"))

    # Step 5: Sign
    message_bytes = compact_json.encode("utf-8")
    signature = keypair.sign_message(message_bytes)
    signature_b58 = base58.b58encode(bytes(signature)).decode("ascii")

    # Step 6: Build final request
    public_key = str(keypair.pubkey())
    request = {
        "account": public_key,
        "agent_wallet": None,
        "signature": signature_b58,
        "timestamp": timestamp,
        "expiry_window": expiry_window,
        **operation_data,
    }

    return request
