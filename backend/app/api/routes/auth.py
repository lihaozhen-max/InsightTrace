import html
import secrets
import time
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.api.dependencies import CurrentUser, DatabaseSession
from app.core.config import get_settings
from app.core.errors import AppError
from app.models.enums import UserRole
from app.schemas.auth import CurrentUserResponse, LogoutResponse
from app.services.auth import resolve_mock_user

router = APIRouter(tags=["auth"])

AUTH_SESSION_KEY = "pending_auth"


def _validate_pending_auth(request: Request, state: str) -> dict[str, object]:
    settings = get_settings()
    pending = request.session.get(AUTH_SESSION_KEY)
    if not isinstance(pending, dict) or pending.get("state") != state:
        raise AppError(
            code="AUTH_STATE_INVALID",
            message="登录请求无效，请重新发起登录",
            status_code=400,
        )

    started_at = pending.get("started_at")
    if not isinstance(started_at, int | float):
        raise AppError(
            code="AUTH_FLOW_EXPIRED",
            message="登录请求已经失效，请重新发起登录",
            status_code=400,
        )

    if time.time() - started_at > settings.mock_auth_code_ttl_seconds:
        request.session.pop(AUTH_SESSION_KEY, None)
        raise AppError(
            code="AUTH_FLOW_EXPIRED",
            message="登录请求已经过期，请重新发起登录",
            status_code=400,
        )

    return pending


@router.get("/auth/login")
async def login(request: Request) -> RedirectResponse:
    state = secrets.token_urlsafe(32)
    request.session[AUTH_SESSION_KEY] = {
        "state": state,
        "started_at": time.time(),
    }
    return RedirectResponse(
        url=f"/auth/mock/authorize?state={quote(state)}",
        status_code=303,
    )


@router.get("/auth/mock/authorize", response_class=HTMLResponse)
async def mock_authorize_page(
    request: Request,
    state: Annotated[str, Query(min_length=20)],
) -> HTMLResponse:
    _validate_pending_auth(request, state)
    safe_state = html.escape(state, quote=True)
    return HTMLResponse(
        content=f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>InsightTrace 演示授权</title>
  <style>
    :root {{ color-scheme: dark; font-family: Inter, 'Microsoft YaHei', sans-serif; }}
    body {{ margin: 0; min-height: 100vh; display: grid; place-items: center;
      color: #e8eef7; background: #07111f; }}
    main {{ width: min(620px, calc(100% - 32px)); padding: 38px; border-radius: 22px;
      border: 1px solid rgba(148,163,184,.2); background: rgba(15,28,46,.9); }}
    p {{ color: #9fb0c6; line-height: 1.7; }}
    .roles {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 28px; }}
    button {{ width: 100%; padding: 18px; border: 1px solid rgba(94,234,212,.45);
      border-radius: 14px; color: #e8eef7; background: rgba(15,118,110,.16);
      cursor: pointer; font: inherit; text-align: left; }}
    button strong {{ display: block; margin-bottom: 6px; color: #5eead4; }}
    button span {{ color: #9fb0c6; font-size: 13px; }}
    @media (max-width: 560px) {{ .roles {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <main>
    <p>INSIGHTTRACE · MOCK OAUTH</p>
    <h1>选择演示身份</h1>
    <p>此页面模拟企业认证中心。MVP 后续可以在不改变业务接口的情况下替换为真实 OAuth/OIDC 服务。</p>
    <div class="roles">
      <form method="post" action="/auth/mock/authorize">
        <input type="hidden" name="state" value="{safe_state}">
        <input type="hidden" name="role" value="analyst">
        <button type="submit"><strong>分析用户</strong><span>创建会话并执行经营分析</span></button>
      </form>
      <form method="post" action="/auth/mock/authorize">
        <input type="hidden" name="state" value="{safe_state}">
        <input type="hidden" name="role" value="admin">
        <button type="submit">
          <strong>系统管理员</strong><span>额外查看配置和运行日志</span>
        </button>
      </form>
    </div>
  </main>
</body>
</html>"""
    )


@router.post("/auth/mock/authorize")
async def mock_authorize(
    request: Request,
    state: Annotated[str, Form(min_length=20)],
    role: Annotated[UserRole, Form()],
) -> RedirectResponse:
    pending = _validate_pending_auth(request, state)
    code = secrets.token_urlsafe(32)
    pending["code"] = code
    pending["role"] = role.value
    pending["code_issued_at"] = time.time()
    request.session[AUTH_SESSION_KEY] = pending

    return RedirectResponse(
        url=f"/auth/callback?code={quote(code)}&state={quote(state)}",
        status_code=303,
    )


@router.get("/auth/callback")
async def callback(
    request: Request,
    session: DatabaseSession,
    code: Annotated[str, Query(min_length=20)],
    state: Annotated[str, Query(min_length=20)],
) -> RedirectResponse:
    settings = get_settings()
    pending = _validate_pending_auth(request, state)
    issued_at = pending.get("code_issued_at")

    if pending.get("code") != code or not isinstance(issued_at, int | float):
        raise AppError(
            code="AUTH_CODE_INVALID",
            message="授权码无效，请重新发起登录",
            status_code=400,
        )

    if time.time() - issued_at > settings.mock_auth_code_ttl_seconds:
        request.session.pop(AUTH_SESSION_KEY, None)
        raise AppError(
            code="AUTH_CODE_EXPIRED",
            message="授权码已经过期，请重新发起登录",
            status_code=400,
        )

    try:
        role = UserRole(str(pending["role"]))
    except (KeyError, ValueError) as error:
        raise AppError(
            code="AUTH_ROLE_INVALID",
            message="授权身份无效，请重新发起登录",
            status_code=400,
        ) from error

    user = await resolve_mock_user(session, role)
    request.session.clear()
    request.session["user_id"] = str(user.id)

    return RedirectResponse(url=settings.frontend_url, status_code=303)


@router.post("/auth/logout", response_model=LogoutResponse)
async def logout(request: Request) -> LogoutResponse:
    request.session.clear()
    return LogoutResponse()


@router.get("/api/me", response_model=CurrentUserResponse)
async def current_user(user: CurrentUser) -> CurrentUserResponse:
    return CurrentUserResponse.model_validate(user)
