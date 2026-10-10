import hmac
import hashlib
import io
import logging
import urllib.parse
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, Request, Response, Form, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func, desc
from sqlalchemy.orm import selectinload
from aiogram import Bot

from app.config import settings
from app.database.session import async_session_factory
from app.database.models import User, Plan, Subscription, PaymentReceipt
from app.services.goguard import GoGuardClient
from app.services.payment import process_receipt_approval, process_receipt_rejection
from app.services.subscription import sync_subscription_details
from app.services.settings_service import (
    get_all_settings,
    update_settings,
    get_web_credentials,
    is_default_password,
    set_web_password,
    get_admin_details,
    add_admin_id,
    remove_admin_id,
)
from app.bot.utils.formatters import format_price, format_timestamp, bytes_to_human

from pathlib import Path

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Register custom Jinja filters
templates.env.filters["format_price"] = lambda v: format_price(int(v or 0), settings.CURRENCY_TITLE)
templates.env.filters["format_timestamp"] = lambda v: format_timestamp(int(v or 0)) if v else "-"
templates.env.filters["bytes_to_human"] = lambda v: bytes_to_human(int(v or 0)) if v else "-"


def create_session_token(username: str) -> str:
    """Create a tamper-proof signed session cookie."""
    signature = hmac.new(
        settings.WEB_SECRET_KEY.encode(),
        username.encode(),
        hashlib.sha256
    ).hexdigest()
    return f"{username}:{signature}"


def verify_session_token(token: Optional[str]) -> Optional[str]:
    """Verify session cookie signature."""
    if not token or ":" not in token:
        return None
    username, sig = token.split(":", 1)
    expected = hmac.new(
        settings.WEB_SECRET_KEY.encode(),
        username.encode(),
        hashlib.sha256
    ).hexdigest()
    if hmac.compare_digest(sig, expected):
        return username
    return None


async def require_auth(request: Request) -> str:
    """FastAPI dependency for admin authentication."""
    token = request.cookies.get("admin_session")
    username = verify_session_token(token)
    if not username:
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": "/login"}
        )

    # Force password change if currently default 'admin'
    path = request.url.path
    if path not in ("/change-password", "/logout"):
        async with async_session_factory() as session:
            if await is_default_password(session):
                raise HTTPException(
                    status_code=status.HTTP_307_TEMPORARY_REDIRECT,
                    headers={"Location": "/change-password?required=1"}
                )

    return username


