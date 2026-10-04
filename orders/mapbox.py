import json
import re
import urllib.parse
import urllib.request
from math import radians, sin, cos, sqrt, atan2

from django.conf import settings


class MapboxError(Exception):
    """Raised when Mapbox cannot geocode or calculate a route."""
    pass


def _normalise_text(value):
    return re.sub(
        r"[^a-z0-9\s]",
        " ",
        (value or "").lower(),
    )


def _distance_km(
    latitude1,
    longitude1,
    latitude2,
    longitude2,
):
    """
    Calculate approximate straight-line distance between two coordinates.
    Used only to help distinguish competing Mapbox candidates.
    Actual delivery distance is always calculated by Mapbox driving routes.
    """

    earth_radius_km = 6371.0

    lat1 = radians(latitude1)
    lat2 = radians(latitude2)

    delta_lat = radians(latitude2 - latitude1)
    delta_lon = radians(longitude2 - longitude1)

    a = (
        sin(delta_lat / 2) ** 2
        + cos(lat1)
        * cos(lat2)
        * sin(delta_lon / 2) ** 2
    )

    c = 2 * atan2(
        sqrt(a),
        sqrt(1 - a),
    )

    return earth_radius_km * c


def geocode_address(
    address,
    reference_latitude=None,
    reference_longitude=None,
):
    """
    Convert a human-readable South African address into longitude/latitude.

    Mapbox may return several candidates for an address. Candidates are
    scored using street, locality and address information.

    If the result is genuinely ambiguous, the function refuses to choose
    silently.

    reference_latitude/reference_longitude are optional and are normally
    the shop coordinates. They are used only as a secondary signal when
    multiple candidates are otherwise similar.

    Returns:
        (longitude, latitude)
    """

    if not address:
        raise MapboxError("Address is empty.")

    token = settings.MAPBOX_TOKEN

    if not token:
        raise MapboxError("Mapbox token is not configured.")

    query = urllib.parse.quote(address)
    print("AIRXPRESS MAPBOX ADDRESS:", repr(address))


    url = (
        "https://api.mapbox.com/search/geocode/v6/forward"
        f"?q={query}"
        "&country=ZA"
        "&limit=10"
        f"&access_token={token}"
    )

    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            data = json.loads(
                response.read().decode("utf-8")
            )
    except Exception as exc:
        raise MapboxError(
            f"Mapbox geocoding failed: {exc}"
        ) from exc

    features = data.get("features", [])

    if not features:
        raise MapboxError(
            "Mapbox could not find that address."
        )

    normalized_requested = _normalise_text(address)

    requested_words = {
        word
        for word in normalized_requested.split()
        if len(word) >= 3
    }

    ignored_words = {
        "street",
        "st",
        "road",
        "rd",
        "drive",
        "dr",
        "avenue",
        "ave",
        "place",
        "pl",
        "close",
        "crescent",
        "cres",
        "lane",
        "ln",
        "south",
        "africa",
        "gauteng",
        "johannesburg",
        "pretoria",
        "sandton",
        "city",
        "extension",
        "ext",
    }

    useful_words = requested_words - ignored_words

    # ---------------------------------------------------------
    # Identify the requested suburb/locality.
    # ---------------------------------------------------------

    requested_locality = None

    locality_match = re.search(
        r"\b(?:ext|extension)\s*\d+\s+(.+?)\s+(?:roodepoort|johannesburg|sandton|pretoria|gauteng|south africa)\b",
        normalized_requested,
    )

    if locality_match:
        requested_locality = locality_match.group(1).strip()

    if requested_locality:
        requested_locality_words = {
            word
            for word in requested_locality.split()
            if len(word) >= 3
        }
    else:
        requested_locality_words = set()
    # ---------------------------------------------------------
    # Identify the requested street name.
    # ---------------------------------------------------------

    street_name = None

    street_match = re.search(
        r"\b\d+\s+([a-z0-9]+)\s+"
        r"(?:street|st|road|rd|drive|dr|avenue|ave|"
        r"place|pl|close|crescent|cres|lane|ln)\b",
        normalized_requested,
    )

    if street_match:
        street_name = street_match.group(1)

    # ---------------------------------------------------------
    # Extract requested house number.
    # ---------------------------------------------------------

    requested_number = None

    number_match = re.search(
        r"\b(\d+)\b",
        normalized_requested,
    )

    if number_match:
        requested_number = number_match.group(1)

    scored_candidates = []

    for feature in features:

        properties = feature.get(
            "properties",
            {},
        )

        geometry = feature.get(
            "geometry",
            {},
        )

        coordinates = geometry.get(
            "coordinates",
        )

        if not coordinates or len(coordinates) < 2:
            continue

        full_address = (
            properties.get("full_address")
            or properties.get("name")
            or ""
        )

        # Include Mapbox geographic context in address matching.
        # This lets AirXpress verify suburb/city instead of relying
        # only on the returned full address.
        context = properties.get("context", {}) or {}

        context_names = []

        for context_type in (
            "neighborhood",
            "locality",
            "place",
            "district",
            "region",
            "postcode",
        ):
            context_item = context.get(context_type, {}) or {}
            context_name = context_item.get("name")

            if context_name:
                context_names.append(str(context_name))

        context_text = " ".join(context_names)

        normalized_feature = _normalise_text(
            f"{full_address} {context_text}"
        )

        feature_words = set(
            normalized_feature.split()
        )

        score = 0

        # -----------------------------------------------------
        # Locality/suburb is a very strong signal.
        # -----------------------------------------------------

        if requested_locality_words:
            matched_locality_words = sum(
                1
                for word in requested_locality_words
                if word in feature_words
            )

            if matched_locality_words == len(requested_locality_words):
                score += 100
            elif matched_locality_words > 0:
                score += 40 * matched_locality_words
            else:
                score -= 50

        # -----------------------------------------------------
        # Street name is the strongest signal.
        # -----------------------------------------------------

        if street_name and street_name in feature_words:
            score += 100

        # -----------------------------------------------------
        # Match meaningful words from the customer's address.
        # -----------------------------------------------------

        matched_useful_words = 0

        for word in useful_words:
            if word in feature_words:
                score += 10
                matched_useful_words += 1

        # -----------------------------------------------------
        # House number match.
        # -----------------------------------------------------

        if requested_number:
            if requested_number in feature_words:
                score += 25

        # -----------------------------------------------------
        # Secondary proximity signal.
        #
        # This is NOT the delivery distance. It only helps when
        # two candidates are otherwise similar.
        # -----------------------------------------------------

        proximity_km = None

        if (
            reference_latitude is not None
            and reference_longitude is not None
        ):
            try:
                candidate_longitude = float(
                    coordinates[0]
                )

                candidate_latitude = float(
                    coordinates[1]
                )

                proximity_km = _distance_km(
                    float(reference_latitude),
                    float(reference_longitude),
                    candidate_latitude,
                    candidate_longitude,
                )

                # Small bonus for nearby candidates.
                if proximity_km <= 5:
                    score += 8
                elif proximity_km <= 12:
                    score += 4

            except (TypeError, ValueError):
                proximity_km = None

        scored_candidates.append(
            {
                "score": score,
                "address": full_address,
                "context": context_text,
                "coordinates": coordinates,
                "matched_useful_words": matched_useful_words,
                "proximity_km": proximity_km,
            }
        )

    if not scored_candidates:
        raise MapboxError(
            "Mapbox returned no usable coordinates."
        )

    # ---------------------------------------------------------
    # HARD LOCALITY VERIFICATION
    #
    # If the customer supplied a specific suburb/locality,
    # Mapbox must return that locality in its geographic context.
    #
    # Never allow a different suburb to win merely because the
    # street name and house number happen to match.
    # ---------------------------------------------------------

    if requested_locality_words:
        verified_candidates = []

        for candidate in scored_candidates:
            candidate_words = set(
                _normalise_text(
                    f"{candidate['address']} {candidate.get('context', '')}"
                ).split()
            )

            if all(
                word in candidate_words
                for word in requested_locality_words
            ):
                verified_candidates.append(candidate)

        if not verified_candidates:
            raise MapboxError(
                "We could not verify the delivery address in the "
                "suburb/locality you entered. Please check the "
                "suburb, city or extension and try again."
            )

        scored_candidates = verified_candidates

    scored_candidates.sort(
        key=lambda candidate: (
            candidate["score"],
            candidate["matched_useful_words"],
        ),
        reverse=True,
    )

    best = scored_candidates[0]

    second = (
        scored_candidates[1]
        if len(scored_candidates) > 1
        else None
    )

    # ---------------------------------------------------------
    # Minimum confidence requirement.
    # ---------------------------------------------------------

    if best["score"] < 50:
        raise MapboxError(
            "Mapbox found locations, but none matched "
            "the requested address closely enough. "
            "Please provide a more complete address."
        )

    # ---------------------------------------------------------
    # Ambiguity protection.
    #
    # If the top two candidates are both strong and nearly tied,
    # do not silently select one.
    # ---------------------------------------------------------

    if second:
        score_difference = (
            best["score"] - second["score"]
        )

        if (
            best["score"] >= 80
            and second["score"] >= 70
            and score_difference < 20
        ):
            raise MapboxError(
                "Mapbox found multiple similarly matching "
                "locations. Please provide a more complete "
                "delivery address, including suburb or "
                "extension."
            )

    print(
        "AIRXPRESS MAPBOX:",
        "selected=",
        best["address"],
        "score=",
        best["score"],
        "proximity_km=",
        (
            round(best["proximity_km"], 2)
            if best["proximity_km"] is not None
            else "n/a"
        ),
    )

    return (
        float(best["coordinates"][0]),
        float(best["coordinates"][1]),
    )


