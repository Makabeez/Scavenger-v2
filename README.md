🦅 The Scavenger — Pacifica Liquidation Sniper
Real-time liquidation detection and automated counter-trading on Pacifica's perpetuals infrastructure.
Afficher l'image
Afficher l'image
Afficher l'image
Afficher l'image

Overview
The Scavenger is a hackathon submission for the Pacifica Hackathon (Trading Applications & Bots track).
Most trading bots use lagging indicators to predict price direction. The Scavenger takes a fundamentally different approach: it reacts to forced market events. When a trader gets liquidated on Pacifica, the exchange engine forcibly closes their position, creating an artificial price wick. The Scavenger detects these events in real-time and fires a counter-trade to capture the mean-reversion bounce.
How it works: Pacifica's WebSocket trades channel includes a tc (trade cause) field on every trade. When tc equals market_liquidation or backstop_liquidation, the bot knows this isn't organic price action — it's a forced close. A long liquidation (close_long) means forced selling, so the bot buys the dip. A short liquidation (close_short) means forced buying, so the bot sells the spike.

Architecture
┌─────────────────────────────────────┐
│   DigitalOcean Droplet (Frankfurt)  │
│                                     │
│  Python Bot                         │
│  ├─ WS: trades channel (SOL)       │
│  ├─ Filter: tc=market_liquidation   │
│  ├─ Execute: signed market orders   │
│  └─ Relay: WS server on :8080      │
└──────────────┬──────────────────────┘
               │
    WebSocket + REST (Ed25519 signed)
               │
┌──────────────▼──────────────────────┐
│        Pacifica Exchange            │
│  REST:  api.pacifica.fi/api/v1      │
│  WS:    ws.pacifica.fi/ws           │
│  Auth:  Ed25519 / Solana keypair    │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│     Vercel Edge Network             │
│  React Dashboard                    │
│  ├─ Connects to bot relay WS       │
│  ├─ Live liquidation feed           │
│  └─ Sniped trade visualization      │
└─────────────────────────────────────┘

Technical Implementation
Liquidation Detection
Pacifica does not expose a dedicated liquidation WebSocket channel. The Scavenger subscribes to the public trades channel and filters by the tc field:
json{
  "channel": "trades",
  "data": [{
    "s": "SOL",
    "a": "500.5",
    "p": "132.45",
    "d": "close_long",
    "tc": "market_liquidation",
    "t": 1773788264586
  }]
}
When tc is market_liquidation or backstop_liquidation and the notional value (a × p) exceeds the configured threshold ($50,000), the bot executes a counter-trade.
Order Execution & Signing
All POST requests to Pacifica require Ed25519 signatures using a Solana keypair. The signing process follows the official Pacifica specification:

Build signature header with millisecond timestamp
Combine header with operation data
Recursively sort all JSON keys alphabetically
Create compact JSON with no whitespace
Sign UTF-8 bytes with Ed25519 private key
Encode signature as Base58

Orders are placed via POST /api/v1/orders/create_market with the create_market_order operation type.
Snipe Logic
Liquidation TypeDirectionPrice EffectBot ActionLong liquidatedclose_longForced selling → price dipsBuy (bid)Short liquidatedclose_shortForced buying → price spikesSell (ask)
After each snipe, the bot enters a 10-second cooldown to prevent over-exposure during cascading liquidations.

Stack
Execution Engine (DigitalOcean FRA1)

Language: Python 3.12
WebSocket: websockets library for persistent connection to wss://ws.pacifica.fi/ws
Signing: solders (Solana keypair) + base58 for Ed25519 signature generation
REST Client: requests for order submission to Pacifica REST API
Process Manager: PM2 (daemonized, auto-restart)
Relay: Built-in WebSocket server broadcasting filtered events to the dashboard

Intel Dashboard (Vercel)

Framework: React 18 + Vite 8
Styling: Tailwind CSS v4
Typography: Inter (UI) + JetBrains Mono (financial data)
Icons: Lucide React
Connection: WebSocket relay from backend for live event streaming
Demo Mode: Built-in crash simulator for presentations

Pacifica Integration

WebSocket: Trades channel subscription with tc field filtering
REST: Market order creation with Ed25519 signed payloads
Builder Program: Builder code (makabeez) included in all mainnet orders
Testnet: Full testnet support via test-api.pacifica.fi / test-ws.pacifica.fi


Live Demo
Dashboard: https://scavenger-ui.vercel.app
The dashboard includes a "Demo Crash" button that simulates a liquidation cascade, showing how the bot identifies large liquidations and marks them as sniped. When connected to the live backend, real liquidation events from Pacifica appear in the feed.

Local Setup
Backend (Bot)
bashgit clone https://github.com/YOUR_USERNAME/scavenger-v2.git
cd scavenger-v2

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.template .env
# Edit .env with your Solana private key

python3 bot.py
Frontend (Dashboard)
bashcd scavenger-ui

npm install --legacy-peer-deps
echo "VITE_RELAY_URL=ws://localhost:8080" > .env.local

npm run dev

Project Structure
scavenger-v2/                 # Backend (DigitalOcean)
├── bot.py                    # Main bot: WS listener + trade execution + relay server
├── signing.py                # Ed25519 signing (Pacifica spec)
├── test_trade.py             # Manual trade verification script
├── approve_builder.py        # Builder code approval utility
├── requirements.txt          # Python dependencies
├── ecosystem.config.js       # PM2 process manager config
└── .env.template             # Configuration template

scavenger-ui/                 # Frontend (Vercel)
├── src/
│   ├── App.tsx               # Dashboard with live feed + demo mode
│   └── index.css             # Tailwind v4 + custom fonts
├── .env.local                # Relay URL config
└── vite.config.ts            # Vite + Tailwind plugin

Hackathon Track & Criteria

Track: Trading Applications & Bots
Innovation: Liquidation-driven reactive trading using undocumented tc field filtering, not lagging indicators
Technical Execution: Ed25519 signing from scratch, real API integration, dual-layer architecture
User Experience: Real-time dashboard with live data relay and demo mode
Potential Impact: Automated yield from forced liquidation events — a strategy used by institutional HFT firms
Builder Program: All mainnet orders routed through registered builder code makabeez


License
MIT — Built for the Pacifica Hackathon 2026.
