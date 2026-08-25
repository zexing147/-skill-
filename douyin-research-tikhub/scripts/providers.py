from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable


def redact_error_body(body: str) -> str:
    """Redact credentials that some upstream error responses echo in headers."""
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return re.sub(r"(?i)(authorization|cookie|api[_-]?key|token)(\\s*[:=]\\s*)[^,}\\s]+",
                      r"\\1\\2[REDACTED_SECRET]", body)

    def scrub(value: Any) -> Any:
        if isinstance(value, dict):
            result = {}
            for key, child in value.items():
                lowered = str(key).lower().replace("-", "_")
                if ("authorization" in lowered or "cookie" in lowered
                        or "token" in lowered or "api_key" in lowered
                        or lowered == "headers"):
                    result[key] = "[REDACTED_SECRET]"
                else:
                    result[key] = scrub(child)
            return result
        if isinstance(value, list):
            return [scrub(child) for child in value]
        return value

    return json.dumps(scrub(payload), ensure_ascii=False)


class ProviderError(RuntimeError):
    pass


class BudgetExceeded(ProviderError):
    pass


@dataclass
class Page:
    items: list[dict[str, Any]]
    next_cursor: str
    has_more: bool
    raw: dict[str, Any]


def deep_find(node: Any, names: tuple[str, ...]) -> Any:
    queue = [node]
    while queue:
        current = queue.pop(0)
        if isinstance(current, dict):
            for name in names:
                if name in current and current[name] is not None:
                    return current[name]
            queue.extend(current.values())
        elif isinstance(current, list):
            queue.extend(current)
    return None


def first(mapping: dict[str, Any], *paths: str) -> Any:
    for path in paths:
        value: Any = mapping
        for part in path.split("."):
            if not isinstance(value, dict) or part not in value:
                break
            value = value[part]
        else:
            if value is not None:
                return value
    return None


def as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes"}
    return False


def response_data(raw: dict[str, Any]) -> dict[str, Any]:
    data = raw.get("data")
    return data if isinstance(data, dict) else raw


def extract_url(text: str) -> str | None:
    match = re.search(r"https?://[^\s\]\[<>\"']+", text)
    return match.group(0).rstrip(".,，。；;!！") if match else None


def resolve_sec_user_id(value: str, timeout: int = 30) -> str:
    value = value.strip()
    if re.fullmatch(r"MS4wLjAB[A-Za-z0-9_-]+", value):
        return value
    url = extract_url(value) or (value if value.startswith("http") else None)
    if not url:
        raise ProviderError("账号标识不是可识别的 sec_user_id 或抖音主页 URL")

    def parse(candidate: str) -> str | None:
        parsed = urllib.parse.urlparse(candidate)
        match = re.search(r"/user/([^/?#]+)", parsed.path)
        if match:
            return urllib.parse.unquote(match.group(1))
        query = urllib.parse.parse_qs(parsed.query)
        for key in ("sec_uid", "sec_user_id"):
            if query.get(key):
                return query[key][0]
        return None

    direct = parse(url)
    if direct:
        return direct
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            final_url = response.geturl()
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ProviderError(f"主页短链重定向失败：{exc}") from exc
    resolved = parse(final_url)
    if not resolved:
        raise ProviderError("短链最终地址中没有 sec_user_id；请复制完整 /user/... 主页 URL")
    return resolved