def create_web_app(bot: Bot, goguard: GoGuardClient) -> FastAPI:
    """FastAPI application factory."""
    app = FastAPI(title="GoGuard Bot Management Panel", docs_url=None, redoc_url=None)
    app.state.bot = bot
    app.state.goguard = goguard

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        if exc.status_code == status.HTTP_307_TEMPORARY_REDIRECT:
            return RedirectResponse(url=exc.headers.get("Location", "/login"))
        return HTMLResponse(content=str(exc.detail), status_code=exc.status_code)

    # =========================================================================
    # Auth Routes
    # =========================================================================

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request):
        token = request.cookies.get("admin_session")
        if verify_session_token(token):
            return RedirectResponse(url="/", status_code=303)
        return templates.TemplateResponse(request=request, name="login.html", context={"error": None})

    @app.post("/login", response_class=HTMLResponse)
    async def login_submit(
        request: Request,
        response: Response,
        username: str = Form(...),
        password: str = Form(...),
    ):
        async with async_session_factory() as session:
            valid_user, valid_pass = await get_web_credentials(session)

        if username == valid_user and password == valid_pass:
            token = create_session_token(username)
            # If password is still default 'admin', redirect to change password
            target_url = "/change-password?required=1" if password == "admin" else "/"
            resp = RedirectResponse(url=target_url, status_code=303)
            resp.set_cookie(
                key="admin_session",
                value=token,
                httponly=True,
                max_age=86400 * 7,
                samesite="lax",
            )
            return resp

        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": "نام کاربری یا رمز عبور اشتباه است."},
            status_code=401,
        )

    @app.get("/logout")
    async def logout():
        resp = RedirectResponse(url="/login", status_code=303)
        resp.delete_cookie("admin_session")
        return resp

    # =========================================================================
    # Password Change Routes (Security Enforcement)
    # =========================================================================

    @app.get("/change-password", response_class=HTMLResponse)
    async def change_password_page(
        request: Request,
        required: Optional[int] = None,
        msg: str = "",
        user: str = Depends(require_auth),
    ):
        async with async_session_factory() as session:
            is_def = await is_default_password(session)

        return templates.TemplateResponse(
            request=request,
            name="change_password.html",
            context={
                "active_page": "change_password",
                "current_user": user,
                "required": bool(required) or is_def,
                "error": None,
                "message": msg,
            },
        )

    @app.post("/change-password", response_class=HTMLResponse)
    async def change_password_submit(
        request: Request,
        current_password: str = Form(...),
        new_password: str = Form(...),
        confirm_password: str = Form(...),
        user: str = Depends(require_auth),
    ):
        async with async_session_factory() as session:
            valid_user, valid_pass = await get_web_credentials(session)
            is_def = await is_default_password(session)

            error = None
            if current_password != valid_pass:
                error = "رمز عبور فعلی نادرست است."
            elif new_password.strip() == "admin":
                error = "رمز عبور جدید نمی‌تواند کلمه پیش‌فرض (admin) باشد."
            elif len(new_password.strip()) < 5:
                error = "رمز عبور جدید باید حداقل ۵ کاراکتر باشد."
            elif new_password != confirm_password:
                error = "رمز عبور جدید با تکرار آن مطابقت ندارد."

            if error:
                return templates.TemplateResponse(
                    request=request,
                    name="change_password.html",
                    context={
                        "active_page": "change_password",
                        "current_user": user,
                        "required": is_def,
                        "error": error,
                        "message": "",
                    },
                    status_code=400,
                )

            await set_web_password(session, new_password.strip())

        return RedirectResponse(
            url="/dashboard?msg=رمز عبور با موفقیت به‌روزرسانی شد و امنیت پنل ارتقا یافت.",
            status_code=303,
        )

    # =========================================================================
    # Dashboard Route
    # =========================================================================

    @app.get("/", response_class=HTMLResponse)
    @app.get("/dashboard", response_class=HTMLResponse)
    async def dashboard(request: Request, msg: str = "", user: str = Depends(require_auth)):
        async with async_session_factory() as session:
            total_users = (await session.execute(select(func.count(User.id)))).scalar() or 0
            active_subs = (await session.execute(
                select(func.count(Subscription.id)).where(Subscription.status == "active")
            )).scalar() or 0
            total_sales = (await session.execute(
                select(func.sum(PaymentReceipt.amount)).where(PaymentReceipt.status == "approved")
            )).scalar() or 0
            pending_receipts = (await session.execute(
                select(func.count(PaymentReceipt.id)).where(PaymentReceipt.status == "pending")
            )).scalar() or 0

            # Pending receipts preview on dashboard
            rec_stmt = (
                select(PaymentReceipt)
                .options(selectinload(PaymentReceipt.user), selectinload(PaymentReceipt.plan))
                .where(PaymentReceipt.status == "pending")
                .order_by(desc(PaymentReceipt.id))
                .limit(5)
            )
            rec_res = await session.execute(rec_stmt)
            recent_receipts = rec_res.scalars().all()

        # Test GoGuard Panel
        goguard_ok = await app.state.goguard.health_check()

        return templates.TemplateResponse(
            request=request,
            name="dashboard.html",
            context={
                "active_page": "dashboard",
                "current_user": user,
                "total_users": total_users,
                "active_subs": active_subs,
                "total_sales": total_sales,
                "pending_receipts": pending_receipts,
                "recent_receipts": recent_receipts,
                "goguard_ok": goguard_ok,
                "goguard_url": settings.GOGUARD_BASE_URL,
                "goguard_user": settings.GOGUARD_USERNAME,
                "message": msg,
            },
        )

    # =========================================================================
    # Settings Management (Dynamic Runtime Config)
    # =========================================================================

    @app.get("/settings", response_class=HTMLResponse)
    async def settings_page(request: Request, user: str = Depends(require_auth), msg: str = ""):
        async with async_session_factory() as session:
            all_sets = await get_all_settings(session)

        return templates.TemplateResponse(
            request=request,
            name="settings.html",
            context={
                "active_page": "settings",
                "current_user": user,
                "settings": all_sets,
                "message": msg,
            },
        )

    @app.post("/settings")
    async def save_settings(request: Request, user: str = Depends(require_auth)):
        form_data = await request.form()
        updates = {k: v for k, v in form_data.items()}

        async with async_session_factory() as session:
            await update_settings(session, updates)

        return RedirectResponse(url="/settings?msg=تنظیمات با موفقیت ذخیره و اعمال شد.", status_code=303)

    # =========================================================================
    # Plans Management
    # =========================================================================

    @app.get("/plans", response_class=HTMLResponse)
    async def plans_page(request: Request, user: str = Depends(require_auth), msg: str = ""):
        async with async_session_factory() as session:
            plans_res = await session.execute(select(Plan).order_by(Plan.price.asc()))
            plans = plans_res.scalars().all()

        return templates.TemplateResponse(
            request=request,
            name="plans.html",
            context={
                "active_page": "plans",
                "current_user": user,
                "plans": plans,
                "message": msg,
            },
        )

    @app.post("/plans")
    async def add_plan(
        title: str = Form(...),
        traffic_gb: float = Form(...),
        duration_days: int = Form(...),
        price: int = Form(...),
        user: str = Depends(require_auth),
    ):
        async with async_session_factory() as session:
            plan = Plan(
                title=title.strip(),
                traffic_gb=traffic_gb,
                duration_days=duration_days,
                price=price,
                is_active=True,
            )
            session.add(plan)
            await session.commit()

        return RedirectResponse(url="/plans?msg=پلن جدید با موفقیت اضافه شد.", status_code=303)

    @app.post("/plans/{plan_id}/toggle")
    async def toggle_plan(plan_id: int, user: str = Depends(require_auth)):
        async with async_session_factory() as session:
            plan = (await session.execute(select(Plan).where(Plan.id == plan_id))).scalar_one_or_none()
            if plan:
                plan.is_active = not plan.is_active
                await session.commit()

        return RedirectResponse(url="/plans", status_code=303)

    @app.post("/plans/{plan_id}/delete")
    async def delete_plan(plan_id: int, user: str = Depends(require_auth)):
        async with async_session_factory() as session:
            plan = (await session.execute(select(Plan).where(Plan.id == plan_id))).scalar_one_or_none()
            if plan:
                await session.delete(plan)
                await session.commit()

        return RedirectResponse(url="/plans?msg=پلن حذف شد.", status_code=303)

    # =========================================================================
    # Receipts Management
    # =========================================================================

    @app.get("/receipts", response_class=HTMLResponse)
    async def receipts_page(
        request: Request,
        status: Optional[str] = None,
        msg: str = "",
        user: str = Depends(require_auth),
    ):
        async with async_session_factory() as session:
            query = (
                select(PaymentReceipt)
                .options(selectinload(PaymentReceipt.user), selectinload(PaymentReceipt.plan))
                .order_by(desc(PaymentReceipt.id))
            )
            if status:
                query = query.where(PaymentReceipt.status == status)

            receipts = (await session.execute(query)).scalars().all()

            # Counts for tabs
            all_count = (await session.execute(select(func.count(PaymentReceipt.id)))).scalar() or 0
            pending_count = (await session.execute(
                select(func.count(PaymentReceipt.id)).where(PaymentReceipt.status == "pending")
            )).scalar() or 0
            approved_count = (await session.execute(
                select(func.count(PaymentReceipt.id)).where(PaymentReceipt.status == "approved")
            )).scalar() or 0
            rejected_count = (await session.execute(
                select(func.count(PaymentReceipt.id)).where(PaymentReceipt.status == "rejected")
            )).scalar() or 0

        return templates.TemplateResponse(
            request=request,
            name="receipts.html",
            context={
                "active_page": "receipts",
                "current_user": user,
                "receipts": receipts,
                "status_filter": status,
                "all_count": all_count,
                "pending_count": pending_count,
                "approved_count": approved_count,
                "rejected_count": rejected_count,
                "message": msg,
            },
        )

    @app.post("/receipts/{rec_id}/approve")
    async def approve_receipt(rec_id: int, user: str = Depends(require_auth)):
        async with async_session_factory() as session:
            ok, msg = await process_receipt_approval(
                bot=app.state.bot,
                session=session,
                goguard=app.state.goguard,
                receipt_id=rec_id,
            )

        return RedirectResponse(url=f"/receipts?msg={msg}", status_code=303)

    @app.post("/receipts/{rec_id}/reject")
    async def reject_receipt(
        rec_id: int,
        reason: str = Form("تصویر فیش نامعتبر است"),
        user: str = Depends(require_auth),
    ):
        async with async_session_factory() as session:
            ok, msg = await process_receipt_rejection(
                bot=app.state.bot,
                session=session,
                receipt_id=rec_id,
                reason=reason,
            )

        return RedirectResponse(url=f"/receipts?msg={msg}", status_code=303)

    @app.get("/receipts/{rec_id}/photo")
    async def view_receipt_photo(rec_id: int, user: str = Depends(require_auth)):
        async with async_session_factory() as session:
            rec = (await session.execute(
                select(PaymentReceipt).where(PaymentReceipt.id == rec_id)
            )).scalar_one_or_none()
            if not rec or not rec.photo_file_id:
                raise HTTPException(status_code=404, detail="رسید یافت نشد.")

        # Stream photo from Telegram Bot API
        try:
            file_info = await app.state.bot.get_file(rec.photo_file_id)
            stream = io.BytesIO()
            await app.state.bot.download_file(file_info.file_path, destination=stream)
            stream.seek(0)
            return StreamingResponse(stream, media_type="image/jpeg")
        except Exception as exc:
            logger.error(f"Error fetching photo for receipt #{rec_id}: {exc}")
            raise HTTPException(status_code=500, detail="خطا در دریافت تصویر از سرور تلگرام")

    # =========================================================================
    # Users Management
    # =========================================================================

    @app.get("/users", response_class=HTMLResponse)
    async def users_page(
        request: Request,
        q: Optional[str] = None,
        msg: str = "",
        user: str = Depends(require_auth),
    ):
        async with async_session_factory() as session:
            stmt = select(User).order_by(desc(User.created_at))
            if q:
                if q.isdigit():
                    stmt = stmt.where(User.id == int(q))
                else:
                    clean_q = q.lstrip("@").strip()
                    stmt = stmt.where(User.username.ilike(f"%{clean_q}%"))

            users = (await session.execute(stmt)).scalars().all()

        return templates.TemplateResponse(
            request=request,
            name="users.html",
            context={
                "active_page": "users",
                "current_user": user,
                "users": users,
                "query": q,
                "message": msg,
            },
        )

    @app.post("/users/{user_id}/balance")
    async def update_user_balance(
        user_id: int,
        amount: int = Form(...),
        user: str = Depends(require_auth),
    ):
        async with async_session_factory() as session:
            db_user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
            if db_user:
                db_user.balance += amount
                if db_user.balance < 0:
                    db_user.balance = 0
                await session.commit()

        return RedirectResponse(url="/users?msg=موجودی کاربر تغییر یافت.", status_code=303)

    @app.post("/users/{user_id}/toggle_ban")
    async def toggle_user_ban(user_id: int, user: str = Depends(require_auth)):
        async with async_session_factory() as session:
            db_user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
            if db_user:
                db_user.is_banned = not db_user.is_banned
                await session.commit()

        return RedirectResponse(url="/users?msg=وضعیت مسدودی کاربر تغییر کرد.", status_code=303)

    # =========================================================================
    # Admins Management
    # =========================================================================

    @app.get("/admins", response_class=HTMLResponse)
    async def admins_page(
        request: Request,
        msg: str = "",
        user: str = Depends(require_auth),
    ):
        async with async_session_factory() as session:
            admins = await get_admin_details(session)

        return templates.TemplateResponse(
            request=request,
            name="admins.html",
            context={
                "active_page": "admins",
                "current_user": user,
                "admins": admins,
                "message": msg,
            },
        )

    @app.post("/admins/add")
    async def add_admin_route(
        admin_id: str = Form(...),
        user: str = Depends(require_auth),
    ):
        async with async_session_factory() as session:
            success, msg = await add_admin_id(session, admin_id)

        encoded_msg = urllib.parse.quote(msg)
        return RedirectResponse(url=f"/admins?msg={encoded_msg}", status_code=303)

    @app.post("/admins/{admin_id}/delete")
    async def delete_admin_route(
        admin_id: int,
        user: str = Depends(require_auth),
    ):
        async with async_session_factory() as session:
            success, msg = await remove_admin_id(session, admin_id)

        encoded_msg = urllib.parse.quote(msg)
        return RedirectResponse(url=f"/admins?msg={encoded_msg}", status_code=303)


    # =========================================================================
    # Subscriptions Management
    # =========================================================================

    @app.get("/subscriptions", response_class=HTMLResponse)
    async def subscriptions_page(
        request: Request,
        msg: str = "",
        user: str = Depends(require_auth),
    ):
        async with async_session_factory() as session:
            subs = (await session.execute(
                select(Subscription)
                .options(selectinload(Subscription.user), selectinload(Subscription.plan))
                .order_by(desc(Subscription.id))
            )).scalars().all()

        return templates.TemplateResponse(
            request=request,
            name="subscriptions.html",
            context={
                "active_page": "subscriptions",
                "current_user": user,
                "subscriptions": subs,
                "message": msg,
            },
        )

    @app.post("/subscriptions/{sub_id}/sync")
    async def sync_subscription(sub_id: int, user: str = Depends(require_auth)):
        async with async_session_factory() as session:
            sub = (await session.execute(
                select(Subscription).where(Subscription.id == sub_id)
            )).scalar_one_or_none()
            if sub:
                await sync_subscription_details(session, app.state.goguard, sub)

        return RedirectResponse(url="/subscriptions?msg=همگام‌سازی با پنل انجام شد.", status_code=303)

    @app.post("/subscriptions/{sub_id}/delete")
    async def delete_subscription(sub_id: int, user: str = Depends(require_auth)):
        async with async_session_factory() as session:
            sub = (await session.execute(
                select(Subscription).where(Subscription.id == sub_id)
            )).scalar_one_or_none()
            if sub:
                try:
                    await app.state.goguard.delete_subscription(sub.goguard_username)
                except Exception as exc:
                    logger.warning(f"Could not delete on panel: {exc}")
                await session.delete(sub)
                await session.commit()

        return RedirectResponse(url="/subscriptions?msg=اشتراک حذف شد.", status_code=303)

    return app