def calculate_driving_distance(
    shop_latitude,
    shop_longitude,
    customer_address,
):
    """
    Calculate actual driving distance between the saved shop location
    and the customer address.

    Returns:
        {
            "distance_km": float,
            "duration_minutes": float,
        }
    """

    if shop_latitude is None or shop_longitude is None:
        raise MapboxError(
            "The shop does not have a configured map location."
        )

    customer_lon, customer_lat = geocode_address(
        customer_address,
        reference_latitude=shop_latitude,
        reference_longitude=shop_longitude,
    )

    token = settings.MAPBOX_TOKEN

    if not token:
        raise MapboxError("Mapbox token is not configured.")

    shop_lon = float(shop_longitude)
    shop_lat = float(shop_latitude)

    url = (
        "https://api.mapbox.com/directions/v5/mapbox/driving/"
        f"{shop_lon},{shop_lat};{customer_lon},{customer_lat}"
        "?overview=false"
        f"&access_token={token}"
    )

    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            data = json.loads(
                response.read().decode("utf-8")
            )
    except Exception as exc:
        raise MapboxError(
            f"Mapbox routing failed: {exc}"
        ) from exc

    if data.get("code") != "Ok":
        raise MapboxError(
            data.get(
                "message",
                "Mapbox could not calculate the route.",
            )
        )

    routes = data.get("routes", [])

    if not routes:
        raise MapboxError(
            "Mapbox returned no driving route."
        )

    route = routes[0]

    distance_km = route["distance"] / 1000
    duration_minutes = route["duration"] / 60
    return {
        "distance_km": round(distance_km, 2),
        "duration_minutes": round(duration_minutes, 1),
        "customer_longitude": float(customer_lon),
        "customer_latitude": float(customer_lat),
    }