class TikHubProvider:
    name = "tikhub"

    def __init__(self, base_url: str, max_api_calls: int,
                 usage_callback: Callable[[dict[str, Any]], None] | None = None,
                 timeout: int = 60, retries: int = 3) -> None:
        parsed = urllib.parse.urlparse(base_url)
        allowed = {"api.tikhub.dev", "api.tikhub.io"}
        if (parsed.scheme != "https" or parsed.hostname not in allowed or parsed.username
                or parsed.password or parsed.port not in (None, 443)
                or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
            raise ProviderError("base_url 必须是 https://api.tikhub.dev 或 https://api.tikhub.io")
        api_key = os.environ.get("TIKHUB_API_KEY", "").strip()
        if not api_key:
            raise ProviderError("缺少环境变量 TIKHUB_API_KEY")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.max_api_calls = max_api_calls
        self.usage_callback = usage_callback
        self.timeout = timeout
        self.retries = retries
        self.calls = 0

    def _record(self, operation: str, status: str,
                http_status: int | None, error: str | None) -> None:
        if self.usage_callback:
            self.usage_callback({"operation": operation, "status": status,
                                 "http_status": http_status, "error": error})

    def _get(self, operation: str, path: str, params: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}{path}?{urllib.parse.urlencode(params)}"
        last_error: Exception | None = None
        for attempt in range(self.retries):
            if self.calls >= self.max_api_calls:
                raise BudgetExceeded(f"达到 API 请求硬上限 {self.max_api_calls}")
            self.calls += 1
            request = urllib.request.Request(url, headers={
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/json",
                "User-Agent": "douyin-research-tikhub/1.0",
            })
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    status = response.status
                    payload = json.loads(response.read().decode("utf-8"))
                code = payload.get("code") if isinstance(payload, dict) else None
                if status == 200 and code in (None, 200):
                    self._record(operation, "ok", status, None)
                    return payload
                message = str(payload.get("message_zh") or payload.get("message") or code)
                self._record(operation, "business_error", status, message)
                raise ProviderError(f"TikHub 业务错误：{message}")
            except urllib.error.HTTPError as exc:
                body = redact_error_body(exc.read().decode("utf-8", errors="replace")[:1000])
                last_error = exc
                self._record(operation, "http_error", exc.code, body)
                if exc.code not in (429, 500, 502, 503, 504) or attempt + 1 >= self.retries:
                    raise ProviderError(f"TikHub HTTP {exc.code}: {body}") from exc
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = exc
                self._record(operation, "transport_error", None, str(exc))
                if attempt + 1 >= self.retries:
                    raise ProviderError(f"TikHub 请求失败：{exc}") from exc
            time.sleep(2 ** attempt)
        raise ProviderError(f"TikHub 请求失败：{last_error}")

    def get_account(self, sec_user_id: str) -> dict[str, Any]:
        return self._get("user_profile", "/api/v1/douyin/app/v3/handler_user_profile",
                         {"sec_user_id": sec_user_id})

    def list_videos(self, sec_user_id: str, cursor: str, count: int = 20) -> Page:
        raw = self._get("user_videos", "/api/v1/douyin/app/v3/fetch_user_post_videos", {
            "sec_user_id": sec_user_id, "max_cursor": cursor, "count": min(count, 20),
            "sort_type": 0, "channel": "normal",
        })
        data = response_data(raw)
        items = data.get("aweme_list") or data.get("item_list") or []
        next_cursor = data.get("max_cursor", data.get("cursor"))
        return Page(items if isinstance(items, list) else [], str(next_cursor or ""),
                    as_bool(data.get("has_more")), raw)

    def list_comments(self, aweme_id: str, cursor: str) -> Page:
        raw = self._get("video_comments", "/api/v1/douyin/app/v3/fetch_video_comments",
                        {"aweme_id": aweme_id, "cursor": cursor, "count": 20})
        data = response_data(raw)
        items = data.get("comments") or data.get("comment_list") or []
        next_cursor = data.get("cursor", data.get("max_cursor"))
        return Page(items if isinstance(items, list) else [], str(next_cursor or ""),
                    as_bool(data.get("has_more")), raw)

    def list_replies(self, aweme_id: str, comment_id: str, cursor: str) -> Page:
        raw = self._get("comment_replies", "/api/v1/douyin/app/v3/fetch_video_comment_replies", {
            "item_id": aweme_id, "comment_id": comment_id, "cursor": cursor, "count": 20,
        })
        data = response_data(raw)
        items = data.get("comments") or data.get("comment_list") or data.get("replies") or []
        next_cursor = data.get("cursor", data.get("max_cursor"))
        return Page(items if isinstance(items, list) else [], str(next_cursor or ""),
                    as_bool(data.get("has_more")), raw)


class MediaCrawlerProvider:
    """Local MediaCrawler adapter boundary.

    The first routing release deliberately does not start a crawler process:
    MediaCrawler requires a separately installed environment and interactive
    Douyin login. Keeping this provider explicit prevents accidental fallback
    or uncontrolled browser launches.
    """

    name = "mediacrawler"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.calls = 0
        self.usage_callback = kwargs.get("usage_callback")

    def _unavailable(self) -> None:
        raise ProviderError(
            "MediaCrawler 备用 Provider 尚未配置：请先安装 MediaCrawler、启动登录态，"
            "并配置 crawler 命令；本次未启动浏览器或发起采集。"
        )

    def get_account(self, sec_user_id: str) -> dict[str, Any]:
        self._unavailable()

    def list_videos(self, sec_user_id: str, cursor: str, count: int = 20) -> Page:
        self._unavailable()

    def list_comments(self, aweme_id: str, cursor: str) -> Page:
        self._unavailable()

    def list_replies(self, aweme_id: str, comment_id: str, cursor: str) -> Page:
        self._unavailable()


def create_provider(name: str, **kwargs: Any) -> Any:
    normalized = name.strip().lower()
    if normalized == "tikhub":
        return TikHubProvider(**kwargs)
    if normalized == "mediacrawler":
        return MediaCrawlerProvider(**kwargs)
    raise ProviderError(f"不支持的 provider：{name}；可选 tikhub 或 mediacrawler")


def normalize_account(sec_user_id: str, raw: dict[str, Any], input_ref: str) -> dict[str, Any]:
    user = deep_find(raw, ("user", "user_info"))
    if not isinstance(user, dict):
        user = raw.get("data") if isinstance(raw.get("data"), dict) else {}
    return {"sec_user_id": str(first(user, "sec_uid", "sec_user_id") or sec_user_id),
            "input_ref": input_ref, "profile_url": f"https://www.douyin.com/user/{sec_user_id}",
            "nickname": first(user, "nickname"), "signature": first(user, "signature"),
            "follower_count": as_int(first(user, "follower_count", "mplatform_followers_count")),
            "following_count": as_int(first(user, "following_count")),
            "total_favorited": as_int(first(user, "total_favorited", "favoriting_count")),
            "aweme_count": as_int(first(user, "aweme_count")), "raw_json": raw}


def normalize_video(sec_user_id: str, item: dict[str, Any]) -> dict[str, Any] | None:
    aweme_id = first(item, "aweme_id", "item_id", "id")
    if aweme_id is None:
        return None
    stats = first(item, "statistics", "stats")
    stats = stats if isinstance(stats, dict) else {}
    author = item.get("author") if isinstance(item.get("author"), dict) else {}
    return {"aweme_id": str(aweme_id),
            "sec_user_id": str(first(author, "sec_uid", "sec_user_id") or sec_user_id),
            "description": first(item, "desc", "description", "title"),
            "create_time": as_int(first(item, "create_time")),
            "duration_ms": as_int(first(item, "duration", "video.duration")),
            "video_url": f"https://www.douyin.com/video/{aweme_id}",
            "play_count": as_int(first(stats, "play_count")),
            "like_count": as_int(first(stats, "digg_count", "like_count")),
            "comment_count": as_int(first(stats, "comment_count")),
            "collect_count": as_int(first(stats, "collect_count")),
            "share_count": as_int(first(stats, "share_count")), "raw_json": item}


def normalize_comment(aweme_id: str, item: dict[str, Any],
                      parent_comment_id: str | None = None) -> dict[str, Any] | None:
    comment_id = first(item, "cid", "comment_id", "id")
    if comment_id is None:
        return None
    user = item.get("user") if isinstance(item.get("user"), dict) else {}
    return {"comment_id": str(comment_id), "aweme_id": aweme_id,
            "parent_comment_id": parent_comment_id,
            "author_id": first(user, "uid", "user_id", "sec_uid"),
            "author_name": first(user, "nickname", "name"),
            "content": first(item, "text", "content"),
            "like_count": as_int(first(item, "digg_count", "like_count")),
            "reply_count": as_int(first(item, "reply_comment_total", "reply_count")),
            "create_time": as_int(first(item, "create_time")), "raw_json": item}
