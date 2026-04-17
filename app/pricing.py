from dataclasses import dataclass


DIRECTION_BASE_PRICE = {
    "mountains": 120,
    "beach": 150,
    "city": 100,
}

TRANSPORT_PER_PERSON = 45
FOOD_PER_PERSON = 35
ACTIVITIES_PER_PERSON = 60


@dataclass
class PriceBreakdown:
    per_person: int
    total: int


def calculate_price(
    *,
    direction: str,
    people_count: int,
    transport: bool,
    food: bool,
    activities: bool,
) -> PriceBreakdown:
    base = DIRECTION_BASE_PRICE.get(direction, DIRECTION_BASE_PRICE["city"])
    per_person = base

    if transport:
        per_person += TRANSPORT_PER_PERSON
    if food:
        per_person += FOOD_PER_PERSON
    if activities:
        per_person += ACTIVITIES_PER_PERSON

    total = per_person * max(people_count, 1)
    return PriceBreakdown(per_person=per_person, total=total)
