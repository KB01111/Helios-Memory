"""Upstash Redis holographic cache store (MVP stub)."""

from __future__ import annotations

import logging
import os
from typing import Any
from urllib import error, request

from helios_memory.models.storage import CacheEntry

logger = logging.getLogger(__name__)


def _stub(method: str) -> None:
    logger.warning("UpstashRedisCacheStore.%s is not implemented (MVP stub)", method)


class UpstashRedisCacheStore:
    """Holographic short-term cache backed by Upstash Redis REST API.

    Activation:
        Set ``UPSTASH_REDIS_REST_URL`` and ``UPSTASH_REDIS_REST_TOKEN``.

    MVP:
        Minimal REST ping on ``connect()``; CRUD methods are stubbed.
    """

    def __init__(
        self,
        rest_url: str | None = None,
        rest_token: str | None = None,
    ) -> None:
        self._rest_url = rest_url or os.environ.get("UPSTASH_REDIS_REST_URL", "")
        self._rest_token = rest_token or os.environ.get(
            "UPSTASH_REDIS_REST_TOKEN", ""
        )
        self._connected = False

    async def connect(self) -> None:
        """Verify Upstash credentials and optionally ping the REST endpoint."""
        if not self._rest_url or not self._rest_token:
            logger.warning(
                "UpstashRedisCacheStore: UPSTASH_REDIS_REST_URL/TOKEN not set; "
                "operating in stub mode"
            )
            self._connected = True
            return

        try:
            ping_url = f"{self._rest_url.rstrip('/')}/ping"
            req = request.Request(
                ping_url,
                headers={"Authorization": f"Bearer {self._rest_token}"},
                method="GET",
            )
            with request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    logger.info("UpstashRedisCacheStore: REST ping succeeded")
                else:
                    logger.warning(
                        "UpstashRedisCacheStore: REST ping returned status %s",
                        resp.status,
                    )
        except (error.URLError, TimeoutError, OSError) as exc:
            logger.warning(
                "UpstashRedisCacheStore: REST ping failed (%s); operating in stub mode",
                exc,
            )

        self._connected = True

    async def close(self) -> None:
        self._connected = False

    async def get(self, key: str) -> CacheEntry | None:
        _stub("get")
        return None

    async def set(
        self,
        key: str,
        value: CacheEntry,
        ttl: int | None = None,
    ) -> None:
        _stub("set")

    async def delete(self, key: str) -> None:
        _stub("delete")

    async def search_by_tags(
        self,
        tags: list[str],
        limit: int = 20,
    ) -> list[CacheEntry]:
        _stub("search_by_tags")
        return []

    async def search_by_query(
        self,
        query: str,
        limit: int = 20,
    ) -> list[Any]:
        _stub("search_by_query")
        return []
