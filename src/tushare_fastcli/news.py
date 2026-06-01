from __future__ import annotations

import hashlib
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from .config import read_env_file


BASE_URL = "https://tushare.pro"
DEFAULT_NEWS_SOURCES = [
    "xq",
    "jinshi",
    "jinrongjie",
    "10jqka",
    "yicai",
    "cls",
    "eastmoney",
    "wallstreetcn",
    "sina",
]


class TushareNewsError(RuntimeError):
    pass


class TushareNewsFetchError(TushareNewsError):
    pass


class TushareNewsParseError(TushareNewsError):
    pass


def _normalize(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _text_of(node: Any) -> str:
    if node is None:
        return ""
    return " ".join(node.get_text(" ", strip=True).split())


def normalize_news_sources(sources: list[str] | tuple[str, ...] | None = None) -> list[str]:
    resolved = list(sources or DEFAULT_NEWS_SOURCES)
    unknown = sorted(set(resolved) - set(DEFAULT_NEWS_SOURCES))
    if unknown:
        raise TushareNewsError(f"未知资讯来源 slug：{', '.join(unknown)}；可选：{', '.join(DEFAULT_NEWS_SOURCES)}")

    deduped: list[str] = []
    for source in resolved:
        if source not in deduped:
            deduped.append(source)
    return deduped


def load_tushare_cookie(
    cookie: str | None = None,
    cookie_file: str | Path | None = None,
    cookie_env: str = "TUSHARE_COOKIE",
    env_file: str | Path = ".env",
    validate: bool = True,
) -> str:
    if _normalize(cookie) is not None:
        resolved = str(cookie).strip()
    elif cookie_file:
        resolved = Path(cookie_file).read_text(encoding="utf-8").strip()
    else:
        env_values = read_env_file(env_file)
        resolved = _normalize(os.getenv(cookie_env)) or _normalize(env_values.get(cookie_env)) or ""

    if not resolved:
        raise TushareNewsError(f"缺少 Tushare 登录 Cookie，请设置 {cookie_env} 或传入 --cookie-file/--cookie")
    if validate:
        validate_tushare_cookie(resolved)
    return resolved


def validate_tushare_cookie(cookie: str) -> None:
    if not re.search(r"(^|;\s*)uid=", cookie) or not re.search(r"(^|;\s*)username=", cookie):
        raise TushareNewsError("Cookie 中未发现 uid/username，可能不是 Tushare 登录 Cookie")


def _request_headers(cookie: str) -> dict[str, str]:
    return {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Referer": f"{BASE_URL}/news/sina",
        "Upgrade-Insecure-Requests": "1",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
        ),
        "Cookie": cookie,
    }


def fetch_news_html(cookie: str, slug: str, timeout: float = 30.0, retries: int = 2) -> str:
    url = f"{BASE_URL}/news/{slug}"
    request = Request(url, headers=_request_headers(cookie))
    attempts = max(retries, 0) + 1
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            with urlopen(request, timeout=timeout) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return response.read().decode(charset, errors="replace")
        except HTTPError as exc:
            raise TushareNewsFetchError(f"{slug}: HTTP {exc.code} {exc.reason}") from exc
        except TimeoutError as exc:
            last_error = exc
            message = "请求超时"
        except URLError as exc:
            last_error = exc
            message = f"请求失败：{exc.reason}"
        except OSError as exc:
            last_error = exc
            message = f"请求失败：{exc}"

        if attempt < attempts:
            time.sleep(min(0.5 * attempt, 2.0))

    raise TushareNewsFetchError(f"{slug}: {message}") from last_error


def _make_soup(html: str) -> Any:
    try:
        from bs4 import BeautifulSoup
    except ImportError as exc:
        raise TushareNewsParseError("解析 Tushare 资讯页需要 beautifulsoup4，请先安装项目依赖") from exc
    return BeautifulSoup(html, "html.parser")


def parse_news_page(html: str, slug: str) -> dict[str, Any]:
    soup = _make_soup(html)
    meta: dict[str, str] = {}
    for item in soup.select("meta"):
        name = item.get("name") or item.get("property") or item.get("http-equiv")
        content = item.get("content")
        if name and content:
            meta[str(name)] = str(content)

    navigation = [
        {"text": _text_of(link), "href": urljoin(BASE_URL, link.get("href", ""))}
        for link in soup.select("#navigation a")
        if _text_of(link)
    ]

    data_sources = []
    for span in soup.select("#data_source_head span.source_name"):
        link = span.find("a")
        if not link:
            continue
        href = str(link.get("href", ""))
        data_sources.append(
            {
                "name": _text_of(link),
                "slug": href.rstrip("/").split("/")[-1],
                "href": urljoin(BASE_URL, href),
                "current": "cur" in (span.get("class") or []),
            }
        )

    channel_names = [_text_of(channel) for channel in soup.select("#channel_head .channel_name")]
    if not channel_names:
        channel_names = [
            str(container.get("id"))[len("news_") :]
            for container in soup.find_all(id=re.compile(r"^news_"))
            if str(container.get("id", "")).startswith("news_")
        ]

    channels = []
    for channel_name in channel_names:
        container = soup.find(id=f"news_{channel_name}")
        items = []
        if container:
            for index, item in enumerate(container.select(".news_item"), start=1):
                content = _text_of(item.select_one(".news_content"))
                if not content:
                    content = _text_of(item)
                if not content:
                    continue
                items.append(
                    {
                        "time": _text_of(item.select_one(".news_datetime")),
                        "content": content,
                        "position": index,
                    }
                )
        channels.append({"name": channel_name, "count": len(items), "items": items})

    current_source = next((source["name"] for source in data_sources if source["current"]), "")
    if not current_source:
        current_source = next((source["name"] for source in data_sources if source["slug"] == slug), "")

    parsed = {
        "slug": slug,
        "url": f"{BASE_URL}/news/{slug}",
        "title": _text_of(soup.title),
        "meta": meta,
        "navigation": navigation,
        "data_sources": data_sources,
        "current_source": current_source,
        "channels": channels,
        "total_items": sum(channel["count"] for channel in channels),
        "has_search": soup.select_one("#search-input") is not None and soup.select_one("#search-button") is not None,
    }
    validate_news_page(parsed, html)
    return parsed


