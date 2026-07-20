"""Bounded, failure-isolated external information cache for the D6 gateway.

The collector never owns device control.  It only normalizes provider results into
timestamped, source-labelled context records that the five-minute report may read.
All network access is optional and bounded so an offline home remains controllable.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sqlite3
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from typing import Any, Callable
from urllib.request import Request, urlopen
from urllib.parse import urlencode, urlsplit

_CST = timezone(timedelta(hours=8))

# 外部信息只接受中文站点，避免英文聚合源混入上下文和语音播报。
_CHINESE_SOURCE_DOMAINS = (
    "chinanews.com.cn", "weather.com.cn", "cma.cn", "cntv.cn",
    "xinhuanet.com", "people.com.cn", "sina.com.cn", "eastmoney.com",
    "amap.com", "baidu.com", "qq.com",
)


def is_chinese_source_url(url: str, *, allow_test: bool = False) -> bool:
    try:
        parsed = urlsplit(str(url).strip())
        host = (parsed.hostname or "").lower().rstrip(".")
        if allow_test and host == "test.invalid":
            return True
        return parsed.scheme in {"http", "https"} and any(
            host == domain or host.endswith("." + domain)
            for domain in _CHINESE_SOURCE_DOMAINS
        )
    except ValueError:
        return False


def chinese_source_name(url: str) -> str:
    host = (urlsplit(str(url).strip()).hostname or "").lower()
    names = {
        "chinanews.com.cn": "中国新闻网", "weather.com.cn": "中国天气网",
        "cma.cn": "中国气象局", "cntv.cn": "央视新闻", "xinhuanet.com": "新华网",
        "people.com.cn": "人民网", "sina.com.cn": "新浪财经",
        "eastmoney.com": "东方财富", "amap.com": "高德地图",
        "baidu.com": "百度", "qq.com": "腾讯",
    }
    for domain, name in names.items():
        if host == domain or host.endswith("." + domain):
            return name
    return "中文网站"


def _now() -> float:
    return time.time()


class ExternalIntelligenceCollector:
    def __init__(self, db_path: str, *, fetcher: Callable[[str, int], Any] | None = None,
                 max_items: int = 24, timeout: int = 6, stale_after: int = 1800) -> None:
        self.db_path = str(db_path)
        self.max_items = max(1, min(int(max_items), 100))
        self.timeout = max(1, min(int(timeout), 15))
        self.stale_after = max(60, int(stale_after))
        self._custom_fetcher = fetcher is not None
        self.fetcher = fetcher or self._fetch_json
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        conn = self._connect()
        try:
            conn.execute("""CREATE TABLE IF NOT EXISTS external_intelligence_cache(
                content_hash TEXT PRIMARY KEY, category TEXT NOT NULL, title TEXT NOT NULL,
                summary TEXT NOT NULL, source_url TEXT NOT NULL, image_url TEXT,
                published_at TEXT, observed_at REAL NOT NULL, fetched_at REAL NOT NULL,
                stale INTEGER NOT NULL DEFAULT 0, payload_json TEXT NOT NULL)""")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_external_observed ON external_intelligence_cache(observed_at DESC)")
            conn.execute("""CREATE TABLE IF NOT EXISTS external_intelligence_config(
                id INTEGER PRIMARY KEY CHECK(id=1), enabled INTEGER NOT NULL DEFAULT 1,
                latitude TEXT NOT NULL DEFAULT '', longitude TEXT NOT NULL DEFAULT '',
                location_name TEXT NOT NULL DEFAULT '', traffic_url TEXT NOT NULL DEFAULT '',
                market_symbol TEXT NOT NULL DEFAULT '', updated_at REAL NOT NULL)""")
            conn.execute(
                "INSERT OR IGNORE INTO external_intelligence_config(id,enabled,updated_at) VALUES(1,1,?)",
                (_now(),),
            )
            conn.commit()
        finally:
            conn.close()

    def get_config(self) -> dict[str, Any]:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT enabled,latitude,longitude,location_name,traffic_url,market_symbol,updated_at "
                "FROM external_intelligence_config WHERE id=1"
            ).fetchone()
            if not row:
                return {"enabled": True, "latitude": "", "longitude": "", "locationName": "",
                        "trafficUrl": "", "marketSymbol": "", "updatedAt": 0}
            return {
                "enabled": bool(row[0]), "latitude": str(row[1] or ""), "longitude": str(row[2] or ""),
                "locationName": str(row[3] or ""), "trafficUrl": str(row[4] or ""),
                "marketSymbol": str(row[5] or ""), "updatedAt": float(row[6] or 0),
                "environment": {
                    "weather": bool(os.environ.get("A9_LOCATION_LAT", "").strip() and os.environ.get("A9_LOCATION_LON", "").strip()),
                    "news": True, "technology": True,
                    "traffic": bool(os.environ.get("A9_EXTERNAL_TRAFFIC_URL", "").strip()),
                    "market": bool(os.environ.get("ALPHAVANTAGE_API_KEY", "").strip()),
                },
            }
        finally:
            conn.close()

    def update_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        current = self.get_config()
        enabled = bool(payload.get("enabled", current.get("enabled", True)))

        def clean_number(name: str) -> str:
            raw = payload.get(name, current.get(name, ""))
            if raw is None or str(raw).strip() == "":
                return ""
            try:
                value = float(raw)
            except (TypeError, ValueError):
                raise ValueError(f"{name} must be numeric")
            if name == "latitude" and not -90 <= value <= 90:
                raise ValueError("latitude out of range")
            if name == "longitude" and not -180 <= value <= 180:
                raise ValueError("longitude out of range")
            return f"{value:g}"

        latitude = clean_number("latitude")
        longitude = clean_number("longitude")
        location_name = str(payload.get("locationName", current.get("locationName", "")) or "").strip()[:80]
        traffic_url = str(payload.get("trafficUrl", current.get("trafficUrl", "")) or "").strip()[:2048]
        market_symbol = str(payload.get("marketSymbol", current.get("marketSymbol", "")) or "").strip()[:32]
        if traffic_url and not is_chinese_source_url(traffic_url):
            raise ValueError("trafficUrl must use http or https; 仅允许中文网站")
        conn = self._connect()
        try:
            conn.execute("""UPDATE external_intelligence_config SET enabled=?,latitude=?,longitude=?,
                location_name=?,traffic_url=?,market_symbol=?,updated_at=? WHERE id=1""",
                         (1 if enabled else 0, latitude, longitude, location_name, traffic_url,
                          market_symbol, _now()))
            conn.commit()
        finally:
            conn.close()
        return self.get_config()

    def _stored_config(self) -> dict[str, Any]:
        return self.get_config()

    def _fetch_json(self, url: str, timeout: int) -> Any:
        request = Request(url, headers={"User-Agent": "A9-D6-home-gateway/1.0"})
        with urlopen(request, timeout=timeout) as response:
            payload = response.read(512 * 1024).decode("utf-8", errors="replace")
            try:
                return json.loads(payload)
            except json.JSONDecodeError:
                return payload

    def _provider_url(self, category: str) -> str:
        stored = self._stored_config()
        if not bool(stored.get("enabled", True)):
            return ""
        configured = os.environ.get(f"A9_EXTERNAL_{category.upper()}_URL", "").strip()
        if category == "traffic" and stored.get("trafficUrl"):
            configured = str(stored.get("trafficUrl"))
        if configured:
            parts = [part for part in configured.split("\n") if is_chinese_source_url(part)]
            return "\n".join(parts)
        if category == "weather":
            city_code = str(os.environ.get("A9_WEATHER_CITY_CODE", "")).strip()
            if city_code.isdigit():
                return f"https://www.weather.com.cn/data/sk/{city_code}.html"
        if category in {"news", "technology"}:
            if category == "news":
                return "https://www.chinanews.com.cn/rss/scroll-news.xml\nhttps://www.chinanews.com.cn/rss/china.xml"
            return "https://www.chinanews.com.cn/rss/tech.xml\nhttps://www.chinanews.com.cn/rss/finance.xml"
        # Tests and embedders may inject a fetcher without configuring real
        # providers.  Keep production offline-safe while allowing that seam to
        # exercise normalization and cache behavior for every category.
        if self._custom_fetcher:
            return f"https://test.invalid/{category}"
        return ""

    def _provider_items(self, category: str, raw: Any, source_url: str) -> list[dict[str, Any]]:
        if category == "weather" and isinstance(raw, dict):
            weather = raw.get("weatherinfo") if isinstance(raw.get("weatherinfo"), dict) else {}
            if weather:
                summary = (f"当前 {weather.get('temp', '--')}℃，{weather.get('weather', '天气未知')}，"
                           f"风向{weather.get('WD', '未知')}，风力{weather.get('WS', '未知')}，"
                           f"湿度{weather.get('SD', '未知')}。")
                return [{"title": f"{weather.get('city', '当前位置')}天气", "description": summary,
                         "url": "https://www.weather.com.cn/", "time": weather.get("ptime", "")}]
            current = raw.get("current") if isinstance(raw.get("current"), dict) else {}
            daily = raw.get("daily") if isinstance(raw.get("daily"), dict) else {}
            location = str(self.get_config().get("locationName") or os.environ.get("A9_LOCATION_NAME", "当前位置"))
            high = (daily.get("temperature_2m_max") or [None])[0]
            low = (daily.get("temperature_2m_min") or [None])[0]
            rain = (daily.get("precipitation_probability_max") or [None])[0]
            summary = (f"当前 {current.get('temperature_2m', '--')}℃，体感 {current.get('apparent_temperature', '--')}℃，"
                       f"湿度 {current.get('relative_humidity_2m', '--')}%，风速 {current.get('wind_speed_10m', '--')}km/h；"
                       f"今日 {low}–{high}℃，最高降水概率 {rain}%。")
            return [{"title": f"{location}今日天气", "description": summary,
                     "url": "https://www.weather.com.cn/", "time": current.get("time", "")}]
        if category in {"news", "technology"} and isinstance(raw, dict):
            articles = raw.get("articles", [])
            if not articles and isinstance(raw.get("items"), list):
                articles = raw.get("items", [])
            if not isinstance(articles, list):
                return []
            return [{"title": article.get("title", ""), "description": article.get("domain", ""),
                     "url": article.get("url", ""), "image": article.get("socialimage", ""),
                     "time": article.get("seendate", "")} for article in articles if isinstance(article, dict)]
        if category in {"news", "technology"} and isinstance(raw, str):
            try:
                root = ET.fromstring(raw)
            except ET.ParseError:
                return []
            result: list[dict[str, Any]] = []
            for node in root.findall(".//item")[: self.max_items]:
                def text(name: str) -> str:
                    value = node.findtext(name, default="") or ""
                    return html.unescape(re.sub(r"<[^>]+>", " ", value)).strip()
                link = text("link")
                title = text("title")
                if title and link:
                    image = ""
                    enclosure = node.find("enclosure")
                    if enclosure is not None:
                        image = str(enclosure.attrib.get("url", ""))
                    if not image:
                        for tag in ("{http://search.yahoo.com/mrss/}content",
                                    "{http://search.yahoo.com/mrss/}thumbnail"):
                            media = node.find(tag)
                            if media is not None and media.attrib.get("url"):
                                image = str(media.attrib.get("url"))
                                break
                    result.append({"title": title, "description": text("description"),
                                   "url": link, "image": image, "time": text("pubDate")})
            return result
        if category == "market" and isinstance(raw, dict):
            quote = raw.get("Global Quote") if isinstance(raw.get("Global Quote"), dict) else {}
            if not quote:
                return []
            symbol = str(quote.get("01. symbol", "指数"))
            return [{"title": f"{symbol} 市场走势", "description":
                     f"价格 {quote.get('05. price', '--')}，涨跌 {quote.get('09. change', '--')}（{quote.get('10. change percent', '--')}）",
                     "url": "https://finance.sina.com.cn/", "time": quote.get("07. latest trading day", "")}]
        values = raw.get("items", raw) if isinstance(raw, dict) else raw
        if isinstance(values, list):
            return [item for item in values if isinstance(item, dict)]
        return [raw] if isinstance(raw, dict) else []

    def _normalize(self, category: str, item: dict[str, Any], source_url: str) -> dict[str, Any] | None:
        title = str(item.get("title") or item.get("name") or "").strip()
        if not title:
            return None
        summary = str(item.get("summary") or item.get("description") or item.get("content") or "").strip()[:1000]
        url = str(item.get("source_url") or item.get("url") or source_url).strip()
        if not url or not is_chinese_source_url(url, allow_test=self._custom_fetcher):
            return None
        published = str(item.get("published_at") or item.get("published") or item.get("time") or "").strip()
        image = str(item.get("image_url") or item.get("image") or item.get("thumbnail") or "").strip()[:2048]
        if image and not is_chinese_source_url(image, allow_test=self._custom_fetcher):
            image = ""
        canonical = f"{category}|{title}|{url}|{published}"
        content_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        now = _now()
        return {
            "category": category, "title": title, "summary": summary,
            "source_url": url, "image_url": image, "published_at": published,
            "source_name": chinese_source_name(url),
            "observed_at": now, "fetched_at": now, "content_hash": content_hash,
            "stale": False,
        }

    def collect_category(self, category: str) -> dict[str, Any]:
        url = self._provider_url(category)
        if not url:
            disabled = not bool(self.get_config().get("enabled", True))
            return {"category": category, "items": [], "available": False,
                    "stale": False, "error": "外部信息已关闭" if disabled else "未配置数据源"}
        try:
            provider_urls = [part for part in url.split("\n") if part]
            raw = None
            last_error: Exception | None = None
            for provider_url in provider_urls:
                try:
                    raw = self.fetcher(provider_url, self.timeout)
                    url = provider_url
                    break
                except Exception as exc:
                    last_error = exc
            if raw is None:
                raise last_error or RuntimeError("provider unavailable")
            values = self._provider_items(category, raw, url)
            normalized = [self._normalize(category, item, url) for item in values[: self.max_items]
                          if isinstance(item, dict)]
            items = [item for item in normalized if item]
            self._store(items)
            return {"category": category, "items": items, "available": True, "fetched_at": _now()}
        except Exception as exc:
            return {"category": category, "items": self.cached(category), "available": False,
                    "stale": True, "error": str(exc)[:180]}

    def _store(self, items: list[dict[str, Any]]) -> None:
        if not items:
            return
        conn = self._connect()
        try:
            for item in items:
                conn.execute("""INSERT OR REPLACE INTO external_intelligence_cache
                    (content_hash,category,title,summary,source_url,image_url,published_at,observed_at,fetched_at,stale,payload_json)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (
                    item["content_hash"], item["category"], item["title"], item["summary"], item["source_url"],
                    item["image_url"], item["published_at"], item["observed_at"], item["fetched_at"], 0,
                    json.dumps(item, ensure_ascii=False),))
            conn.execute("DELETE FROM external_intelligence_cache WHERE observed_at < ?", (_now() - 7 * 86400,))
            conn.commit()
        finally:
            conn.close()

    def cached(self, category: str = "") -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            if category:
                rows = conn.execute("SELECT payload_json, fetched_at FROM external_intelligence_cache WHERE category=? ORDER BY observed_at DESC LIMIT ?", (category, self.max_items)).fetchall()
            else:
                rows = conn.execute("SELECT payload_json, fetched_at FROM external_intelligence_cache ORDER BY observed_at DESC LIMIT ?", (self.max_items,)).fetchall()
            values = []
            for row in rows:
                item = json.loads(row[0])
                if not is_chinese_source_url(item.get("source_url", ""), allow_test=self._custom_fetcher):
                    continue
                item["stale"] = (_now() - float(row[1])) > self.stale_after
                values.append(item)
            return values
        finally:
            conn.close()

    def collect(self) -> dict[str, Any]:
        config = self.get_config()
        if not bool(config.get("enabled", True)):
            return {"success": True, "enabled": False, "generated_at": datetime.now(_CST).isoformat(),
                    "categories": [], "items": []}
        categories = ("weather", "traffic", "news", "technology", "market")
        reports = [self.collect_category(category) for category in categories]
        items = [item for report in reports for item in report.get("items", [])]
        return {"success": True, "enabled": True, "generated_at": datetime.now(_CST).isoformat(),
                "categories": reports, "items": items[: self.max_items]}
