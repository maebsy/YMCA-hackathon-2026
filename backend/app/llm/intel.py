"""위협 정보: CISA KEV(실제 공격에 쓰인 취약점 목록)와 FIRST EPSS(30일 안에 악용될 확률).

- KEV: https://www.cisa.gov/known-exploited-vulnerabilities-catalog (미국 정부 공개 자료)
- EPSS: https://www.first.org/epss/api (무료 공개 API, 등록 불필요)

네트워크가 안 되면 빈 결과를 돌려주고, 위험도 해석은 "모름"으로 진행합니다. 검사를 멈추지 않습니다.
"""

import asyncio
import logging
import time
from typing import Protocol

import httpx

from app.llm.schemas import ThreatIntelRecord

log = logging.getLogger(__name__)

KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
EPSS_URL = "https://api.first.org/data/v1/epss"
_EPSS_BATCH = 100  # EPSS API 한 번에 조회할 수 있는 CVE 수


class ThreatIntel(Protocol):
    async def lookup(self, cves: list[str]) -> dict[str, ThreatIntelRecord]: ...


class StaticThreatIntel:
    """미리 정한 값을 돌려줍니다. 테스트와 오프라인 시연용."""

    def __init__(self, records: dict[str, ThreatIntelRecord] | None = None) -> None:
        self.records = records or {}

    async def lookup(self, cves: list[str]) -> dict[str, ThreatIntelRecord]:
        return {c: self.records[c] for c in cves if c in self.records}


class HttpThreatIntel:
    """KEV 목록은 통째로 받아 캐시하고(기본 6시간), EPSS 는 CVE별로 캐시합니다.

    받지 못하면 그 실패도 failure_backoff_s(기본 5분) 동안 기억합니다. 외부망이 막힌 서버에서 요청마다
    시간 제한(10초)만큼 기다리지 않게 하려는 것입니다.
    """

    def __init__(
        self,
        timeout_s: float = 10.0,
        ttl_s: float = 6 * 3600,
        failure_backoff_s: float = 300.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._http = httpx.AsyncClient(timeout=timeout_s, transport=transport, follow_redirects=True)
        self._ttl = ttl_s
        self._backoff = failure_backoff_s
        self._kev: dict[str, str] = {}  # CVE → 추가된 날짜
        self._kev_loaded_at = 0.0
        self._kev_retry_at = 0.0  # 이 시각 전에는 KEV 를 다시 받으러 가지 않음 (실패 뒤)
        self._epss_retry_at = 0.0
        self._epss: dict[str, tuple[float, float, float]] = {}  # CVE → (epss, percentile, 받은 시각)
        self._lock = asyncio.Lock()

    async def aclose(self) -> None:
        await self._http.aclose()

    async def lookup(self, cves: list[str]) -> dict[str, ThreatIntelRecord]:
        cves = sorted({c.upper() for c in cves if c.upper().startswith("CVE-")})
        if not cves:
            return {}
        async with self._lock:  # 동시에 여러 건이 와도 KEV 는 한 번만 받습니다
            await self._refresh_kev()
            await self._fetch_epss([c for c in cves if not self._fresh_epss(c)])
        out = {}
        for cve in cves:
            epss = self._epss.get(cve)
            out[cve] = ThreatIntelRecord(
                cve=cve,
                kev=cve in self._kev,
                kev_date_added=self._kev.get(cve),
                epss=epss[0] if epss else None,
                epss_percentile=epss[1] if epss else None,
            )
        return out

    def _fresh_epss(self, cve: str) -> bool:
        hit = self._epss.get(cve)
        return bool(hit) and time.monotonic() - hit[2] < self._ttl

    async def _refresh_kev(self) -> None:
        now = time.monotonic()
        if self._kev_loaded_at and now - self._kev_loaded_at < self._ttl:
            return
        if now < self._kev_retry_at:
            return
        try:
            resp = await self._http.get(KEV_URL)
            resp.raise_for_status()
            self._kev = {v["cveID"].upper(): v.get("dateAdded") for v in resp.json().get("vulnerabilities", [])}
            self._kev_loaded_at = time.monotonic()
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            self._kev_retry_at = time.monotonic() + self._backoff
            log.warning("KEV 목록을 받지 못했습니다 (모름으로 진행, %.0f초 뒤 다시 시도): %s", self._backoff, exc)

    async def _fetch_epss(self, cves: list[str]) -> None:
        if time.monotonic() < self._epss_retry_at:
            return
        for i in range(0, len(cves), _EPSS_BATCH):
            batch = cves[i : i + _EPSS_BATCH]
            try:
                resp = await self._http.get(EPSS_URL, params={"cve": ",".join(batch)})
                resp.raise_for_status()
                now = time.monotonic()
                for row in resp.json().get("data", []):
                    self._epss[row["cve"].upper()] = (float(row["epss"]), float(row["percentile"]), now)
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                self._epss_retry_at = time.monotonic() + self._backoff
                log.warning("EPSS 를 받지 못했습니다 (모름으로 진행, %.0f초 뒤 다시 시도): %s", self._backoff, exc)
                return
