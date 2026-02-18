import os
import json
import logging
from datetime import datetime
from typing import Dict, List

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Configuração
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sentinel")

PORT = int(os.getenv("PORT", 8000))

# Cache simples
price_cache: Dict[str, dict] = {}
ws_clients: List[WebSocket] = []

# Cria app
app = FastAPI(title="Sentinel Tactical API", version="3.0")

# CORS liberado
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    logger.info("Rota / acessada")
    return {
        "status": "online",
        "service": "Sentinel Tactical v3.0",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/analyze/{asset}")
async def analyze(asset: str):
    logger.info(f"Analisando: {asset}")
    
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
                
                rsi = 50 - (change * 2)
                rsi = max(0, min(100, rsi))
                
                confluences = 0
                if rsi < 30 or rsi > 70:
                    confluences += 1
                if abs(change) > 1:
                    confluences += 1
                
                if confluences >= 2:
                    tier = "FORTE"
                    signal = {"direction": "CALL" if rsi < 50 else "PUT", "entry": price, "expiration": 5}
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
                    "indicators": {"rsi": round(rsi, 1), "change_24h": round(change, 2)},
                    "signal": signal,
                    "timestamp": datetime.now().isoformat()
                }
            else:
                return {"asset": asset, "status": "error", "message": "Sem dados"}
                
    except Exception as e:
        logger.error(f"Erro: {e}")
        return {"asset": asset, "status": "error", "message": str(e)}

# Inicia diretamente sem if __name__
logger.info("=== Sentinel API Iniciando ===")
logger.info(f"Porta: {PORT}")
uvicorn.run(app, host="0.0.0.0", port=PORT)
