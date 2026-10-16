"""Ứng dụng demo "Kho hàng mini" để chạy bộ test mẫu của OmniTest.

Tài khoản demo cố định (không phải bí mật thật): demo / Demo@123.
Dữ liệu lưu trong bộ nhớ, mất khi khởi động lại. POST /api/reset đưa về trạng thái ban đầu.
"""

import asyncio
import html
import re
import secrets
from itertools import count
from typing import Annotated, Any

from fastapi import Cookie, FastAPI, Form, Header, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field

DEMO_USER = "demo"
DEMO_PASSWORD = "Demo@123"  # noqa: S105 - tài khoản demo công khai

app = FastAPI(title="OmniTest Demo Target", docs_url="/api/docs")

_items: dict[int, dict[str, Any]] = {}
_ids = count(1)
_tokens: set[str] = set()


def _seed() -> None:
    global _ids
    _items.clear()
    _tokens.clear()
    _ids = count(1)
    for name, qty in (("Bút bi", 120), ("Sổ tay", 45)):
        i = next(_ids)
        _items[i] = {"id": i, "name": name, "quantity": qty}


_seed()

STYLE = """
body{font-family:system-ui,sans-serif;max-width:720px;margin:40px auto;padding:0 16px;color:#1f2937}
label{display:block;margin-top:12px;font-weight:600}input{padding:8px;width:100%;box-sizing:border-box}
button{margin-top:16px;padding:8px 16px;cursor:pointer}.error{color:#b91c1c}.ok{color:#047857}
table{width:100%;border-collapse:collapse;margin-top:16px}td,th{border-bottom:1px solid #e5e7eb;padding:8px;text-align:left}
"""


def page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(
        f"<!doctype html><html lang='vi'><head><meta charset='utf-8'><title>{html.escape(title)} | Kho hàng mini</title>"
        f"<style>{STYLE}</style></head><body><h1>{html.escape(title)}</h1>{body}</body></html>"
    )


def _logged_in(session: str | None) -> bool:
    return session is not None and session in _tokens


# ---------- Giao diện ----------


@app.get("/", include_in_schema=False)
def index() -> RedirectResponse:
    return RedirectResponse("/login", status_code=303)


@app.get("/login", response_class=HTMLResponse)
def login_form(error: str = "") -> HTMLResponse:
    err = f"<p class='error' role='alert'>{html.escape(error)}</p>" if error else ""
    return page(
        "Đăng nhập",
        f"""{err}<form method='post' action='/login'>
<label for='username'>Tên đăng nhập</label><input id='username' name='username' required>
<label for='password'>Mật khẩu</label><input id='password' name='password' type='password' required>
<button type='submit'>Đăng nhập</button></form>""",
    )


@app.post("/login")
def login_submit(
    username: Annotated[str, Form()] = "", password: Annotated[str, Form()] = ""
) -> Response:
    if username != DEMO_USER or password != DEMO_PASSWORD:
        return RedirectResponse(
            "/login?error=Sai+t%C3%AAn+%C4%91%C4%83ng+nh%E1%BA%ADp+ho%E1%BA%B7c+m%E1%BA%ADt+kh%E1%BA%A9u",
            status_code=303,
        )
    token = secrets.token_urlsafe(16)
    _tokens.add(token)
    resp = RedirectResponse("/items", status_code=303)
    resp.set_cookie("demo_session", token, httponly=True, samesite="lax")
    return resp


@app.get("/register", response_class=HTMLResponse)
def register_form() -> HTMLResponse:
    return _register_page({}, {})


def _register_page(
    values: dict[str, str], errors: dict[str, str], ok: bool = False
) -> HTMLResponse:
    def field(name: str, label: str, type_: str = "text") -> str:
        err = errors.get(name)
        e = f"<p class='error' id='{name}-error'>{html.escape(err)}</p>" if err else ""
        return (
            f"<label for='{name}'>{label}</label><input id='{name}' name='{name}' type='{type_}' "
            f"value='{html.escape(values.get(name, ''))}'>{e}"
        )

    msg = "<p class='ok' role='status'>Đăng ký thành công</p>" if ok else ""
    return page(
        "Đăng ký",
        f"""{msg}<form method='post' action='/register' novalidate>
{field("full_name", "Họ tên")}{field("email", "Email", "email")}{field("age", "Tuổi", "number")}
{field("password", "Mật khẩu", "password")}<button type='submit'>Đăng ký</button></form>""",
    )


@app.post("/register", response_class=HTMLResponse)
def register_submit(
    full_name: Annotated[str, Form()] = "",
    email: Annotated[str, Form()] = "",
    age: Annotated[str, Form()] = "",
    password: Annotated[str, Form()] = "",
) -> HTMLResponse:
    errors: dict[str, str] = {}
    if not full_name.strip():
        errors["full_name"] = "Vui lòng nhập họ tên"
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        errors["email"] = "Email không hợp lệ"
    if not age.isdigit() or not 18 <= int(age) <= 100:
        errors["age"] = "Tuổi phải từ 18 đến 100"
    if len(password) < 8:
        errors["password"] = "Mật khẩu tối thiểu 8 ký tự"  # noqa: S105
    values = {"full_name": full_name, "email": email, "age": age}
    return _register_page(values, errors, ok=not errors)


