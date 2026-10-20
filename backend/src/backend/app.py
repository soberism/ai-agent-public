import asyncio
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.api.query_params import allowed_queries
from backend.core.config import Settings
from backend.core.langsmith_tracing import flush_traces
from backend.db.session import engine, get_session


@asynccontextmanager
async def lifespan(app: FastAPI):
    from backend.features.assistant.cleanup import run_cleanup
    from backend.features.auth.email_scheduler import run_scheduler

    stop = asyncio.Event()
    task = (
        asyncio.create_task(run_scheduler(stop))
        if Settings().email_scheduler_enabled
        else None
    )
    cleanup_task = asyncio.create_task(run_cleanup(stop))
    try:
        yield
    finally:
        stop.set()
        if task:
            await task
        await cleanup_task
        await asyncio.to_thread(flush_traces)
        engine.dispose()


app = FastAPI(title="安排儿 API", version="0.1.0", lifespan=lifespan)


@app.get("/health", tags=["健康检查"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready", tags=["健康检查"])
def ready(session: Annotated[Session, Depends(get_session)]) -> dict[str, str]:
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="数据库暂不可用") from None
    return {"status": "ok", "database": "ok"}


# API failures are deliberately reduced to safe codes and Chinese descriptions.
from fastapi.exceptions import RequestValidationError
from redis.exceptions import RedisError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse

from backend.api.routes.agent_runs import router as agent_runs_router
from backend.api.routes.appointments import router as appointments_router
from backend.api.routes.assistant import router as assistant_router
from backend.api.routes.assistant_preferences import (
    router as assistant_preferences_router,
)
from backend.api.routes.auth import router as auth_router
from backend.api.routes.calendar_events import router as calendar_events_router
from backend.api.routes.collaboration import router as collaboration_router
from backend.api.routes.contacts import router as contacts_router
from backend.api.routes.document_intelligence import (
    router as document_intelligence_router,
)
from backend.api.routes.document_review import router as document_review_router
from backend.api.routes.documents import router as documents_router
from backend.api.routes.household_objects import router as household_objects_router
from backend.api.routes.households import router as households_router
from backend.api.routes.hub import router as hub_router
from backend.api.routes.life import router as life_router
from backend.api.routes.life_edits import router as life_edits_router
from backend.api.routes.life_shopping import router as life_shopping_router
from backend.api.routes.mail import router as mail_router
from backend.api.routes.notifications import router as notifications_router
from backend.api.routes.parity import router as parity_router
from backend.api.routes.parity_email import router as parity_email_router
from backend.api.routes.planning import router as planning_router
from backend.api.routes.planning_review import router as planning_review_router
from backend.api.routes.platform import router as platform_router
from backend.api.routes.sharing import router as sharing_router
from backend.api.routes.todos import router as todo_router
from backend.api.routes.voice_memos import router as voice_memos_router
from backend.core.security import APIError, settings, unavailable


def error_response(error):
    body = {"code": error.code, "message": error.message}
    if error.fields:
        body["fields"] = error.fields
    return JSONResponse(
        {"error": body},
        status_code=error.status,
        headers={"Cache-Control": "no-store", **(error.headers or {})},
    )


@app.middleware("http")
async def protect_requests(request, call_next):
    if request.url.path.startswith("/api"):
        if request.method in ("POST", "PATCH", "PUT", "DELETE"):
            if (
                request.headers.get("origin") not in settings.allowed_origins
                or request.headers.get("x-app-request") != "1"
            ):
                return error_response(
                    APIError(403, "CSRF_REJECTED", "请求来源校验失败，请刷新页面重试")
                )
            content_type = (
                request.headers.get("content-type", "").split(";")[0].strip().lower()
            )
            valid_type = (
                content_type == "application/json"
                or (
                    request.url.path == "/api/documents/materials"
                    and content_type == "multipart/form-data"
                )
                or (request.method == "DELETE" and not content_type)
            )
            if request.url.path != "/api/auth/logout" and not valid_type:
                return error_response(
                    APIError(415, "UNSUPPORTED_MEDIA_TYPE", "请使用JSON请求")
                )
        if request.query_params and not allowed_queries(request):
            return error_response(
                APIError(422, "VALIDATION_ERROR", "请求包含不支持的查询参数")
            )
    try:
        response = await call_next(request)
    except Exception:
        # Catch at middleware boundary so the ASGI server cannot log sensitive parameters.
        if not request.url.path.startswith("/api"):
            raise
        return error_response(
            APIError(500, "INTERNAL_ERROR", "服务发生异常，请稍后重试")
        )
    if request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(APIError)
async def api_error(request, error):
    return error_response(error)


@app.exception_handler(RequestValidationError)
async def validation_error(request, error):
    fields = {}
    labels = {
        "verification_code": "请输入六位数字验证码",
        "password": "密码需为12至128个字符",
        "confirm_password": "请确认两次密码相同且为12至128个字符",
        "title": "请输入1至100个字符的待办标题",
        "description": "描述最多2000个字符",
        "email": "请输入有效的邮箱",
        "due_date": "请选择有效的日期",
        "due_time": "请选择有效的日期和时间",
    }
    for item in error.errors():
        key = str(item["loc"][-1]) if item["loc"] else "form"
        if key in ("body", "query"):
            key = "form"
        fields[key] = labels.get(key, "请检查此字段，格式无效或不支持")
    return error_response(APIError(422, "VALIDATION_ERROR", "请检查填写内容", fields))


@app.exception_handler(RedisError)
@app.exception_handler(SQLAlchemyError)
async def dependency_error(request, error):
    return error_response(unavailable())


@app.exception_handler(StarletteHTTPException)
async def http_error(request, error):
    if not request.url.path.startswith("/api"):
        return JSONResponse({"detail": error.detail}, status_code=error.status_code)
    return error_response(
        APIError(error.status_code, "REQUEST_REJECTED", "请求无效或接口不存在")
    )


@app.exception_handler(Exception)
async def internal_error(request, error):
    # Never log exception repr: DB parameters and validation inputs can contain secrets.
    return error_response(APIError(500, "INTERNAL_ERROR", "服务发生异常，请稍后重试"))


app.include_router(sharing_router)
app.include_router(agent_runs_router)
app.include_router(auth_router)
app.include_router(todo_router)
app.include_router(assistant_router)
app.include_router(assistant_preferences_router)
app.include_router(platform_router)
app.include_router(calendar_events_router)
app.include_router(planning_router)
app.include_router(planning_review_router)
app.include_router(households_router)
app.include_router(household_objects_router)
app.include_router(contacts_router)
app.include_router(notifications_router)
app.include_router(documents_router)
app.include_router(document_review_router)
app.include_router(document_intelligence_router)
app.include_router(life_router)
app.include_router(life_edits_router)
app.include_router(life_shopping_router)
app.include_router(appointments_router)
app.include_router(collaboration_router)
app.include_router(hub_router)
app.include_router(mail_router)
app.include_router(voice_memos_router)
app.include_router(parity_router)
app.include_router(parity_email_router)


from fastapi.openapi.utils import get_openapi


def documented_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
    schema["components"].setdefault("securitySchemes", {})["SessionCookie"] = {
        "type": "apiKey",
        "in": "cookie",
        "name": "session",
        "description": "固定7天的HttpOnly服务端会话",
    }
    for path, methods in schema["paths"].items():
        if not path.startswith("/api"):
            continue
        for method, operation in methods.items():
            if (
                path.startswith(
                    (
                        "/api/todos",
                        "/api/assistant",
                        "/api/agent",
                        "/api/platform",
                        "/api/calendar",
                        "/api/planning",
                        "/api/households",
                        "/api/contacts",
                        "/api/contact-groups",
                        "/api/notifications",
                        "/api/documents",
                        "/api/life",
                        "/api/hub",
                        "/api/collaboration",
                        "/api/sharing",
                        "/api/mail",
                    )
                )
                or path == "/api/auth/me"
            ):
                operation["security"] = [{"SessionCookie": []}]
            if method in ("post", "patch", "put", "delete"):
                operation.setdefault("parameters", []).extend(
                    [
                        {
                            "name": "Origin",
                            "in": "header",
                            "required": True,
                            "schema": {"type": "string"},
                            "description": "环境精确允许的同源地址",
                        },
                        {
                            "name": "X-App-Request",
                            "in": "header",
                            "required": True,
                            "schema": {"type": "string", "enum": ["1"]},
                        },
                    ]
                )
    app.openapi_schema = schema
    return schema


app.openapi = documented_openapi
