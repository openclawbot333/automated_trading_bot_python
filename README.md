# automated_trading_bot_python

Rule-based trading bot scaffold (TradingView + broker APIs).

## Structure
- `src/` – core logic
- `config/` – config templates
- `scripts/` – utility scripts
- `tests/` – tests

## Quick start
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Webhook server
```bash
export WEBHOOK_SECRET=change-me
uvicorn src.webhook_server:app --reload --port 8000
```

POST JSON to `/webhook` with header `X-Webhook-Secret`.
