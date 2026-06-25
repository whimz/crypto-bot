"""Klines (candlestick) data access for Binance, with Testnet/Production support."""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlencode

import requests

from backend.config import BINANCE_API_KEY, BINANCE_SECRET_KEY, BINANCE_TESTNET

PRODUCTION_BASE_URL = "https://api.binance.com"
TESTNET_BASE_URL = "https://testnet.binance.vision"

KLINES_ENDPOINT = "/api/v3/klines"
ORDER_ENDPOINT = "/api/v3/order"

VALID_INTERVALS = {
    "1m", "3m", "5m", "15m", "30m",
    "1h", "2h", "4h", "6h", "8h", "12h",
    "1d", "3d", "1w", "1M",
}


@dataclass(frozen=True)
class Candle:
    open_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    close_time: int
    quote_volume: float
    trades: int


class BinanceClientError(Exception):
    pass


class BinanceClient:
    """Thin REST client for Binance market data, switching base URL by testnet flag."""

    def __init__(
        self,
        testnet: Optional[bool] = None,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        session: Optional[requests.Session] = None,
    ):
        self.testnet = BINANCE_TESTNET if testnet is None else testnet
        self.base_url = TESTNET_BASE_URL if self.testnet else PRODUCTION_BASE_URL
        self.api_key = api_key if api_key is not None else BINANCE_API_KEY
        self.secret_key = secret_key if secret_key is not None else BINANCE_SECRET_KEY
        self.session = session or requests.Session()

    def get_klines(
        self,
        symbol: str = "BTCUSDT",
        interval: str = "1h",
        limit: int = 500,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> list[Candle]:
        """Fetch candlestick data for a symbol.

        Args:
            symbol: trading pair, e.g. "BTCUSDT".
            interval: kline interval, one of VALID_INTERVALS.
            limit: number of candles to return (max 1000).
            start_time: optional start time in ms since epoch.
            end_time: optional end time in ms since epoch.
        """
        if interval not in VALID_INTERVALS:
            raise ValueError(f"Invalid interval: {interval!r}. Valid options: {sorted(VALID_INTERVALS)}")
        if not (1 <= limit <= 1000):
            raise ValueError("limit must be between 1 and 1000")

        params = {
            "symbol": symbol.upper(),
            "interval": interval,
            "limit": limit,
        }
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time

        url = f"{self.base_url}{KLINES_ENDPOINT}"
        try:
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise BinanceClientError(f"Failed to fetch klines for {symbol}: {exc}") from exc

        raw_klines = response.json()
        return [self._parse_kline(k) for k in raw_klines]

    def place_market_order(self, symbol: str, side: str, quote_order_qty: float) -> dict:
        """Place a MARKET order sized in quote currency (USDT) for both BUY and SELL.

        Binance's `quoteOrderQty` works for SELL too: "sell as much base asset as
        needed to receive this much quote currency", so callers never need to
        convert to a base-asset quantity themselves.
        """
        if side not in ("BUY", "SELL"):
            raise ValueError(f"side must be 'BUY' or 'SELL', got {side!r}")
        if quote_order_qty <= 0:
            raise ValueError("quote_order_qty must be positive")

        params = {
            "symbol": symbol.upper(),
            "side": side,
            "type": "MARKET",
            "quoteOrderQty": quote_order_qty,
        }
        return self._signed_request("POST", ORDER_ENDPOINT, params)

    def _signed_request(self, method: str, path: str, params: dict) -> dict:
        if not self.api_key or not self.secret_key:
            raise BinanceClientError("BINANCE_API_KEY/BINANCE_SECRET_KEY are not configured")

        signed_params = dict(params)
        signed_params["timestamp"] = int(time.time() * 1000)
        signed_params.setdefault("recvWindow", 5000)
        query = urlencode(signed_params)
        signature = hmac.new(self.secret_key.encode(), query.encode(), hashlib.sha256).hexdigest()
        signed_params["signature"] = signature

        url = f"{self.base_url}{path}"
        headers = {"X-MBX-APIKEY": self.api_key}
        try:
            response = self.session.request(method, url, params=signed_params, headers=headers, timeout=10)
            response.raise_for_status()
        except requests.RequestException as exc:
            detail = exc.response.text if exc.response is not None else str(exc)
            raise BinanceClientError(f"Binance {method} {path} failed: {detail}") from exc

        return response.json()

    @staticmethod
    def _parse_kline(raw: list) -> Candle:
        return Candle(
            open_time=raw[0],
            open=float(raw[1]),
            high=float(raw[2]),
            low=float(raw[3]),
            close=float(raw[4]),
            volume=float(raw[5]),
            close_time=raw[6],
            quote_volume=float(raw[7]),
            trades=int(raw[8]),
        )


def get_klines(
    symbol: str = "BTCUSDT",
    interval: str = "1h",
    limit: int = 500,
) -> list[Candle]:
    """Convenience wrapper using the BINANCE_TESTNET env var to pick the environment."""
    return BinanceClient().get_klines(symbol=symbol, interval=interval, limit=limit)
