import os
import json
import logging
from datetime import datetime
from typing import Dict, List

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

# Configuração básica
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sentinel")

PORT = int(os.getenv("PORT", 8000))

# Cache simples em memória
price_cache: Dict[str, dict] = {}
ws_clients: List[WebSocket] = []

# Cria app
app = FastAPI(title="Sentinel Tactical API", version="1.0.0")

# CORS liberado para todas as origens
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {
        "status": "online",
        "service": "Sentinel Tactical v1.0",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/analyze/{asset}")
async def analyze(asset: str):
    """Análise técnica simplificada"""
    
    # Mapeamento de pares
    symbol_map = {
        "EUR/USD": "EURUSDT",
        "GBP/USD": "GBPUSDT", 
        "USD/JPY": "USDJPY",
        "BTC/USDT": "BTCUSDT",
        "ETH/USDT": "ETHUSDT",
        "AUD/USD": "AUDUSDT",
        "USD/CAD": "USDCAD",
        "XAU/USD": "XAUUSDT"
    }
    
    symbol = symbol_map.get(asset, asset.replace("/", "") + "USDT")
    
    # Busca preço em tempo real
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://api.bybit.com/v5/market/tickers?category=spot&symbol={symbol}",
                timeout=10.0
            )
            data = resp.json()
            
            if data.get("retCode") == 0 and data.get("result", {}).get("list"):
                ticker = data["result"]["list"][0]
                price = float(ticker["lastPrice"])
                change = float(ticker.get("price24hPcnt", 0)) * 100
                
                # RSI simplificado
                rsi = 50 - (change * 2)
                rsi = max(0, min(100, rsi))
                
                # Determina tier
                confluences = 0
                if rsi < 30 or rsi > 70:
                    confluences += 1
                if abs(change) > 1:
                    confluences += 1
                
                if confluences >= 2:
                    tier = "FORTE"
                    signal = {
                        "direction": "CALL" if rsi < 50 else "PUT",
                        "entry": price,
                        "expiration": 5
                    }
                elif confluences == 1:
                    tier = "MODERADO"
                    signal = None
                else:
                    tier = "FRACO"
                    signal = None
                
                return {
                    "asset": asset,
                    "price": price,
                    "tier": tier,
                    "indicators": {
                        "rsi": round(rsi, 1),
                        "change_24h": round(change, 2)
                    },
                    "signal": signal,
                    "timestamp": datetime.now().isoformat()
                }
            else:
                return {
                    "asset": asset,
                    "status": "error",
                    "message": f"API retornou erro: {data.get('retMsg', 'desconhecido')}",
                    "symbol": symbol
                }
                
    except Exception as e:
        logger.error(f"Erro ao analisar {asset}: {e}")
        return {
            "asset": asset,
            "status": "error",
            "message": str(e),
            "symbol": symbol
        }

@app.get("/dashboard")
async def dashboard():
    return {
        "status": "online",
        "message": "Dashboard endpoint working"
    }

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    ws_clients.append(ws)
    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)
            if msg.get("action") == "subscribe":
                await ws.send_json({"type": "subscribed"})
    except WebSocketDisconnect:
        if ws in ws_clients:
            ws_clients.remove(ws)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)