def calculate_driver_route(
    driver_latitude,
    driver_longitude,
    customer_latitude,
    customer_longitude,
):
    """
    Calculate the live driving route from the driver's current GPS
    position to the customer's saved destination.

    Returns:
        {
            "distance_km": float,
            "duration_minutes": float,
            "geometry": GeoJSON geometry,
        }
    """

    if (
        driver_latitude is None
        or driver_longitude is None
        or customer_latitude is None
        or customer_longitude is None
    ):
        return None

    token = settings.MAPBOX_TOKEN

    if not token:
        raise MapboxError(
            "Mapbox token is not configured."
        )

    driver_lon = float(driver_longitude)
    driver_lat = float(driver_latitude)
    customer_lon = float(customer_longitude)
    customer_lat = float(customer_latitude)

    url = (
        "https://api.mapbox.com/directions/v5/mapbox/driving/"
        f"{driver_lon},{driver_lat};"
        f"{customer_lon},{customer_lat}"
        "?overview=full"
        "&geometries=geojson"
        f"&access_token={token}"
    )

    try:
        with urllib.request.urlopen(
            url,
            timeout=10,
        ) as response:
            data = json.loads(
                response.read().decode("utf-8")
            )
    except Exception as exc:
        raise MapboxError(
            f"Mapbox live routing failed: {exc}"
        ) from exc

    if data.get("code") != "Ok":
        raise MapboxError(
            data.get(
                "message",
                "Mapbox could not calculate the live route.",
            )
        )

    routes = data.get("routes", [])

    if not routes:
        raise MapboxError(
            "Mapbox returned no live driving route."
        )

    route = routes[0]

    return {
        "distance_km": round(
            route["distance"] / 1000,
            2,
        ),
        "duration_minutes": round(
            route["duration"] / 60,
            1,
        ),
        "geometry": route.get("geometry"),
    }