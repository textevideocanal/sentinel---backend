import os
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional

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

# ============ CONFIGURAÇÃO DOS PARES ============

# Pares que existem na ByBit (Cripto)
BYBIT_PAIRS = {
    "BTCUSDT": "BTCUSDT",
    "ETHUSDT": "ETHUSDT",
    "SOLUSDT": "SOLUSDT",
    "XRPUSDT": "XRPUSDT",
    "ADAUSDT": "ADAUSDT",
    "DOGEUSDT": "DOGEUSDT",
    "LTCUSDT": "LTCUSDT",
    "LINKUSDT": "LINKUSDT",
}

# Pares de Forex (usar API alternativa ou ByBit Linear)
FOREX_PAIRS = {
    "EURUSD": "EURUSD",  # Na ByBit Linear: EURUSDT (mas é cripto, não forex real)
    "GBPUSD": "GBPUSD",
    "USDJPY": "USDJPY",
    "AUDUSD": "AUDUSD",
    "USDCAD": "USDCAD",
    "NZDUSD": "NZDUSD",
    "USDCHF": "USDCHF",
    "EURGBP": "EURGBP",
}

# Commodities
COMMODITY_PAIRS = {
    "XAUUSD": "XAUUSD",  # Ouro
    "XAGUSD": "XAGUSD",  # Prata
    "USOIL": "USOIL",    # Petróleo
}

@app.get("/")
async def root():
    logger.info("Rota / acessada")
    return {
        "status": "online",
        "service": "Sentinel Tactical API",
        "available_pairs": {
            "crypto": list(BYBIT_PAIRS.keys()),
            "forex": list(FOREX_PAIRS.keys()),
            "commodities": list(COMMODITY_PAIRS.keys())
        },
        "timestamp": datetime.now().isoformat()
    }

@app.get("/analyze/{asset}")
async def analyze(asset: str):
    logger.info(f"Analisando: {asset}")
    
    # Normaliza o símbolo (remove barras, uppercase)
    symbol = asset.upper().replace("/", "").replace("%2F", "").replace("%2f", "")
    
    # Verifica se é um par válido
    all_pairs = {**BYBIT_PAIRS, **FOREX_PAIRS, **COMMODITY_PAIRS}
    
    if symbol not in all_pairs:
        return {
            "asset": asset,
            "status": "error",
            "message": f"Par {asset} não suportado. Use: {list(all_pairs.keys())}"
        }
    
    try:
        # Tenta ByBit primeiro (para cripto)
        if symbol in BYBIT_PAIRS:
            return await fetch_bybit_data(symbol, asset)
        
        # Para Forex/Commodities, usa API alternativa (Yahoo Finance via RapidAPI ou similar)
        # Ou simula com dados mockados para teste
        else:
            return await fetch_forex_data(symbol, asset)
            
    except Exception as e:
        logger.error(f"Erro ao analisar {asset}: {e}")
        return {"asset": asset, "status": "error", "message": str(e)}

async def fetch_bybit_data(symbol: str, original_asset: str):
    """Busca dados da ByBit (apenas cripto)"""
    bybit_symbol = BYBIT_PAIRS.get(symbol, symbol)
    
    async with httpx.AsyncClient() as client:
        # Tenta Spot primeiro
        resp = await client.get(
            f"https://api.bybit.com/v5/market/tickers?category=spot&symbol={bybit_symbol}",
            timeout=10.0
        )
        data = resp.json()
        
        # Se não encontrar no spot, tenta linear perpetual
        if data.get("retCode") != 0 or not data.get("result", {}).get("list"):
            resp = await client.get(
                f"https://api.bybit.com/v5/market/tickers?category=linear&symbol={bybit_symbol}",
                timeout=10.0
            )
            data = resp.json()
        
        if data.get("retCode") == 0 and data.get("result", {}).get("list"):
            ticker = data["result"]["list"][0]
            return process_ticker_data(ticker, original_asset, "bybit")
        else:
            return {
                "asset": original_asset,
                "status": "error",
                "message": f"Par {bybit_symbol} não encontrado na ByBit",
                "api_response": data
            }

async def fetch_forex_data(symbol: str, original_asset: str):
    """
    Busca dados de Forex/Commodities
    Opções: Alpha Vantage, Yahoo Finance, ou Twelve Data
    """
    # OPÇÃO 1: Usar Yahoo Finance (gratuito, não oficial)
    try:
        async with httpx.AsyncClient() as client:
            # Yahoo Finance endpoint não oficial
            yahoo_symbol = get_yahoo_symbol(symbol)
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}?interval=1d&range=1d"
            
            resp = await client.get(url, timeout=10.0)
            data = resp.json()
            
            if data.get("chart", {}).get("result"):
                result = data["chart"]["result"][0]
                meta = result["meta"]
                
                price = meta.get("regularMarketPrice", 0)
                prev_close = meta.get("previousClose", price)
                change = ((price - prev_close) / prev_close * 100) if prev_close else 0
                
                # Simula RSI baseado no change (mesma lógica do seu código)
                rsi = 50 - (change * 2)
                rsi = max(0, min(100, rsi))
                
                return generate_signal(original_asset, price, change, rsi, "yahoo")
            else:
                raise Exception("Dados não disponíveis no Yahoo Finance")
                
    except Exception as e:
        logger.warning(f"Yahoo Finance falhou para {symbol}: {e}")
        
        # OPÇÃO 2: Retornar dados simulados para teste
        return generate_mock_data(symbol, original_asset)

