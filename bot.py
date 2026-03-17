"""
The Scavenger v2 - Pacifica Liquidation Sniper
Built on REAL Pacifica API documentation.

Strategy:
- Subscribe to the 'trades' WebSocket channel
- Filter for trades where tc = "market_liquidation" or "backstop_liquidation"  
- When a large liquidation trade occurs, execute a counter-trade
- A liquidation that closes a long (close_long) = forced selling = we BUY the dip
- A liquidation that closes a short (close_short) = forced buying = we SELL the spike
"""

import os
import sys
import json
import time
import uuid
import asyncio
import logging
from datetime import datetime

import websockets
import requests
from dotenv import load_dotenv

from signing import get_keypair, get_public_key, sign_payload

# ─── Configuration ───────────────────────────────────────────────
load_dotenv()

PRIVATE_KEY = os.getenv("PRIVATE_KEY", "")
ENVIRONMENT = os.getenv("ENVIRONMENT", "testnet")
TARGET_SYMBOL = os.getenv("TARGET_SYMBOL", "SOL")
MIN_LIQUIDATION_NOTIONAL = float(os.getenv("MIN_LIQUIDATION_NOTIONAL", "50000"))
TRADE_AMOUNT_USD = float(os.getenv("TRADE_AMOUNT_USD", "500"))
SLIPPAGE_PERCENT = os.getenv("SLIPPAGE_PERCENT", "0.5")
BUILDER_CODE = os.getenv("BUILDER_CODE", "")
RELAY_PORT = int(os.getenv("RELAY_PORT", "8080"))

# URL mapping
if ENVIRONMENT == "testnet":
    WS_URL = "wss://test-ws.pacifica.fi/ws"
    REST_URL = "https://test-api.pacifica.fi/api/v1"
else:
    WS_URL = "wss://ws.pacifica.fi/ws"
    REST_URL = "https://api.pacifica.fi/api/v1"

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("scavenger")

# ─── State ───────────────────────────────────────────────────────
keypair = None
public_key = ""
is_trading = False
trade_cooldown = 10  # seconds between trades

# Event history for the relay/frontend
event_log = []
MAX_EVENTS = 100

# Connected frontend WebSocket clients
frontend_clients = set()


