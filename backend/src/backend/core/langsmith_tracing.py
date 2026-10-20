"""上传脱敏后的执行内容；凭据、身份及异常原文不进入 LangSmith。"""

import hashlib
import logging
import os
from functools import lru_cache, wraps

from langchain_core.tracers.context import tracing_v2_enabled
from langsmith import Client, trace, tracing_context
from langsmith.wrappers import wrap_openai

from backend.core.security import settings
from backend.core.trace_redaction import redact_payload, redaction_scope

logger = logging.getLogger(__name__)


def safe_metadata(data):
    if "error" in data:
        return {"error": "执行失败（详情已隐藏）"}
    safe = {}
    if data.get("environment") in {"development", "production", "test", "staging"}:
        safe["environment"] = data["environment"]
    value = data.get("run_ref", "")
    if (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    ):
        safe["run_ref"] = value
    return safe


def safe_run_ops(runs):
    """采用字段白名单，覆盖输入输出以外的 error/events/serialized 泄漏面。"""
    allowed = {
        "id",
        "trace_id",
        "parent_run_id",
        "dotted_order",
        "name",
        "run_type",
        "start_time",
        "end_time",
        "session_name",
    }
    result = []
    for run in runs:
        safe = {key: value for key, value in run.items() if key in allowed}
        for field in ("inputs", "outputs"):
            if field in run:
                safe[field] = redact_payload(run[field])
        if "error" in run:
            safe["error"] = "执行失败（详情已隐藏）" if run["error"] else None
        metadata = run.get("extra", {}).get("metadata", {})
        safe["extra"] = {"metadata": safe_metadata(metadata)}
        result.append(safe)
    return result


@lru_cache(maxsize=2)
def _client(pid, api_key, endpoint, workspace_id):
    # PID 隔离 Celery prefork 后的队列和后台线程，不缓存父进程客户端。
    return Client(
        api_key=api_key,
        api_url=endpoint,
        workspace_id=workspace_id or None,
        timeout_ms=2000,
        hide_inputs=redact_payload,
        hide_outputs=redact_payload,
        hide_metadata=safe_metadata,
        omit_traced_runtime_info=True,
        process_buffered_run_ops=safe_run_ops,
        run_ops_buffer_size=100,
        run_ops_buffer_timeout_ms=1000,
    )


def get_client():
    key = settings.langsmith_api_key.get_secret_value()
    if not settings.langsmith_tracing or not key:
        return None
    try:
        return _client(
            os.getpid(),
            key,
            settings.langsmith_endpoint,
            settings.langsmith_workspace_id,
        )
    except Exception:  # noqa: BLE001 -- 观测配置故障不能中断业务。
        logger.warning("LangSmith 初始化失败，已跳过追踪（详情已隐藏）")
        return None


def observed(function):
    """同时绑定 LangGraph callbacks 和 SDK 上下文；不捕获或重跑业务异常。"""

    @wraps(function)
    def wrapped(*args, **kwargs):
        client = get_client()
        if client is None:
            with tracing_context(enabled=False):
                return function(*args, **kwargs)
        project = settings.langsmith_project or f"ai-agent-{settings.app_env}"
        metadata = {"environment": settings.app_env}
        if function.__name__ in {"execute_run", "execute_plan"}:
            run_id = args[0] if args else kwargs.get("run_id", "")
            metadata["run_ref"] = hashlib.sha256(str(run_id).encode()).hexdigest()
        with (
            redaction_scope(),
            tracing_context(enabled=True, client=client, project_name=project),
            tracing_v2_enabled(project_name=project, client=client),
            trace(
                function.__name__,
                inputs={},
                metadata=metadata,
                client=client,
                project_name=project,
            ),
        ):
            return function(*args, **kwargs)

    return wrapped


def traced_model(client):
    tracing_client = get_client()
    if tracing_client is None:
        return client
    return wrap_openai(client, tracing_extra={"client": tracing_client})


def flush_traces():
    client = get_client()
    if client is not None:
        try:
            client.flush(timeout=3)
        except Exception:  # noqa: BLE001 -- 关闭追踪不能影响业务退出。
            logger.warning("LangSmith 刷新失败（详情已隐藏）")
