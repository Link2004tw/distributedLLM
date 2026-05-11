import httpx
from typing import Dict, List, Optional, Set


class Scheduler:

    def __init__(self, master_url: str = "http://localhost:9000"):
        self.master_url = master_url
        self._client: Optional[httpx.AsyncClient] = None

    async def init(self):
        self._client = httpx.AsyncClient(timeout=5.0)

    async def close(self):
        if self._client:
            await self._client.aclose()

    async def select_worker(self, strategy: str = "round_robin",
                            exclude_workers: Optional[List[str]] = None) -> Optional[dict]:
        if not self._client:
            return None
        try:
            resp = await self._client.post(
                f"{self.master_url}/schedule",
                json={
                    "strategy": strategy,
                    "exclude_workers": exclude_workers or [],
                }
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return None

    async def get_healthy_workers(self) -> List[dict]:
        if not self._client:
            return []
        try:
            resp = await self._client.get(f"{self.master_url}/workers")
            if resp.status_code == 200:
                return [w for w in resp.json().get("workers", []) if w.get("healthy")]
        except Exception:
            pass
        return []

    async def reset_routing(self):
        if not self._client:
            return
        try:
            await self._client.post(f"{self.master_url}/routing/reset")
        except Exception:
            pass