def add_event(event_type: str, data: dict):
    """Add event to the log for the frontend relay."""
    entry = {
        "id": str(uuid.uuid4())[:8],
        "type": event_type,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    event_log.insert(0, entry)
    if len(event_log) > MAX_EVENTS:
        event_log.pop()
    
    # Broadcast to connected frontend clients
    msg = json.dumps(entry)
    for client in list(frontend_clients):
        try:
            asyncio.ensure_future(client.send(msg))
        except Exception:
            frontend_clients.discard(client)


# ─── Trading Logic ───────────────────────────────────────────────

def execute_market_order(side: str, symbol: str, amount_usd: float, price: float):
    """
    Execute a market order via Pacifica REST API.
    
    Endpoint: POST /api/v1/orders/create_market
    Operation type: create_market_order
    """
    global is_trading
    
    # Calculate amount in base asset
    amount = str(round(amount_usd / price, 2))
    
    operation_data = {
        "symbol": symbol,
        "amount": amount,
        "side": side,  # "bid" to buy, "ask" to sell
        "slippage_percent": SLIPPAGE_PERCENT,
        "reduce_only": False,
        "client_order_id": str(uuid.uuid4()),
    }
    
    # Add builder code if configured
    if BUILDER_CODE:
        operation_data["builder_code"] = BUILDER_CODE
    
    # Sign the request
    signed_request = sign_payload(
        keypair=keypair,
        operation_type="create_market_order",
        operation_data=operation_data,
    )
    
    log.info(f"📡 Sending {side.upper()} market order: {amount} {symbol} (~${amount_usd})")
    
    try:
        url = f"{REST_URL}/orders/create_market"
        response = requests.post(
            url,
            json=signed_request,
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        
        result = response.json()
        
        if response.status_code == 200:
            log.info(f"✅ Order executed! Response: {json.dumps(result)[:200]}")
            add_event("trade_executed", {
                "side": side,
                "symbol": symbol,
                "amount": amount,
                "price": str(price),
                "order_response": result,
            })
        else:
            log.error(f"❌ Order failed [{response.status_code}]: {json.dumps(result)[:300]}")
            add_event("trade_failed", {
                "side": side,
                "symbol": symbol,
                "error": str(result),
            })
    except Exception as e:
        log.error(f"❌ Request error: {e}")
        add_event("trade_error", {"error": str(e)})


def handle_liquidation_trade(trade: dict):
    """
    Process a trade that was caused by a liquidation.
    
    Trade data fields (from Pacifica docs):
    - s: symbol (e.g. "SOL")
    - a: amount (decimal string)  
    - p: price (decimal string)
    - d: trade side ("open_long", "open_short", "close_long", "close_short")
    - tc: trade cause ("normal", "market_liquidation", "backstop_liquidation", "settlement")
    - t: timestamp in milliseconds
    """
    global is_trading
    
    symbol = trade.get("s", "")
    amount_str = trade.get("a", "0")
    price_str = trade.get("p", "0")
    direction = trade.get("d", "")
    trade_cause = trade.get("tc", "")
    
    try:
        amount = float(amount_str)
        price = float(price_str)
    except (ValueError, TypeError):
        return
    
    notional = amount * price
    
    # Log ALL liquidation trades (even small ones) for the dashboard
    add_event("liquidation", {
        "symbol": symbol,
        "direction": direction,
        "price": price_str,
        "amount": amount_str,
        "notional": round(notional, 2),
        "cause": trade_cause,
        "sniped": False,
    })
    
    # Filter: only target symbol and minimum size
    if symbol != TARGET_SYMBOL:
        return
    
    if notional < MIN_LIQUIDATION_NOTIONAL:
        log.info(f"⚡ Liquidation detected: {symbol} {direction} ${notional:.0f} — too small, ignoring")
        return
    
    log.warning(f"🚨 MASSIVE LIQUIDATION: {symbol} {direction} ${notional:.0f} at ${price}")
    
    if is_trading:
        log.info("⏳ Already in a trade, skipping...")
        return
    
    is_trading = True
    
    # Determine counter-trade side:
    # close_long liquidation = forced selling = price dips = we BUY (bid)
    # close_short liquidation = forced buying = price spikes = we SELL (ask)
    if direction in ("close_long",):
        snipe_side = "bid"  # buy the dip
    elif direction in ("close_short",):
        snipe_side = "ask"  # sell the spike
    else:
        log.info(f"Unexpected liquidation direction: {direction}, skipping")
        is_trading = False
        return
    
    log.info(f"🔫 SNIPING: {snipe_side.upper()} {symbol} at ~${price}")
    
    # Update the last event to mark it as sniped
    if event_log and event_log[0]["type"] == "liquidation":
        event_log[0]["data"]["sniped"] = True
    
    execute_market_order(snipe_side, symbol, TRADE_AMOUNT_USD, price)
    
    # Cooldown
    async def reset_trading():
        await asyncio.sleep(trade_cooldown)
        global is_trading
        is_trading = False
        log.info("🔓 Ready for next snipe")
    
    asyncio.ensure_future(reset_trading())


# ─── WebSocket Connection ────────────────────────────────────────

async def connect_pacifica():
    """Connect to Pacifica WebSocket and subscribe to trades."""
    
    while True:
        try:
            log.info(f"🔌 Connecting to {WS_URL}...")
            
            async with websockets.connect(WS_URL, ping_interval=30, ping_timeout=10) as ws:
                log.info(f"✅ Connected to Pacifica {ENVIRONMENT.upper()}")
                
                # Subscribe to trades for the target symbol
                subscribe_msg = {
                    "method": "subscribe",
                    "params": {
                        "source": "trades",
                        "symbol": TARGET_SYMBOL,
                    }
                }
                await ws.send(json.dumps(subscribe_msg))
                log.info(f"📡 Subscribed to trades for {TARGET_SYMBOL}")
                
                add_event("status", {"message": f"Connected to {ENVIRONMENT}", "connected": True})
                
                # Set up heartbeat
                async def heartbeat():
                    while True:
                        try:
                            await asyncio.sleep(30)
                            await ws.send(json.dumps({"method": "ping"}))
                        except Exception:
                            break
                
                heartbeat_task = asyncio.create_task(heartbeat())
                
                # Process messages
                async for message in ws:
                    try:
                        data = json.loads(message)
                        
                        # Skip pong responses
                        if data.get("channel") == "pong":
                            continue
                        
                        # Process trade messages
                        if data.get("channel") == "trades":
                            trades = data.get("data", [])
                            for trade in trades:
                                tc = trade.get("tc", "normal")
                                if tc in ("market_liquidation", "backstop_liquidation"):
                                    handle_liquidation_trade(trade)
                    
                    except json.JSONDecodeError:
                        continue
                    except Exception as e:
                        log.error(f"Message processing error: {e}")
                
                heartbeat_task.cancel()
        
        except websockets.ConnectionClosed as e:
            log.warning(f"⚠️ WS disconnected: {e}. Reconnecting in 3s...")
            add_event("status", {"message": "Disconnected", "connected": False})
        except Exception as e:
            log.error(f"❌ WS error: {e}. Reconnecting in 5s...")
            add_event("status", {"message": f"Error: {e}", "connected": False})
        
        await asyncio.sleep(3)


# ─── Frontend Relay WebSocket Server ─────────────────────────────

async def frontend_relay_handler(websocket, path=None):
    """Handle frontend WebSocket connections for the dashboard."""
    frontend_clients.add(websocket)
    log.info(f"🖥️ Frontend client connected ({len(frontend_clients)} total)")
    
    try:
        # Send current event history on connect
        await websocket.send(json.dumps({
            "type": "history",
            "data": event_log[:50],
        }))
        
        # Keep connection alive
        async for message in websocket:
            pass
    except websockets.ConnectionClosed:
        pass
    finally:
        frontend_clients.discard(websocket)
        log.info(f"🖥️ Frontend client disconnected ({len(frontend_clients)} total)")


async def start_relay_server():
    """Start the WebSocket relay server for the frontend dashboard."""
    server = await websockets.serve(
        frontend_relay_handler,
        "0.0.0.0",
        RELAY_PORT,
    )
    log.info(f"🖥️ Frontend relay server running on ws://0.0.0.0:{RELAY_PORT}")
    return server


# ─── Main ────────────────────────────────────────────────────────

async def main():
    global keypair, public_key
    
    print("=" * 60)
    print("  🦅 THE SCAVENGER v2 — Liquidation Sniper")
    print("  Built on REAL Pacifica API")
    print("=" * 60)
    
    # Validate private key
    if not PRIVATE_KEY or PRIVATE_KEY == "your_solana_private_key_here":
        log.error("❌ Set your PRIVATE_KEY in the .env file!")
        sys.exit(1)
    
    # Initialize keypair
    try:
        keypair = get_keypair(PRIVATE_KEY)
        public_key = get_public_key(keypair)
        log.info(f"🔑 Wallet: {public_key[:8]}...{public_key[-4:]}")
    except Exception as e:
        log.error(f"❌ Invalid private key: {e}")
        sys.exit(1)
    
    log.info(f"🌐 Environment: {ENVIRONMENT.upper()}")
    log.info(f"🎯 Target: {TARGET_SYMBOL} (min ${MIN_LIQUIDATION_NOTIONAL:,.0f} notional)")
    log.info(f"💰 Trade size: ${TRADE_AMOUNT_USD}")
    log.info(f"📡 WS: {WS_URL}")
    log.info(f"🌐 REST: {REST_URL}")
    if BUILDER_CODE:
        log.info(f"🏗️ Builder code: {BUILDER_CODE}")
    print("-" * 60)
    
    # Start both the Pacifica connection and the frontend relay
    relay_server = await start_relay_server()
    await connect_pacifica()


if __name__ == "__main__":
    asyncio.run(main())
