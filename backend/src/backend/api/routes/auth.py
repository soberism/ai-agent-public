from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import APIRouter, Request, Response
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from backend.api.schemas import (
    ERROR_RESPONSES,
    EmailInput,
    Login,
    PasswordChange,
    Register,
    UserOut,
    VerificationSent,
)
from backend.core.security import (
    DB,
    APIError,
    Principal,
    Store,
    dummy_hash,
    establish_session,
    password_hasher,
    rate_limit,
    session_key,
    settings,
    unavailable,
)
from backend.db.models import User
from backend.db.parity_models import EmailPreference
from backend.features.auth.verification import consume_code, request_code

router = APIRouter(prefix="/api/auth", tags=["账号"], responses=ERROR_RESPONSES)


@router.post("/register/code", response_model=VerificationSent)
def send_registration_code(body: EmailInput, request: Request, store: Store):
    request_code(store, request, body.email)
    return VerificationSent()


@router.post("/register", response_model=UserOut, status_code=201)
def register(
    body: Register, request: Request, response: Response, session: DB, store: Store
):
    rate_limit(store, request)
    consume_code(store, body.email, body.verification_code)
    try:
        user = session.scalar(
            select(User).where(User.email == body.email).with_for_update()
        )
        if user and user.active:
            raise APIError(
                409, "ACCOUNT_CONFLICT", "无法创建账号，请尝试登录或更换邮箱"
            )
        if user:
            user.active = True
            user.password_hash = password_hasher.hash(body.password)
        else:
            user = User(
                email=body.email, password_hash=password_hasher.hash(body.password)
            )
            session.add(user)
            session.flush()
            session.add(EmailPreference(owner_id=user.id))
        session.commit()
    except IntegrityError:
        session.rollback()
        raise APIError(
            409, "ACCOUNT_CONFLICT", "无法创建账号，请尝试登录或更换邮箱"
        ) from None
    except SQLAlchemyError:
        session.rollback()
        raise APIError(
            503,
            "REGISTRATION_FAILED",
            "注册未完成，请先尝试登录核对；如账号未创建，请重新获取验证码",
        ) from None
    try:
        establish_session(store, user, request, response)
    except RedisError:
        raise APIError(
            503, "ACCOUNT_CREATED_LOGIN_REQUIRED", "账号已创建，请重新登录"
        ) from None
    return user


@router.post("/login", response_model=UserOut)
def login(body: Login, request: Request, response: Response, session: DB, store: Store):
    rate_limit(store, request, body.email)
    user = session.scalar(select(User).where(User.email == body.email))
    try:
        matched = password_hasher.verify(
            user.password_hash if user and user.active else dummy_hash, body.password
        )
    except VerificationError, InvalidHashError:
        matched = False
    if not user or not user.active or not matched:
        raise APIError(401, "INVALID_CREDENTIALS", "邮箱或密码不正确")
    establish_session(store, user, request, response)
    return user


@router.get("/me", response_model=UserOut)
def me(user: Principal):
    return user


@router.post("/password", status_code=204)
def change_password(
    body: PasswordChange, request: Request, user: Principal, session: DB, store: Store
):
    rate_limit(store, request, user.email)
    try:
        account = session.scalar(
            select(User)
            .where(User.id == user.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if not account or not account.active:
            raise APIError(401, "SESSION_EXPIRED", "登录已失效，请重新登录")
        try:
            matched = password_hasher.verify(
                account.password_hash, body.current_password
            )
        except VerificationError, InvalidHashError:
            matched = False
        if not matched:
            raise APIError(400, "INVALID_PASSWORD", "原密码不正确")
        account.password_hash = password_hasher.hash(body.new_password)
        account.auth_version += 1
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        raise unavailable("修改密码失败，请重试") from None


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, store: Store):
    try:
        # Ping even without a Cookie: success must confirm dependency availability.
        store.delete(session_key(request.cookies.get("session", "")))
    except RedisError:
        raise unavailable("退出失败，请重试") from None
    response.delete_cookie(
        "session",
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )


@router.delete("/account", status_code=204)
def deactivate_account(user: Principal, session: DB, response: Response):
    try:
        account = session.scalar(
            select(User)
            .where(User.id == user.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if not account.active:
            raise APIError(401, "SESSION_EXPIRED", "登录已失效，请重新登录")
        account.active = False
        account.auth_version += 1
        account.password_hash = dummy_hash
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        raise unavailable("注销失败，请重试") from None
    response.delete_cookie(
        "session",
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )
