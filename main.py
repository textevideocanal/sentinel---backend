import os
import json
import logging
from datetime import datetime
from typing import Dict, List

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

# Configuração
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sentinel")

PORT = int(os.getenv("PORT", 8000))

# Cache simples
price_cache: Dict[str, dict] = {}
ws_clients: List[WebSocket] = []

# Cria app
app = FastAPI(title="Sentinel Tactical API", version="2.0")

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
        "service": "Sentinel Tactical v2.0",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/test")
async def test():
    logger.info("Rota /test acessada")
    return {"message": "Teste OK"}

@app.get("/analyze/{asset}")
async def analyze(asset: str):
    logger.info(f"Analisando: {asset}")
    return {
        "asset": asset,
        "status": "test",
        "message": "Rota funcionando",
        "timestamp": datetime.now().isoformat()
    }

# Log ao iniciar
logger.info("=== Sentinel API Iniciando ===")
logger.info(f"Rotas registradas: {['/']}")

if __name__ == "__main__":
    import uvicorn
    logger.info("Iniciando uvicorn...")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