def validate_news_page(parsed: dict[str, Any], html: str) -> None:
    if "/weborder/#/login" in html or "We're sorry but Tushare数据 doesn't work properly" in html:
        raise TushareNewsParseError("返回的是登录页或前端壳页，请更新 TUSHARE_COOKIE 后重试")
    if not parsed["data_sources"] or not parsed["current_source"]:
        raise TushareNewsParseError("未解析到资讯来源导航，可能是 Cookie 失效或页面结构变化")
    if not parsed["channels"]:
        raise TushareNewsParseError("未解析到频道列表，可能是页面结构变化")


def _extract_title_body(content: str) -> tuple[str, str]:
    bracket_match = re.match(r"^【([^】]{1,120})】\s*(.*)$", content)
    if bracket_match:
        return bracket_match.group(1).strip(), bracket_match.group(2).strip()

    if "|" in content:
        title, body = content.split("|", 1)
        title = title.strip()
        body = body.strip()
        if 0 < len(title) <= 120 and body:
            return title, body
    return "", content


def _normalize_hash_text(value: str) -> str:
    return " ".join(value.strip().split())


def _hash_parts(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def _content_hash(title: str, body: str, content: str) -> str:
    if title or body:
        return _hash_parts(_normalize_hash_text(title), _normalize_hash_text(body))
    return _hash_parts(_normalize_hash_text(content))


def _resolved_datetime(publish_date: str | None, publish_time: str) -> str | None:
    if publish_date is None:
        return None
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", publish_date):
        raise TushareNewsError("publish_date 必须是 YYYY-MM-DD 格式")
    if not re.fullmatch(r"\d{2}:\d{2}(:\d{2})?", publish_time):
        return None
    time_text = publish_time if publish_time.count(":") == 2 else f"{publish_time}:00"
    return f"{publish_date} {time_text}"


def build_news_records(
    pages: list[dict[str, Any]],
    fetched_at: str | None = None,
    publish_date: str | None = None,
) -> list[dict[str, Any]]:
    resolved_fetched_at = fetched_at or _now_iso()
    records: list[dict[str, Any]] = []
    for page in pages:
        source_name = page.get("current_source", "")
        for channel in page.get("channels", []):
            for item in channel.get("items", []):
                content = str(item.get("content", "")).strip()
                title, body = _extract_title_body(content)
                publish_time = str(item.get("time", "")).strip()
                content_hash = _content_hash(title, body, content)
                record = {
                    "id": _hash_parts(page["slug"], channel["name"], publish_time, content),
                    "content_hash": content_hash,
                    "dedupe_key": _hash_parts(page["slug"], channel["name"], publish_time, content_hash),
                    "src": page["slug"],
                    "source": source_name,
                    "source_name": source_name,
                    "source_url": page["url"],
                    "channel": channel["name"],
                    "time": publish_time,
                    "datetime": _resolved_datetime(publish_date, publish_time),
                    "title": title,
                    "content": content,
                    "body": body,
                    "sequence": len(records) + 1,
                    "channel_sequence": item.get("position"),
                    "fetched_at": resolved_fetched_at,
                    "source_kind": "tushare_news_page",
                }
                records.append(record)
    return records


def build_news_summary(pages: list[dict[str, Any]], fetched_at: str) -> dict[str, Any]:
    return {
        "base_url": f"{BASE_URL}/news",
        "fetched_at": fetched_at,
        "source_kind": "tushare_news_page",
        "sources": [
            {
                "slug": page["slug"],
                "name": page["current_source"],
                "url": page["url"],
                "channels": [{"name": channel["name"], "count": channel["count"]} for channel in page["channels"]],
                "total_items": page["total_items"],
            }
            for page in pages
        ],
    }


def crawl_tushare_news(
    cookie: str,
    sources: list[str] | tuple[str, ...] | None = None,
    timeout: float = 30.0,
    delay: float = 0.3,
    retries: int = 2,
    publish_date: str | None = None,
) -> dict[str, Any]:
    resolved_sources = normalize_news_sources(sources)
    fetched_at = _now_iso()
    pages = []
    for index, slug in enumerate(resolved_sources, start=1):
        pages.append(parse_news_page(fetch_news_html(cookie, slug, timeout=timeout, retries=retries), slug))
        if index < len(resolved_sources) and delay > 0:
            time.sleep(delay)

    payload = build_news_summary(pages, fetched_at)
    payload["records"] = build_news_records(pages, fetched_at=fetched_at, publish_date=publish_date)
    return payload
