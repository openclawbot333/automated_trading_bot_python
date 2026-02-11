from abc import ABC, abstractmethod
from typing import Dict, Any


class BrokerAdapter(ABC):
    @abstractmethod
    def place_order(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        """Place an order based on a TradingView signal payload."""
        raise NotImplementedError
