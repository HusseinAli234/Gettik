from pathlib import Path

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from .database import engine, get_session
from .models import Base, Trip
from .pricing import DIRECTION_BASE_PRICE, calculate_price

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Gettik MVP")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@app.on_event("startup")
async def startup_event() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@app.get("/", response_class=HTMLResponse)
async def create_trip_page(request: Request) -> HTMLResponse:
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
        context={
            "directions": DIRECTION_BASE_PRICE,
            "breakdown": breakdown,
            "form": {
                "direction": "city",
                "people_count": 5,
                "transport": False,
                "food": False,
                "activities": False,
            },
        },
    )


@app.post("/price-preview", response_class=HTMLResponse)
async def price_preview(
    request: Request,
    direction: str = Form(...),
    people_count: int = Form(...),
    transport: bool = Form(False),
    food: bool = Form(False),
    activities: bool = Form(False),
) -> HTMLResponse:
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
        context={"breakdown": breakdown},
    )


@app.post("/trips", response_class=HTMLResponse)
async def create_trip(
    direction: str = Form(...),
    people_count: int = Form(...),
    transport: bool = Form(False),
    food: bool = Form(False),
    activities: bool = Form(False),
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    breakdown = calculate_price(
        direction=direction,
        people_count=people_count,
        transport=transport,
        food=food,
        activities=activities,
    )

    trip = Trip(
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
) -> HTMLResponse:
    trip = await session.get(Trip, trip_id)
    if trip is None:
        return HTMLResponse("Trip not found", status_code=404)

    share_url = str(request.url)
    return templates.TemplateResponse(
        request=request,
        name="trip_detail.html",
        context={"trip": trip, "share_url": share_url},
    )
