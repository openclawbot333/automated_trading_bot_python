import os
from typing import Dict, Any
from fastapi import FastAPI, Header, HTTPException
from .brokers.mock import MockBroker

app = FastAPI()

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")

broker = MockBroker()


@app.post("/webhook")
async def tradingview_webhook(payload: Dict[str, Any], x_webhook_secret: str = Header(default="")):
    if WEBHOOK_SECRET and x_webhook_secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

    # Basic payload expectations
    # Example: {"symbol":"ES","side":"buy","qty":1,"price":123.45}
    if "symbol" not in payload or "side" not in payload:
        raise HTTPException(status_code=400, detail="Missing required fields")

    result = broker.place_order(payload)
    return {"ok": True, "result": result}
