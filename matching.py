from math import asin, cos, radians, sin, sqrt

MAX_MATCH_DISTANCE_KM = 500.0
DISTANCE_SCORE_MAX = 60.0
DAY_BONUS = 10.0
TIGHT_FIT_BONUS = 10.0
TIGHT_FIT_THRESHOLD = 0.8  # utilization (load weight / truck capacity)


def haversine_km(lat1, lng1, lat2, lng2) -> float:
    r = 6371.0
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return 2 * r * asin(sqrt(a))


def score_match(load, truck, distance_km: float) -> float:
    score = DISTANCE_SCORE_MAX * (1 - distance_km / MAX_MATCH_DISTANCE_KM)
    if truck.available_from.date() <= load.pickup_time.date() <= truck.available_until.date():
        score += DAY_BONUS
    utilization = load.weight_kg / truck.capacity_kg
    if utilization >= TIGHT_FIT_THRESHOLD:
        score += TIGHT_FIT_BONUS
    return score


def compatible_trucks(load, trucks):
    # Hard filters: equipment, capacity, availability window, truck available, within 500 km.
    results = []
    for truck in trucks:
        if truck.status != "available":
            continue
        if truck.equipment_type != load.equipment_type:
            continue
        if truck.capacity_kg < load.weight_kg:
            continue
        if not (truck.available_from <= load.pickup_time <= truck.available_until):
            continue
        distance_km = haversine_km(load.origin_lat, load.origin_lng, truck.current_lat, truck.current_lng)
        if distance_km > MAX_MATCH_DISTANCE_KM:
            continue
        score = score_match(load, truck, distance_km)
        results.append({"truck": truck, "distance_km": round(distance_km, 1), "score": round(score, 1)})
    results.sort(key=lambda r: r["score"], reverse=True)
    return results
