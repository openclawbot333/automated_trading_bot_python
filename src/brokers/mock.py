from typing import Dict, Any
from .base import BrokerAdapter


class MockBroker(BrokerAdapter):
    def place_order(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        # Simulate a broker response
        return {
            "status": "accepted",
            "broker": "mock",
            "received": signal,
        }
