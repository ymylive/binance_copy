from __future__ import annotations

from typing import Any, Dict, Optional

import httpx


class LeaderProxyClient:
    def __init__(self, base_url: str, timeout_ms: int = 5000) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_ms = timeout_ms
        self._client: Optional[httpx.AsyncClient] = None
        self.connected = False
        self.last_error: Optional[str] = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            timeout = self.timeout_ms / 1000.0
            self._client = httpx.AsyncClient(timeout=timeout)
        return self._client

    async def connect(self) -> bool:
        try:
            client = await self._ensure_client()
            resp = await client.get(f"{self.base_url}/api/leader/ping")
            resp.raise_for_status()
            self.connected = True
            self.last_error = None
            return True
        except Exception as exc:  # pragma: no cover - runtime connectivity
            self.connected = False
            self.last_error = str(exc)
            return False

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
        self.connected = False

    async def _request(
        self,
        method: str,
        path: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        client = await self._ensure_client()
        url = f"{self.base_url}{path}"
        try:
            if method == "GET":
                resp = await client.get(url)
            else:
                resp = await client.post(url, json=data)
            resp.raise_for_status()
            self.connected = True
            self.last_error = None
            return resp.json()
        except Exception as exc:
            self.connected = False
            self.last_error = str(exc)
            raise

    async def fetch_detail(self, portfolio_id: str) -> Dict[str, Any]:
        return await self._request("GET", f"/api/leader/{portfolio_id}/detail")

    async def fetch_order_history(
        self,
        portfolio_id: str,
        start_time: int,
        end_time: int,
        page_size: int,
    ) -> Dict[str, Any]:
        payload = {
            "portfolioId": portfolio_id,
            "startTime": start_time,
            "endTime": end_time,
            "pageSize": page_size,
        }
        return await self._request(
            "POST",
            f"/api/leader/{portfolio_id}/order-history",
            data=payload,
        )

    async def fetch_position_history(
        self,
        portfolio_id: str,
        page_number: int,
        page_size: int,
    ) -> Dict[str, Any]:
        payload = {
            "portfolioId": portfolio_id,
            "pageNumber": page_number,
            "pageSize": page_size,
        }
        return await self._request(
            "POST",
            f"/api/leader/{portfolio_id}/position-history",
            data=payload,
        )

    async def fetch_positions(self, portfolio_id: str) -> Dict[str, Any]:
        return await self._request("GET", f"/api/leader/{portfolio_id}/positions")