def get_yahoo_symbol(symbol: str) -> str:
    """Converte símbolo para formato Yahoo Finance"""
    conversions = {
        "EURUSD": "EURUSD=X",
        "GBPUSD": "GBPUSD=X",
        "USDJPY": "USDJPY=X",
        "AUDUSD": "AUDUSD=X",
        "USDCAD": "USDCAD=X",
        "NZDUSD": "NZDUSD=X",
        "USDCHF": "USDCHF=X",
        "XAUUSD": "GC=F",  # Ouro futuro
        "XAGUSD": "SI=F",  # Prata futuro
        "USOIL": "CL=F",   # Petróleo WTI
    }
    return conversions.get(symbol, symbol)

def process_ticker_data(ticker: dict, asset: str, source: str):
    """Processa dados do ticker e gera sinal"""
    try:
        price = float(ticker.get("lastPrice", ticker.get("markPrice", 0)))
        change = float(ticker.get("price24hPcnt", 0)) * 100
        
        # Cálculo simplificado de RSI (sua lógica original)
        rsi = 50 - (change * 2)
        rsi = max(0, min(100, rsi))
        
        return generate_signal(asset, price, change, rsi, source)
        
    except Exception as e:
        return {
            "asset": asset,
            "status": "error",
            "message": f"Erro ao processar dados: {e}",
            "raw_data": ticker
        }

def generate_signal(asset: str, price: float, change: float, rsi: float, source: str):
    """Gera o sinal de trading baseado nos indicadores"""
    
    confluences = 0
    reasons = []
    
    # RSI extremo
    if rsi < 30:
        confluences += 1
        reasons.append("RSI sobrevendido (<30)")
    elif rsi > 70:
        confluences += 1
        reasons.append("RSI sobrecomprado (>70)")
    
    # Movimento forte
    if abs(change) > 2:
        confluences += 1
        reasons.append(f"Movimento forte 24h ({change:+.2f}%)")
    elif abs(change) > 1:
        confluences += 0.5
        reasons.append(f"Movimento moderado 24h ({change:+.2f}%)")
    
    # Determina tier e sinal
    if confluences >= 2:
        tier = "FORTE"
        direction = "CALL" if rsi < 50 else "PUT"
        signal = {
            "direction": direction,
            "entry": price,
            "expiration": 5,
            "reasons": reasons
        }
    elif confluences >= 1:
        tier = "MODERADO"
        signal = {
            "direction": "CALL" if rsi < 50 else "PUT",
            "entry": price,
            "expiration": 5,
            "note": "Aguardar confirmação adicional",
            "reasons": reasons
        }
    else:
        tier = "FRACO"
        signal = None
    
    return {
        "asset": asset,
        "price": price,
        "tier": tier,
        "indicators": {
            "rsi": round(rsi, 1),
            "change_24h": round(change, 2),
            "source": source
        },
        "signal": signal,
        "timestamp": datetime.now().isoformat()
    }

def generate_mock_data(symbol: str, original_asset: str):
    """Gera dados simulados para teste quando APIs falham"""
    import random
    
    # Preços base aproximados
    base_prices = {
        "EURUSD": 1.0850,
        "GBPUSD": 1.2650,
        "USDJPY": 149.50,
        "AUDUSD": 0.6550,
        "USDCAD": 1.3550,
        "NZDUSD": 0.6150,
        "USDCHF": 0.8850,
        "XAUUSD": 2030.00,
        "XAGUSD": 23.50,
        "USOIL": 78.50,
    }
    
    base = base_prices.get(symbol, 100.0)
    variation = random.uniform(-0.02, 0.02)
    price = base * (1 + variation)
    change = variation * 100
    
    rsi = 50 - (change * 2)
    rsi = max(0, min(100, rsi))
    
    result = generate_signal(original_asset, price, change, rsi, "mock")
    result["note"] = "Dados simulados - API indisponível"
    return result

# ============ WEBSOCKET PARA STREAMING ============

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    ws_clients.append(websocket)
    logger.info(f"Cliente WebSocket conectado. Total: {len(ws_clients)}")
    
    try:
        while True:
            # Recebe mensagem do cliente
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message.get("action") == "subscribe":
                asset = message.get("asset")
                # Aqui você implementaria streaming de dados
                await websocket.send_json({
                    "type": "subscribed",
                    "asset": asset,
                    "timestamp": datetime.now().isoformat()
                })
                
    except WebSocketDisconnect:
        ws_clients.remove(websocket)
        logger.info(f"Cliente desconectado. Total: {len(ws_clients)}")

# Inicia servidor
if __name__ == "__main__":
    logger.info("=== Sentinel API Iniciando ===")
    logger.info(f"Porta: {PORT}")
    uvicorn.run(app, host="0.0.0.0", port=PORT
