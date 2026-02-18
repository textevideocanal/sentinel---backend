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
    
    # Mapeamento de pares válidos
    symbol_map = {
        "BTC/USDT": "BTCUSDT",
        "ETH/USDT": "ETHUSDT",
        "SOL/USDT": "SOLUSDT",
        "XRP/USDT": "XRPUSDT",
        "ADA/USDT": "ADAUSDT",
        "DOGE/USDT": "DOGEUSDT",
        "LTC/USDT": "LTCUSDT",
        "LINK/USDT": "LINKUSDT",
        # Sem Forex - ByBit não tem EURUSD, GBPUSD, etc no spot
    }
    
    # Normaliza o símbolo
    symbol = symbol_map.get(asset.upper(), asset.replace("/", "").upper())
    
    # Verifica se é um par suportado
    if symbol not in symbol_map.values():
        return {
            "asset": asset,
            "status": "error",
            "message": f"Par {asset} não suportado. Use: {list(symbol_map.keys())}"
        }
    
    try:
        async with httpx.AsyncClient() as client:
            # Tenta buscar na ByBit Spot
            resp = await client.get(
                f"https://api.bybit.com/v5/market/tickers?category=spot&symbol={symbol}",
                timeout=10.0
            )
            data = resp.json()
            
            logger.info(f"Resposta ByBit: {data}")
            
            # Verifica se retornou dados válidos
            if data.get("retCode") == 0 and data.get("result", {}).get("list"):
                ticker = data["result"]["list"][0]
                
                # Extrai valores com segurança
                price = float(ticker.get("lastPrice", 0))
                change_24h = float(ticker.get("price24hPcnt", 0)) * 100
                
                # Cálculo simplificado de RSI
                rsi = 50 - (change_24h * 2)
                rsi = max(0, min(100, rsi))
                
                # Lógica de sinais
                confluences = 0
                if rsi < 30 or rsi > 70:
                    confluences += 1
                if abs(change_24h) > 2:
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
                    "symbol": symbol,
                    "price": price,
                    "tier": tier,
                    "indicators": {
                        "rsi": round(rsi, 1),
                        "change_24h": round(change_24h, 2)
                    },
                    "signal": signal,
                    "timestamp": datetime.now().isoformat()
                }
            else:
                # Retorna erro com detalhes da API
                return {
                    "asset": asset,
                    "symbol": symbol,
                    "status": "error",
                    "message": "Par não encontrado na ByBit ou sem dados",
                    "api_response": data
                }
                
    except Exception as e:
        logger.error(f"Erro ao analisar {asset}: {str(e)}")
        return {
            "asset": asset,
            "status": "error",
            "message": str(e)
        }

# Inicia servidor
if __name__ == "__main__":
    logger.info("=== Sentinel API Iniciando ===")
    logger.info(f"Porta: {PORT}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
