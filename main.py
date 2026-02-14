import os
import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Configuração
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sentinel")

PORT = int(os.getenv("PORT", 8000))

class SentinelCore:
    def _init_(self):
        self.scheduler = AsyncIOScheduler()
        self.price_cache: Dict[str, dict] = {}
        self.news_cache: List[dict] = []
        self.ws_clients: List[WebSocket] = []
        
    async def init(self):
        """Inicializa"""
        self.scheduler.start()
        self.scheduler.add_job(self._update_prices, "interval", seconds=5)
        asyncio.create_task(self._update_prices())
        asyncio.create_task(self._update_news())
        logger.info("✅ Sentinel iniciado")
    
    async def _update_prices(self):
        """Busca preços da Bybit"""
        try:
            async with httpx.AsyncClient() as client:
                symbols = ["BTCUSDT", "ETHUSDT", "EURUSDT", "GBPUSDT"]
                for symbol in symbols:
                    resp = await client.get(
                        f"https://api.bybit.com/v5/market/tickers?category=spot&symbol={symbol}",
                        timeout=10.0
                    )
                    data = resp.json()
                    if data.get("retCode") == 0:
                        ticker = data["result"]["list"][0]
                        self.price_cache[symbol] = {
                            "price": float(ticker["lastPrice"]),
                            "timestamp": int(ticker["ts"]),
                            "change_24h": float(ticker.get("price24hPcnt", 0)) * 100
                        }
                
                # Notifica clients
                await self._broadcast({
                    "type": "prices",
                    "data": self.price_cache
                })
        except Exception as e:
            logger.error(f"Erro preços: {e}")
    
    async def _update_news(self):
        """Busca notícias (simplificado)"""
        # Mock por enquanto - implementar depois
        self.news_cache = [
            {
                "time": "14:30",
                "currency": "USD",
                "event": "Non-Farm Payrolls",
                "impact": "High"
            }
        ]
    
    async def _broadcast(self, message: dict):
        """Envia para WebSockets"""
        disconnected = []
        for ws in self.ws_clients:
            try:
                await ws.send_json(message)
            except:
                disconnected.append(ws)
        for ws in disconnected:
            if ws in self.ws_clients:
                self.ws_clients.remove(ws)
    
    def analyze(self, asset: str) -> dict:
        """Análise técnica"""
        symbol = asset.replace("/", "") + "USDT"
        price_data = self.price_cache.get(symbol)
        
        if not price_data:
            return {
                "asset": asset,
                "status": "offline",
                "message": "Sem dados"
            }
        
        price = price_data["price"]
        change = price_data["change_24h"]
        
        # Análise simplificada
        rsi = 50 - (change * 2)
        rsi = max(0, min(100, rsi))
        
        confluences = 0
        if rsi < 30 or rsi > 70:
            confluences += 1
        if abs(change) > 1:
            confluences += 1
        
        tiers = {2: ("FORTE", "🟢"), 1: ("MODERADO", "🟡"), 0: ("FRACO", "🔴")}
        tier, emoji = tiers.get(confluences, ("FRACO", "🔴"))
        
        signal = None
        if tier == "FORTE":
            signal = {
                "direction": "CALL" if rsi < 50 else "PUT",
                "entry": price,
                "expiration": 5
            }
        
        return {
            "asset": asset,
            "price": price,
            "tier": tier,
            "emoji": emoji,
            "indicators": {"rsi": round(rsi, 1), "change_24h": round(change, 2)},
            "confluences": confluences,
            "signal": signal,
            "timestamp": datetime.now().isoformat()
        }

# Instância global
core = SentinelCore()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await core.init()
    yield

app = FastAPI(
    title="Sentinel Tactical API",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"status": "online", "service": "Sentinel Tactical v1.0"}

@app.get("/dashboard")
async def dashboard():
    return {
        "prices": core.price_cache,
        "news": core.news_cache,
        "assets": [
            {"name": "EUR/USD", "price": core.price_cache.get("EURUSDT", {}).get("price")},
            {"name": "GBP/USD", "price": core.price_cache.get("GBPUSDT", {}).get("price")},
            {"name": "BTC/USDT", "price": core.price_cache.get("BTCUSDT", {}).get("price")}
        ]
    }

@app.get("/analyze/{asset}")
async def analyze(asset: str):
    return core.analyze(asset)

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    core.ws_clients.append(ws)
    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)
            if msg.get("action") == "subscribe":
                await ws.send_json({"type": "subscribed", "assets": msg.get("assets", [])})
    except WebSocketDisconnect:
        if ws in core.ws_clients:
            core.ws_clients.remove(ws)

if _name_ == "_main_":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)