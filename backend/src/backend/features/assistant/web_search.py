"""One bounded search request; never fetch model-supplied URLs."""

import base64
import ipaddress
import json
from html.parser import HTMLParser
from urllib.error import URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.core.security import unavailable


class SearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=200)

    @field_validator("query")
    @classmethod
    def nonblank(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("搜索词不能为空")
        return value


WEB_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "联网搜索公开网页，返回最多五条网页摘要和真实来源；只发送公开搜索词，不发送用户个人或应用内数据",
        "parameters": SearchInput.model_json_schema(),
    },
}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise URLError("搜索服务重定向被拒绝")


def public_url(value):
    if (
        not isinstance(value, str)
        or len(value) > 1000
        or any(char.isspace() or ord(char) < 32 or char == "\\" for char in value)
    ):
        return False
    try:
        url = urlsplit(value)
        host = url.hostname.rstrip(".") if url.hostname else None
        if (
            url.scheme not in {"http", "https"}
            or not host
            or url.username is not None
            or url.password is not None
            or url.port not in {None, 80, 443}
            or host in {"localhost", "localhost.localdomain"}
            or host.endswith((".localhost", ".local", ".internal"))
        ):
            return False
        try:
            return ipaddress.ip_address(host).is_global
        except ValueError:
            return "." in host and not (
                host.split(".")[-1].isdigit() or host.split(".")[-1].startswith("0x")
            )
    except ValueError:
        return False


class SearchResults(HTMLParser):
    def __init__(self):
        super().__init__()
        self.results = []
        self.depth = 0
        self.title = False
        self.snippet = False
        self.row = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "li":
            if self.depth:
                self.depth += 1
            elif "b_algo" in attrs.get("class", "").split():
                self.depth = 1
                self.row = {"title": "", "url": "", "content": ""}
        if not self.depth:
            return
        if tag == "h2":
            self.title = True
        if tag == "a" and self.title:
            self.row["url"] = attrs.get("href", "")
        if tag == "p":
            self.snippet = True

    def handle_data(self, data):
        if self.depth:
            if self.title:
                self.row["title"] += data
            if self.snippet:
                self.row["content"] += data

    def handle_endtag(self, tag):
        if not self.depth:
            return
        if tag == "h2":
            self.title = False
        if tag == "p":
            self.snippet = False
        if tag == "li":
            self.depth -= 1
            if not self.depth:
                parsed = urlsplit(self.row["url"])
                encoded = parse_qs(parsed.query).get("u", [""])[0]
                if (
                    parsed.hostname in {"www.bing.com", "cn.bing.com"}
                    and parsed.path == "/ck/a"
                    and encoded.startswith("a1")
                ):
                    value = encoded[2:]
                    self.row["url"] = base64.urlsafe_b64decode(
                        value + "=" * (-len(value) % 4)
                    ).decode("utf-8")
                for field, limit in (("title", 150), ("content", 1500)):
                    self.row[field] = " ".join(self.row[field].split())[:limit]
                self.results.append(self.row)
                self.title = self.snippet = False


def search_web(arguments):
    query = SearchInput.model_validate(arguments).query
    request = Request(
        "https://cn.bing.com/search?" + urlencode({"q": query, "mkt": "zh-CN"}),
        headers={"User-Agent": "Mozilla/5.0 (compatible; ai-agent/0.1)"},
    )
    try:
        # ponytail: public HTML can change or rate-limit; replace this adapter if reliability becomes insufficient.
        with build_opener(NoRedirect()).open(request, timeout=10) as response:
            if response.status != 200:
                raise ValueError("搜索服务要求验证")
            raw = response.read(262145)
        if len(raw) > 262144:
            raise ValueError("响应过大")
        html = raw.decode("utf-8")
        if (
            "<html" not in html.lower()
            or "anomaly.js" in html
            or "anomaly-modal" in html
            or "b_captcha" in html
            or "b_results" not in html
        ):
            raise ValueError("无效搜索响应或验证码")
        parser = SearchResults()
        parser.feed(html)
        results, seen = [], set()
        for result in parser.results:
            if (
                not result["title"]
                or not public_url(result["url"])
                or result["url"] in seen
            ):
                continue
            seen.add(result["url"])
            results.append(result)
            if len(results) == 5:
                break
        return results
    except URLError, OSError, ValueError, TypeError:
        raise unavailable(
            "免费联网搜索暂时不可用或被限流，请稍后重试；尚未执行任何创建操作"
        ) from None


def search_messages(message, sources):
    call = message.tool_calls[0]
    return [
        {
            "role": "assistant",
            "content": message.content,
            "tool_calls": [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": "web_search",
                        "arguments": call.function.arguments,
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": call.id,
            "content": json.dumps({"untrusted_results": sources}, ensure_ascii=False),
        },
    ]


def with_sources(message, sources):
    message = message.replace("参考来源：", "提及资料：")
    if not sources:
        return message
    references = "\n".join(
        f"{index}. {source['title']}\n{source['url']}"
        for index, source in enumerate(sources, 1)
    )
    return f"{message}\n\n参考来源：\n{references}"
