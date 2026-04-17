import hashlib
import hmac
import json
import os
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.sessions import SessionMiddleware

from .database import engine, get_session
from .models import Base, Trip, User
from .pricing import DIRECTION_BASE_PRICE, calculate_price

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Gettik MVP")
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "gettik-dev-secret"))
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return f"{salt.hex()}:{digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt_hex, digest_hex = stored_hash.split(":", maxsplit=1)
    except ValueError:
        return False
    salt = bytes.fromhex(salt_hex)
    expected_digest = bytes.fromhex(digest_hex)
    actual_digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return hmac.compare_digest(actual_digest, expected_digest)


async def get_current_user(request: Request, session: AsyncSession) -> User | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return await session.get(User, user_id)


def template_context(request: Request, **kwargs: Any) -> dict[str, Any]:
    return {"request": request, **kwargs}


async def run_legacy_migrations() -> None:
    """Apply lightweight SQLite migrations for older local DBs."""
    async with engine.begin() as conn:
        table_info = await conn.execute(text("PRAGMA table_info(trips)"))
        columns = {row[1] for row in table_info.fetchall()}
        if "user_id" not in columns:
            await conn.execute(text("ALTER TABLE trips ADD COLUMN user_id INTEGER"))
        if "start_date" not in columns:
            await conn.execute(text("ALTER TABLE trips ADD COLUMN start_date DATE"))
            await conn.execute(text("UPDATE trips SET start_date = DATE(created_at) WHERE start_date IS NULL"))
        if "route_name" not in columns:
            await conn.execute(text("ALTER TABLE trips ADD COLUMN route_name VARCHAR(120)"))
        if "route_data" not in columns:
            await conn.execute(text("ALTER TABLE trips ADD COLUMN route_data TEXT"))


@app.on_event("startup")
async def startup_event() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await run_legacy_migrations()


@app.get("/", response_class=HTMLResponse, response_model=None)
async def create_trip_page(request: Request, session: AsyncSession = Depends(get_session)) -> Response:
    user = await get_current_user(request, session)
    if user is None:
        return RedirectResponse(url="/login", status_code=303)

    breakdown = calculate_price(
        direction="city",
        people_count=5,
        transport=False,
        food=False,
        activities=False,
    )
    return templates.TemplateResponse(
        request=request,
        name="create_trip.html",
        context=template_context(
            request,
            user=user,
            directions=DIRECTION_BASE_PRICE,
            breakdown=breakdown,
            form={
                "direction": "city",
                "people_count": 5,
                "start_date": date.today().isoformat(),
                "transport": False,
                "food": False,
                "activities": False,
                "route_name": "",
                "route_data": "",
            },
            mapbox_access_token=os.getenv("MAPBOX_ACCESS_TOKEN", ""),
        ),
    )


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="register.html", context=template_context(request, error=None))


@app.post("/register", response_class=HTMLResponse, response_model=None)
async def register(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    session: AsyncSession = Depends(get_session),
) -> Response:
    if len(password) < 6:
        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context=template_context(request, error="Пароль должен быть не короче 6 символов."),
            status_code=400,
        )

    existing_user = await session.scalar(select(User).where(User.email == email.lower().strip()))
    if existing_user:
        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context=template_context(request, error="Пользователь с таким email уже зарегистрирован."),
            status_code=400,
        )

    user = User(name=name.strip(), email=email.lower().strip(), password_hash=hash_password(password))
    session.add(user)
    await session.commit()
    await session.refresh(user)
    request.session["user_id"] = user.id
    return RedirectResponse(url="/cabinet", status_code=303)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="login.html", context=template_context(request, error=None))


@app.post("/login", response_class=HTMLResponse, response_model=None)
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    session: AsyncSession = Depends(get_session),
) -> Response:
    user = await session.scalar(select(User).where(User.email == email.lower().strip()))
    if user is None or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context=template_context(request, error="Неверный email или пароль."),
            status_code=400,
        )

    request.session["user_id"] = user.id
    return RedirectResponse(url="/cabinet", status_code=303)


@app.post("/logout")
async def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


@app.get("/cabinet", response_class=HTMLResponse, response_model=None)
async def cabinet(request: Request, session: AsyncSession = Depends(get_session)) -> Response:
    user = await get_current_user(request, session)
    if user is None:
        return RedirectResponse(url="/login", status_code=303)

    trips_result = await session.execute(
        select(Trip).where(Trip.user_id == user.id).order_by(Trip.created_at.desc(), Trip.id.desc())
    )
    trips = trips_result.scalars().all()
    return templates.TemplateResponse(
        request=request,
        name="cabinet.html",
        context=template_context(request, user=user, trips=trips),
    )


@app.post("/price-preview", response_class=HTMLResponse, response_model=None)
async def price_preview(
    request: Request,
    direction: str = Form(...),
    people_count: int = Form(...),
    transport: bool = Form(False),
    food: bool = Form(False),
    activities: bool = Form(False),
    session: AsyncSession = Depends(get_session),
) -> Response:
    user = await get_current_user(request, session)
    if user is None:
        return RedirectResponse(url="/login", status_code=303)

    breakdown = calculate_price(
        direction=direction,
        people_count=people_count,
        transport=transport,
        food=food,
        activities=activities,
    )
    return templates.TemplateResponse(
        request=request,
        name="_price_preview.html",
        context=template_context(request, breakdown=breakdown),
    )


@app.post("/trips", response_class=HTMLResponse, response_model=None)
async def create_trip(
    request: Request,
    direction: str = Form(...),
    people_count: int = Form(...),
    start_date: date = Form(...),
    transport: bool = Form(False),
    food: bool = Form(False),
    activities: bool = Form(False),
    route_name: str = Form(""),
    route_data: str = Form(""),
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    user = await get_current_user(request, session)
    if user is None:
        return RedirectResponse(url="/login", status_code=303)

    breakdown = calculate_price(
        direction=direction,
        people_count=people_count,
        transport=transport,
        food=food,
        activities=activities,
    )

    normalized_route_data: str | None = None
    normalized_route_name: str | None = route_name.strip() or None
    if route_data.strip():
        try:
            route_payload = json.loads(route_data)
            normalized_route_data = json.dumps(route_payload, ensure_ascii=False)
        except json.JSONDecodeError:
            normalized_route_name = None

    trip = Trip(
        user_id=user.id,
        direction=direction,
        people_count=people_count,
        start_date=start_date,
        transport=transport,
        food=food,
        activities=activities,
        route_name=normalized_route_name,
        route_data=normalized_route_data,
        total_price=breakdown.total,
    )
    session.add(trip)
    await session.commit()
    await session.refresh(trip)

    return RedirectResponse(url=f"/trips/{trip.id}", status_code=303)


@app.get("/trips/{trip_id}", response_class=HTMLResponse, response_model=None)
async def trip_details(
    trip_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Response:
    user = await get_current_user(request, session)
    if user is None:
        return RedirectResponse(url="/login", status_code=303)

    trip = await session.get(Trip, trip_id)
    if trip is None or trip.user_id != user.id:
        return HTMLResponse("Поездка не найдена", status_code=404)

    share_url = str(request.url)
    return templates.TemplateResponse(
        request=request,
        name="trip_detail.html",
        context=template_context(request, user=user, trip=trip, share_url=share_url),
    )
