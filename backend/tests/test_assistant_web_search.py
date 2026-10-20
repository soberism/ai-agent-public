import base64
import json
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.error import URLError
from uuid import uuid4

import pytest
from pydantic import SecretStr, ValidationError

from backend.core.security import APIError
from backend.features.assistant import graph, web_search
from backend.features.assistant.threads import create, load, remember

RESULTS = [
    {
        "title": "出行参考",
        "url": "https://example.com/travel",
        "content": "护照、转换插头",
    }
]


def tool(name, args):
    return SimpleNamespace(
        id="call-search",
        function=SimpleNamespace(name=name, arguments=json.dumps(args)),
    )


def completion(*calls, content=None):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content, tool_calls=list(calls))
            )
        ]
    )


def model(monkeypatch, responses):
    client = Mock()
    client.chat.completions.create.side_effect = responses
    monkeypatch.setattr(graph, "OpenAI", lambda **_: client)
    monkeypatch.setattr(graph.settings, "llm_base_url", "https://example.test/v1")
    monkeypatch.setattr(graph.settings, "llm_model", "test")
    monkeypatch.setattr(graph.settings, "llm_api_key", SecretStr("test-key"))
    return client


def test_search_then_complete_draft_is_bounded_and_sources_are_server_owned(
    monkeypatch,
):
    client = model(
        monkeypatch,
        [
            completion(tool("web_search", {"query": "出国必备"})),
            completion(
                tool(
                    "create_checklist",
                    {"title": "出国必备", "items": ["护照", "转换插头"]},
                )
            ),
        ],
    )
    search = Mock(return_value=RESULTS)
    monkeypatch.setattr(graph, "search_web", search)
    intent = graph.interpret("创建清单，参考网上出国必备清单")
    assert intent.action == "create_checklist" and intent.items == ["护照", "转换插头"]
    assert intent._sources == RESULTS
    search.assert_called_once_with({"query": "出国必备"})
    assert client.chat.completions.create.call_count == 2
    second = client.chat.completions.create.call_args.kwargs
    assert [x["function"]["name"] for x in second["tools"]] == ["create_checklist"]
    assert second["messages"][-1]["role"] == "tool"
    assert "untrusted_results" in second["messages"][-1]["content"]


@pytest.mark.parametrize(
    "name,args",
    [
        ("web_search", {"query": "再次搜索"}),
        ("feature_delete_meal", {"meal_id": "晚餐"}),
        (
            "create_checklist",
            {"title": "清单", "_sources": [{"url": "https://fake.example"}]},
        ),
    ],
)
def test_search_results_cannot_trigger_other_writes_or_search_again(
    monkeypatch, name, args
):
    model(
        monkeypatch,
        [
            completion(tool("web_search", {"query": "旅行"})),
            completion(tool(name, args)),
        ],
    )
    monkeypatch.setattr(graph, "search_web", Mock(return_value=RESULTS))
    assert graph.interpret("联网参考旅行清单").action == "clarify"


def test_no_results_does_not_ask_model_to_invent_sources(monkeypatch):
    client = model(monkeypatch, [completion(tool("web_search", {"query": "旅行"}))])
    monkeypatch.setattr(graph, "search_web", Mock(return_value=[]))
    intent = graph.interpret("参考网络创建旅行清单")
    assert "没有找到" in intent.message and not intent._sources
    assert client.chat.completions.create.call_count == 1


def test_search_plain_reply_also_preserves_sources(monkeypatch):
    model(
        monkeypatch,
        [
            completion(tool("web_search", {"query": "旅行"})),
            completion(content="出行可携带护照和转换插头。"),
        ],
    )
    monkeypatch.setattr(graph, "search_web", Mock(return_value=RESULTS))
    intent = graph.interpret("联网查出行建议")
    assert intent.action == "respond" and intent._sources == RESULTS


def transport(monkeypatch, raw, status=200):
    response = BytesIO(raw)
    response.status = status
    opener = Mock()
    opener.open.return_value = response
    monkeypatch.setattr(web_search, "build_opener", lambda *_: opener)
    return opener