@app.get("/items", response_class=HTMLResponse, response_model=None)
def items_page(demo_session: Annotated[str | None, Cookie()] = None) -> Response:
    if not _logged_in(demo_session):
        return RedirectResponse("/login", status_code=303)
    rows = "".join(
        f"<tr data-testid='item-{i['id']}'><td>{html.escape(i['name'])}</td><td>{i['quantity']}</td>"
        f"<td><form method='post' action='/items/{i['id']}/delete'><button aria-label='Xóa {html.escape(i['name'])}'>Xóa</button></form></td></tr>"
        for i in _items.values()
    )
    return page(
        "Danh sách hàng",
        f"""<p>Xin chào {DEMO_USER}</p>
<form method='post' action='/items'><label for='name'>Tên hàng</label><input id='name' name='name'>
<label for='quantity'>Số lượng</label><input id='quantity' name='quantity' type='number' value='1'>
<button type='submit'>Thêm hàng</button></form>
<table><thead><tr><th>Tên</th><th>Số lượng</th><th></th></tr></thead><tbody>{rows}</tbody></table>""",
    )


@app.post("/items", include_in_schema=False)
def items_create(
    name: Annotated[str, Form()] = "",
    quantity: Annotated[int, Form()] = 1,
    demo_session: Annotated[str | None, Cookie()] = None,
) -> RedirectResponse:
    if _logged_in(demo_session) and name.strip():
        i = next(_ids)
        _items[i] = {"id": i, "name": name.strip(), "quantity": quantity}
    return RedirectResponse("/items", status_code=303)


@app.post("/items/{item_id}/delete", include_in_schema=False)
def items_delete(
    item_id: int, demo_session: Annotated[str | None, Cookie()] = None
) -> RedirectResponse:
    if _logged_in(demo_session):
        _items.pop(item_id, None)
    return RedirectResponse("/items", status_code=303)


# ---------- API JSON ----------


class LoginIn(BaseModel):
    username: str
    password: str


class ItemIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    quantity: int = Field(ge=0, le=1_000_000)


def _require_token(authorization: str | None) -> None:
    if (
        not authorization
        or not authorization.startswith("Bearer ")
        or authorization[7:] not in _tokens
    ):
        raise HTTPException(401, "Chưa xác thực")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/redirect")
def open_redirect(to: str) -> RedirectResponse:
    """Chuyển hướng tới URL bất kỳ: chỉ để kiểm tra OmniTest chặn chuyển hướng tới đích bị cấm."""
    return RedirectResponse(to, status_code=302)


@app.get("/api/slow")
async def slow(seconds: float = 1.0) -> dict[str, float]:
    """Phản hồi chậm (tối đa 10 giây) để thử timeout và hủy lần chạy."""
    seconds = max(0.0, min(seconds, 10.0))
    await asyncio.sleep(seconds)
    return {"waited": seconds}


@app.post("/api/login")
def api_login(body: LoginIn) -> dict[str, str]:
    if body.username != DEMO_USER or body.password != DEMO_PASSWORD:
        raise HTTPException(401, "Sai tên đăng nhập hoặc mật khẩu")
    token = secrets.token_urlsafe(16)
    _tokens.add(token)
    return {"token": token, "token_type": "bearer"}


@app.get("/api/items")
def api_items(authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    _require_token(authorization)
    return {"items": list(_items.values()), "total": len(_items)}


@app.post("/api/items", status_code=201)
def api_create(
    body: ItemIn, response: Response, authorization: Annotated[str | None, Header()] = None
) -> dict[str, Any]:
    _require_token(authorization)
    i = next(_ids)
    _items[i] = {"id": i, **body.model_dump()}
    response.headers["Location"] = f"/api/items/{i}"
    return _items[i]


@app.get("/api/items/{item_id}")
def api_get(item_id: int, authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    _require_token(authorization)
    if item_id not in _items:
        raise HTTPException(404, "Không tìm thấy")
    return _items[item_id]


@app.put("/api/items/{item_id}")
def api_update(
    item_id: int, body: ItemIn, authorization: Annotated[str | None, Header()] = None
) -> dict[str, Any]:
    _require_token(authorization)
    if item_id not in _items:
        raise HTTPException(404, "Không tìm thấy")
    _items[item_id].update(body.model_dump())
    return _items[item_id]


@app.delete("/api/items/{item_id}", status_code=204)
def api_delete(item_id: int, authorization: Annotated[str | None, Header()] = None) -> None:
    _require_token(authorization)
    if _items.pop(item_id, None) is None:
        raise HTTPException(404, "Không tìm thấy")


@app.post("/api/reset", status_code=204)
def api_reset(request: Request) -> None:
    _seed()
