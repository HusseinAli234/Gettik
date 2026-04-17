import hashlib
import hmac
import os
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
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


@app.on_event("startup")
async def startup_event() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@app.get("/", response_class=HTMLResponse)
async def create_trip_page(request: Request, session: AsyncSession = Depends(get_session)) -> HTMLResponse:
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
                "transport": False,
                "food": False,
                "activities": False,
            },
        ),
    )


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="register.html", context=template_context(request, error=None))


@app.post("/register", response_class=HTMLResponse)
async def register(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse | RedirectResponse:
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


@app.post("/login", response_class=HTMLResponse)
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse | RedirectResponse:
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


@app.get("/cabinet", response_class=HTMLResponse)
async def cabinet(request: Request, session: AsyncSession = Depends(get_session)) -> HTMLResponse | RedirectResponse:
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


@app.post("/price-preview", response_class=HTMLResponse)
async def price_preview(
    request: Request,
    direction: str = Form(...),
    people_count: int = Form(...),
    transport: bool = Form(False),
    food: bool = Form(False),
    activities: bool = Form(False),
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse | RedirectResponse:
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


@app.post("/trips", response_class=HTMLResponse)
async def create_trip(
    request: Request,
    direction: str = Form(...),
    people_count: int = Form(...),
    transport: bool = Form(False),
    food: bool = Form(False),
    activities: bool = Form(False),
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

    trip = Trip(
        user_id=user.id,
        direction=direction,
        people_count=people_count,
        transport=transport,
        food=food,
        activities=activities,
        total_price=breakdown.total,
    )
    session.add(trip)
    await session.commit()
    await session.refresh(trip)

    return RedirectResponse(url=f"/trips/{trip.id}", status_code=303)


@app.get("/trips/{trip_id}", response_class=HTMLResponse)
async def trip_details(
    trip_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse | RedirectResponse:
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