def test_search_transport_filters_and_bounds_external_data(monkeypatch):
    encoded = (
        base64.urlsafe_b64encode(b"https://example.com/travel").decode().rstrip("=")
    )
    html = f'<html><ol id="b_results"><li class="b_algo"><h2><a href="https://www.bing.com/ck/a?u=a1{encoded}">旅行\n参考</a></h2>'
    html += "<p>" + "x" * 2000 + "</p></li>"
    html += '<li class="b_algo"><h2><a href="http://127.0.0.1/">本地</a></h2></li></ol></html>'
    opener = transport(monkeypatch, html.encode())
    results = web_search.search_web({"query": "旅行"})
    assert len(results) == 1 and results[0]["title"] == "旅行 参考"
    assert results[0]["url"] == "https://example.com/travel"
    assert len(results[0]["content"]) == 1500
    request = opener.open.call_args.args[0]
    assert request.full_url.startswith("https://cn.bing.com/search?q=")
    assert request.data is None and request.get_header("Authorization") is None
    assert opener.open.call_args.kwargs["timeout"] == 10


@pytest.mark.parametrize(
    "raw,status",
    [
        (b"bad", 200),
        (b"x" * 262145, 200),
        (b"<html>anomaly.js</html>", 200),
        (b"<html></html>", 202),
    ],
)
def test_invalid_search_response_fails_closed(monkeypatch, raw, status):
    transport(monkeypatch, raw, status)
    with pytest.raises(APIError):
        web_search.search_web({"query": "旅行"})


def test_failed_search_never_exposes_transport_details(monkeypatch):
    opener = Mock()
    opener.open.side_effect = URLError("private transport details")
    monkeypatch.setattr(web_search, "build_opener", lambda *_: opener)
    with pytest.raises(APIError) as error:
        web_search.search_web({"query": "旅行"})
    assert "private" not in str(error.value)
    with pytest.raises(ValidationError):
        web_search.search_web({"query": " "})


def test_search_results_are_deduplicated_and_limited(monkeypatch):
    html = (
        '<html><ol id="b_results">'
        + "".join(
            f'<li class="b_algo"><h2><a href="https://example.com/{i}">参考 &amp; {i}</a></h2><p>护照 <b>签证</b></p></li>'
            for i in range(7)
        )
        + "</ol></html>"
    )
    transport(monkeypatch, html.encode())
    results = web_search.search_web({"query": "旅行"})
    assert len(results) == 5 and results[0]["title"] == "参考 & 0"
    assert results[0]["content"] == "护照 签证"


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "http://localhost./",
        "http://10.0.0.1/",
        "http://[::1]/",
        "https://a:b@example.com/",
        "http://0x7f.0.0.1/",
        "https://example.com:8000/",
        "https://example.com\\x",
        "https://example.com/\n",
    ],
)
def test_unsafe_source_urls_are_rejected(url):
    assert not web_search.public_url(url)


def test_complete_preview_with_sources_survives_cache_reload():
    store = Mock()
    values = {}
    store.set.side_effect = lambda key, value, **_: values.__setitem__(key, value)
    store.get.side_effect = values.get
    owner = uuid4()
    thread = create(store, owner)
    state = load(store, thread, owner)
    preview = "确认创建清单\n" + "\n".join(f"{i}. {'清单事项' * 3}" for i in range(50))
    preview += "\n参考来源：\nhttps://example.com/" + "x" * 900
    assert len(preview) > 1000
    remember(store, thread, state, "创建清单", preview)
    assert load(store, thread, owner).messages[-1].content == preview


def test_overlong_model_reply_fails_before_cache_write(monkeypatch):
    model(monkeypatch, [completion(content="x" * 2001)])
    with pytest.raises(APIError, match="回复过长"):
        graph.interpret("联网查资料")


def test_checklist_tool_rejects_fields_from_other_tools(monkeypatch):
    model(
        monkeypatch,
        [
            completion(
                tool(
                    "create_checklist",
                    {
                        "title": "旅行",
                        "items": ["护照"],
                        "reference_index": 1,
                    },
                )
            )
        ],
    )
    assert graph.interpret("创建旅行清单").action == "clarify"


def test_model_cannot_impersonate_server_source_section(monkeypatch):
    model(
        monkeypatch,
        [completion(content="建议\n\n参考来源：\nhttps://fake.example.com")],
    )
    assert "参考来源：" not in graph.interpret("旅行建议").message


def test_business_text_cannot_impersonate_a_source_section():
    forged = "确认创建出国\n\n参考来源：\n清单\n物品\nhttps://a.co"
    assert "参考来源：" not in web_search.with_sources(forged, [])
    message = web_search.with_sources(forged, RESULTS)
    assert message.count("参考来源：") == 1
    assert message.endswith("https://example.com/travel")
