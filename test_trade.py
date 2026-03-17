"""
Manual Test Trade - Pacifica Testnet
Run this to verify signing + order execution works before enabling the bot.

Usage: python3 test_trade.py
"""

import os
import json
import uuid
import requests
from dotenv import load_dotenv
from signing import get_keypair, get_public_key, sign_payload

load_dotenv()

PRIVATE_KEY = os.getenv("PRIVATE_KEY", "")
ENVIRONMENT = os.getenv("ENVIRONMENT", "testnet")
BUILDER_CODE = os.getenv("BUILDER_CODE", "")

if ENVIRONMENT == "testnet":
    REST_URL = "https://test-api.pacifica.fi/api/v1"
else:
    REST_URL = "https://api.pacifica.fi/api/v1"

# Initialize keypair
keypair = get_keypair(PRIVATE_KEY)
public_key = get_public_key(keypair)

print("=" * 60)
print("  🧪 MANUAL TEST TRADE — Pacifica Testnet")
print("=" * 60)
print(f"  Wallet:  {public_key[:12]}...{public_key[-6:]}")
print(f"  REST:    {REST_URL}")
print(f"  Builder: {BUILDER_CODE or '(none)'}")
print("=" * 60)


# ─── Test 1: Check account info (GET - no signing needed) ───────
print("\n📋 TEST 1: Fetching account info...")
try:
    url = f"{REST_URL}/account?account={public_key}"
    resp = requests.get(url, timeout=10)
    print(f"   Status: {resp.status_code}")
    data = resp.json()
    print(f"   Response: {json.dumps(data, indent=2)[:500]}")
except Exception as e:
    print(f"   ❌ Error: {e}")


# ─── Test 2: Check positions (GET) ──────────────────────────────
print("\n📋 TEST 2: Fetching positions...")
try:
    url = f"{REST_URL}/positions?account={public_key}"
    resp = requests.get(url, timeout=10)
    print(f"   Status: {resp.status_code}")
    data = resp.json()
    print(f"   Response: {json.dumps(data, indent=2)[:500]}")
except Exception as e:
    print(f"   ❌ Error: {e}")


# ─── Test 3: Get SOL market price (GET) ─────────────────────────
print("\n📋 TEST 3: Fetching SOL price...")
sol_price = 0
try:
    url = f"{REST_URL}/markets/ticker?symbol=SOL"
    resp = requests.get(url, timeout=10)
    print(f"   Status: {resp.status_code}")
    data = resp.json()
    print(f"   Response: {json.dumps(data, indent=2)[:500]}")
    # Try to extract price
    if isinstance(data, dict):
        sol_price = float(data.get("last_price", 0) or data.get("mark_price", 0) or 0)
    if sol_price == 0 and isinstance(data, list) and len(data) > 0:
        sol_price = float(data[0].get("last_price", 0) or data[0].get("mark_price", 0) or 0)
    print(f"   SOL Price: ${sol_price}")
except Exception as e:
    print(f"   ❌ Error: {e}")


# ─── Test 4: Place a tiny market order (POST - requires signing) ─
print("\n" + "=" * 60)
print("  🔫 TEST 4: Placing a TINY market BUY order")
print("  Symbol: SOL | Side: bid | Amount: ~$5 worth")
print("=" * 60)

if sol_price == 0:
    print("   ⚠️  Could not get SOL price. Using fallback $130")
    sol_price = 130.0

# Calculate a tiny amount (~$5 worth)
trade_amount_usd = 15.0
amount = str(round(trade_amount_usd / sol_price, 2))

operation_data = {
    "symbol": "SOL",
    "amount": amount,
    "side": "bid",
    "slippage_percent": "1.0",
    "reduce_only": False,
    "client_order_id": str(uuid.uuid4()),
}

if BUILDER_CODE:
    operation_data["builder_code"] = BUILDER_CODE

print(f"\n   Order payload:")
print(f"   {json.dumps(operation_data, indent=2)}")

confirm = input("\n   ⚠️  Send this order? (yes/no): ").strip().lower()
if confirm != "yes":
    print("   Cancelled.")
    exit()

print("\n   📡 Signing and sending...")

signed_request = sign_payload(
    keypair=keypair,
    operation_type="create_market_order",
    operation_data=operation_data,
)

print(f"   Signed request (preview):")
preview = {k: v for k, v in signed_request.items() if k != "signature"}
preview["signature"] = signed_request.get("signature", "")[:20] + "..."
print(f"   {json.dumps(preview, indent=2)}")

try:
    url = f"{REST_URL}/orders/create_market"
    resp = requests.post(
        url,
        json=signed_request,
        headers={"Content-Type": "application/json"},
        timeout=15,
    )
    
    print(f"\n   Status: {resp.status_code}")
    result = resp.json()
    print(f"   Response: {json.dumps(result, indent=2)[:800]}")
    
    if resp.status_code == 200:
        print("\n   ✅ SUCCESS! Order went through!")
        print("   Your signing, API connection, and account are all working.")
    else:
        print(f"\n   ❌ Order failed with status {resp.status_code}")
        print("   Check the error message above for details.")
        
except Exception as e:
    print(f"\n   ❌ Request error: {e}")

print("\n" + "=" * 60)
print("  Test complete. Check the Pacifica testnet UI to verify.")
print("=" * 60)
