"""Glue JSON / page payloads -> clean dicts for every /zap-imoveis/* endpoint.
Pure functions, no I/O.

Sources:
  * glue search / listing records: {listing, account, medias, link,
    accountLink, children} per row — the listing carries prices as strings
    OR numbers ("400000" / 400000), areas as lists of strings or numbers
    (["35"], [30, 56] for a development's range), rooms as int lists.
  * glue /v3/locations: one block per requested field (neighborhood, city,
    street, condominium) with its own result list and totalCount.
  * site pages: the Next.js React Server Components payload, pushed as
    `self.__next_f.push([1,"<escaped chunk>"])` script rows; rsc_payload()
    JSON-decodes each chunk and joins them, rsc_object() parses the JSON
    object that follows an anchor like `"averagePrice":`. RSC placeholders
    ("$undefined", "$35" references to streamed text) are nulled.

Value conventions (shared with the other scraper packages):
  * money  numeric BRL amounts + `currency`; a 0 IPTU / condo fee is "not
           informed" and comes back null
  * dates  ISO 8601 as the site gives them (UTC, seconds)
  * keys   snake_case; `link` not `url`; booleans as questions

Fixtures captured 2026-11-07 (zap_imoveis/fixtures/): a sale search page
(Pinheiros, 30 rows), a filtered rent page, a new-developments page (units in
`children`), an empty search, a count + facets payload, a used listing, a
development listing, an expired listing (410), an unknown listing (404),
three autocomplete payloads (neighbourhood / city / none), a condominium
autocomplete, an agency account, an agency's listings, the list page, agency
page and condominium page (HTML with the RSC payload), their 404 shells and
a Cloudflare 403 page.
"""
import json
import re

from zap_imoveis.refs import (BUSINESS_LABEL, CONSTRUCTION_STATUS_LABEL, CURRENCY, LISTING_TYPE_LABEL, SITE,
                              company_link, condominium_link, location_slug_from_url, photo_url, property_link,
                              property_type_label, short_condominium_id)

_RSC_CHUNK_RE = re.compile(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)', re.S)
_RSC_REF_RE = re.compile(r"^\$[0-9a-zA-Z:]+$")
_DECODER = json.JSONDecoder()

_CONTRACT_TYPES = {"REAL_ESTATE": "agency", "PROPERTY_DEVELOPER": "developer", "OWNER": "owner",
                   "RecordType_NONE": None, "": None, None: None}
_PERIODS = {"MONTHLY": "monthly", "YEARLY": "yearly", "Period_NONE": None, "": None, None: None}
_POI_TYPES = {"BS": "bus_stop", "TP": "transport", "SW": "subway", "TR": "train"}


# ---- value helpers ---------------------------------------------------------------

def _num(value):
    """"400000" / 400000 / 3.5 -> number; "", None, non-numeric -> None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    text = str(value).strip().replace(",", ".")
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return int(number) if number == int(number) else number


def _money(value):
    """A price-like amount where 0 means "not informed"."""
    number = _num(value)
    return number if number else None


def _str(value):
    if isinstance(value, str):
        value = value.strip()
        if value and not _RSC_REF_RE.match(value):
            return value
    return None


def _lower(value):
    value = _str(value)
    return value.lower() if value else None


def _first(values):
    if isinstance(values, list):
        return values[0] if values else None
    return values


def _first_num(values):
    return _num(_first(values))


def _range(values):
    """[30, 56] -> {"min": 30, "max": 56}; a single value or empty -> None."""
    numbers = [n for n in (_num(v) for v in (values or [])) if n is not None] if isinstance(values, list) else []
    if len(numbers) < 2 or min(numbers) == max(numbers):
        return None
    return {"min": min(numbers), "max": max(numbers)}


def _iso(value):
    """"2026-05-13T03:51:05.042Z" -> "2026-05-13T03:51:05Z"; None when absent."""
    value = _str(value)
    if not value:
        return None
    return re.sub(r"\.\d+Z$", "Z", value)


def _dedupe(values):
    seen, out = set(), []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _clean(obj):
    """Null the RSC placeholders ("$undefined", "$3c" text references) in a
    decoded payload, recursively."""
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    if isinstance(obj, str) and _RSC_REF_RE.match(obj):
        return None
    return obj


# ---- RSC payload ---------------------------------------------------------------

def rsc_payload(html):
    """The joined React Server Components text of a Next.js page."""
    parts = []
    for chunk in _RSC_CHUNK_RE.findall(html or ""):
        try:
            parts.append(json.loads('"' + chunk + '"'))
        except ValueError:
            parts.append(chunk)
    return "".join(parts)


def rsc_object(text, anchor, where=None):
    """The JSON object right after `anchor` in the RSC text (cleaned), or
    None. `where(obj) -> bool` picks among several occurrences."""
    start = 0
    while True:
        index = text.find(anchor, start)
        if index < 0:
            return None
        try:
            obj, _ = _DECODER.raw_decode(text, index + len(anchor))
        except ValueError:
            start = index + len(anchor)
            continue
        if where is None or where(obj):
            return _clean(obj)
        start = index + len(anchor)


def page_title(html):
    match = re.search(r"<title>([^<]*)</title>", html or "", re.I)
    return match.group(1).strip() if match else ""


# ---- listing records -------------------------------------------------------------

def _pricing(info):
    rental = info.get("rentalInfo") or {}
    iptu = _money(info.get("iptu")) or _money(info.get("yearlyIptu"))
    period = _PERIODS.get(info.get("iptuPeriod"), _lower(info.get("iptuPeriod")))
    if iptu is not None and period is None and info.get("yearlyIptu") not in (None, "", 0, "0") and not _money(info.get("iptu")):
        period = "yearly"
    return {
        "business": BUSINESS_LABEL.get(info.get("businessType"), _lower(info.get("businessType"))),
        "price": _money(info.get("price")),
        "currency": CURRENCY,
        "condo_fee_monthly": _money(info.get("monthlyCondoFee")),
        "iptu": iptu,
        "iptu_period": period,
        "rent_total_monthly": _money(rental.get("monthlyRentalTotalPrice")),
        "rent_period": _PERIODS.get(rental.get("period"), _lower(rental.get("period"))),
        "warranties": [_lower(w) for w in rental.get("warranties") or [] if _lower(w)] or None,
    }


def _address(address, display_type=None, geolocation=None):
    address = address or {}
    point = address.get("point") or {}
    lat = _num(point.get("lat") if "lat" in point else point.get("latitude"))
    lng = _num(point.get("lon") if "lon" in point else point.get("longitude"))
    if lat is None and geolocation:
        lat, lng = _num(geolocation.get("lat")), _num(geolocation.get("lon"))
    return {
        "street": _str(address.get("street")),
        "number": _str(address.get("streetNumber")),
        "complement": _str(address.get("complement")),
        "neighborhood": _str(address.get("neighborhood")),
        "zone": _str(address.get("zone")),
        "city": _str(address.get("city")),
        "state": _str(address.get("state")),
        "state_code": _str(address.get("stateAcronym")),
        "zip_code": _str(address.get("zipCode")),
        "country": _str(address.get("country")) or "BR",
        "location_id": _str(address.get("locationId")),
        "coordinates": {"latitude": lat, "longitude": lng} if lat is not None and lng is not None else None,
        "precision": _lower(address.get("precision")) if _str(address.get("precision")) not in (None, "Precision_NONE") else None,
        "display_level": _lower(display_type) if display_type else None,
    }


def _medias(medias):
    photos, floor_plans, videos, tours = [], [], [], []
    for media in medias or []:
        kind = (media or {}).get("type")
        url = _str((media or {}).get("url"))
        if not url:
            continue
        if kind == "IMAGE":
            photos.append(photo_url(url))
        elif kind == "FLOOR_PLAN":
            floor_plans.append(photo_url(url))
        elif kind == "VIDEO_TOUR":
            tours.append(url)
        elif kind == "VIDEO":
            videos.append(url)
    return photos, floor_plans, videos, tours


def _advertiser(account, listing, account_link):
    account = account or {}
    listing = listing or {}
    phones = account.get("phones") or {}
    contact = listing.get("advertiserContact") or {}
    page_id = account.get("legacyVivarealId") or account.get("legacyZapId")
    href = _str((account_link or {}).get("href"))
    link = (SITE + href) if href else company_link(page_id)
    billing = (account.get("addresses") or {}).get("billing") or {}
    return {
        "id": _str(account.get("id")) or _str(listing.get("advertiserId")),
        "name": _str(account.get("name")) or _str((account_link or {}).get("name")),
        "link": link,
        "type": _CONTRACT_TYPES.get(listing.get("contractType"), _lower(listing.get("contractType"))),
        "license_number": _str(account.get("licenseNumber")),
        "phones": _dedupe([_str(phones.get("primary")), _str(phones.get("mobile")),
                           *[_str(p) for p in contact.get("phones") or []]]) or None,
        "whatsapp": _str(listing.get("whatsappNumber")),
        "website": _str(account.get("websiteUrl")),
        "tier": _lower(account.get("tier")),
        "is_verified": (account.get("config") or {}).get("verified") if isinstance(account.get("config"), dict) else None,
        "logo": photo_url(_str(account.get("logoUrl")), 400, 400),
        "address": _address(billing) if billing and account.get("showAddress") else None,
        "created_at": _iso(account.get("createdDate")),
    }


def _construction(listing):
    status = CONSTRUCTION_STATUS_LABEL.get(listing.get("constructionStatus"), _lower(listing.get("constructionStatus")))
    developers = [{"name": _str(d.get("name")), "logo": _str(d.get("logo") or d.get("imageUrl"))}
                  for d in listing.get("propertyDevelopers") or [] if isinstance(d, dict) and _str(d.get("name"))]
    timeline = sorted(
        ({"date": _str(e.get("date")), "status": CONSTRUCTION_STATUS_LABEL.get(e.get("constructionStatus"),
                                                                                _lower(e.get("constructionStatus")))}
         for e in listing.get("constructionStatusCalendar") or [] if isinstance(e, dict) and _str(e.get("date"))),
        key=lambda e: e["date"])
    delivered = _iso(listing.get("deliveredAt"))
    if not (status or developers or timeline or delivered):
        return None
    return {"status": status, "developer": developers[0] if developers else None,
            "timeline": timeline or None, "delivered_at": delivered}


def _unit(child):
    pricing = [_pricing(p) for p in child.get("pricingInfos") or []]
    return {
        "id": _str(child.get("id")),
        "price": pricing[0]["price"] if pricing else None,
        "currency": CURRENCY,
        "usable_area_m2": _first_num(child.get("usableAreas")),
        "total_area_m2": _first_num(child.get("totalAreas")),
        "bedrooms": _first_num(child.get("bedrooms")),
        "bathrooms": _first_num(child.get("bathrooms")),
        "parking_spaces": _first_num(child.get("parkingSpaces")),
    }


def _nearby(listing):
    nearby = listing.get("nearBy") or {}
    if not isinstance(nearby, dict) or not nearby:
        return None
    out = {}
    for key, label in (("oneKm", "within_1km"), ("twoKm", "within_2km"), ("threeKm", "within_3km")):
        block = nearby.get(key) or {}
        names = []
        for values in block.values() if isinstance(block, dict) else []:
            names.extend(_str(v) for v in values or [] if _str(v))
        out[label] = _dedupe(names) or None
    return out if any(out.values()) else None


def _pois(listing):
    pois = []
    for raw in (listing.get("address") or {}).get("poisList") or []:
        raw = _str(raw)
        if not raw:
            continue
        prefix, _, name = raw.partition(":")
        if name:
            pois.append({"type": _POI_TYPES.get(prefix, prefix.lower()), "name": name.strip()})
        else:
            pois.append({"type": None, "name": raw})
    return pois or None


def parse_listing(entry, business=None, detail=False):
    """One glue row ({listing, account, medias, link, accountLink, children})
    -> the public listing record. `business` ("SALE"/"RENTAL") picks the
    primary pricing block when the ad is listed for both."""
    entry = entry or {}
    listing = entry.get("listing") or {}
    link = entry.get("link") or {}
    pricing = [_pricing(p) for p in listing.get("pricingInfos") or [] if isinstance(p, dict)]
    wanted = BUSINESS_LABEL.get(business)
    primary = next((p for p in pricing if p["business"] == wanted), pricing[0] if pricing else None)
    others = [p for p in pricing if p is not primary] or None
    usable = _first_num(listing.get("usableAreas"))
    price = primary["price"] if primary else None
    photos, floor_plans, videos, tours = _medias(entry.get("medias"))
    stamps = [s for s in listing.get("stamps") or [] if isinstance(s, str)]
    listing_id = _str(listing.get("id"))
    record = {
        "id": listing_id,
        "link": property_link(listing_id, _str(link.get("href"))),
        "title": _str(listing.get("title")) or _str(link.get("name")),
        "description": _str(listing.get("description")),
        "business": primary["business"] if primary else None,
        "listing_type": LISTING_TYPE_LABEL.get(listing.get("listingType"), _lower(listing.get("listingType"))),
        "property_type": property_type_label(listing.get("unitTypes"), listing.get("unitSubTypes"),
                                             listing.get("usageTypes")),
        "usage": _lower(_first(listing.get("usageTypes"))),
        "status": _lower(listing.get("status")),
        "publication_type": _lower(listing.get("publicationType")),
        "external_id": _str(listing.get("externalId")),
        "pricing": primary,
        "other_pricing": others,
        "price_per_m2": round(price / usable, 2) if price and usable else None,
        "bedrooms": _first_num(listing.get("bedrooms")),
        "bathrooms": _first_num(listing.get("bathrooms")),
        "suites": _first_num(listing.get("suites")),
        "parking_spaces": _first_num(listing.get("parkingSpaces")),
        "usable_area_m2": usable,
        "total_area_m2": _first_num(listing.get("totalAreas")),
        "floor": _num(listing.get("unitFloor")) or None,
        "building_floors": _first_num(listing.get("floors")) or None,
        "units_on_floor": _num(listing.get("unitsOnTheFloor")) or None,
        "unit_ranges": None,
        "amenities": [a for a in listing.get("amenities") or [] if isinstance(a, str)] or None,
        "address": _address(listing.get("address"), listing.get("displayAddressType"),
                            listing.get("displayAddressGeolocation")),
        "photos": photos or None,
        "photo_count": len(photos),
        "floor_plans": floor_plans or None,
        "videos": videos or None,
        "virtual_tours": tours or None,
        "video_tour_link": _str(listing.get("videoTourLink")),
        "advertiser": _advertiser(entry.get("account"), listing, entry.get("accountLink")),
        "condominium_name": _str(listing.get("condominiumName")),
        "construction": _construction(listing),
        "units": [_unit(c) for c in entry.get("children") or [] if isinstance(c, dict)] or None,
        "is_below_market": any(s.startswith("DATAZAP_APPROVED") for s in stamps),
        "is_price_shown": listing.get("showPrice") if isinstance(listing.get("showPrice"), bool) else None,
        "has_virtual_tour": bool(tours or _str(listing.get("videoTourLink"))),
        "accepts_exchange": listing.get("acceptExchange") if isinstance(listing.get("acceptExchange"), bool) else None,
        "portals": [_lower(p) for p in listing.get("portals") or [] if _lower(p)] or None,
        "quality_score": _num(listing.get("lqs")),
        "created_at": _iso(listing.get("createdAt")),
        "updated_at": _iso(listing.get("updatedAt")),
    }
    ranges = {
        "usable_area_m2": _range(listing.get("usableAreas")),
        "total_area_m2": _range(listing.get("totalAreas")),
        "bedrooms": _range(listing.get("bedrooms")),
        "bathrooms": _range(listing.get("bathrooms")),
        "suites": _range(listing.get("suites")),
        "parking_spaces": _range(listing.get("parkingSpaces")),
    }
    if any(ranges.values()):
        record["unit_ranges"] = ranges
    if detail:
        record["nearby_transport"] = _nearby(listing)
        record["points_of_interest"] = _pois(listing)
    return record


def parse_search(payload, business=None):
    """A /v4/listings payload -> {total_count, results, facets, page_total}.
    Rows are deduped by id (glue pads a page with promoted listings)."""
    payload = payload or {}
    search = payload.get("search") or {}
    rows = ((search.get("result") or {}).get("listings")) or []
    seen, results = set(), []
    for entry in rows:
        record = parse_listing(entry, business)
        if record["id"] and record["id"] not in seen:
            seen.add(record["id"])
            results.append(record)
    pagination = (payload.get("page") or {}).get("uriPagination") or {}
    return {
        "total_count": _num(search.get("totalCount")),
        "page_total": _num(pagination.get("totalListingCounter")) or _num(pagination.get("total")),
        "results": results,
        "facets": parse_facets(payload),
    }


def parse_facets(payload):
    amenities = ((payload or {}).get("facets") or {}).get("amenities") or {}
    if not isinstance(amenities, dict):
        return None
    return {k: _num(v) for k, v in sorted(amenities.items(), key=lambda kv: -(kv[1] or 0))} or None


def parse_listing_detail(payload, business=None):
    """A /v2/listing/<id> payload -> the full listing record."""
    return parse_listing(payload, business, detail=True)


# ---- locations -------------------------------------------------------------------

_LOCATION_TYPES = ("neighborhood", "city", "street")


def _location_hit(kind, hit):
    address = hit.get("address") or {}
    point = address.get("point") or {}
    url = _str(hit.get("url"))
    name = {"neighborhood": address.get("neighborhood"), "city": address.get("city"),
            "street": address.get("street")}.get(kind) or address.get("neighborhood") or address.get("city")
    lat, lng = _num(point.get("lat")), _num(point.get("lon"))
    return {
        "location_id": _str(address.get("locationId")),
        "type": kind,
        "name": _str(name),
        "street": _str(address.get("street")) if kind == "street" else None,
        "neighborhood": _str(address.get("neighborhood")),
        "zone": _str(address.get("zone")),
        "city": _str(address.get("city")),
        "state": _str(address.get("state")),
        "state_code": _str(address.get("stateAcronym")),
        "coordinates": {"latitude": lat, "longitude": lng} if lat is not None and lng is not None else None,
        "slug": location_slug_from_url(url),
        "link": (SITE + url) if url else None,
        "score": _num(hit.get("score")),
    }


def parse_locations(payload):
    """A /v3/locations payload -> [{location_id, type, name, ..., link}],
    neighbourhoods first, deduped per (type, location_id, street)."""
    payload = payload or {}
    seen, results = set(), []
    for kind in _LOCATION_TYPES:
        block = payload.get(kind) or {}
        for hit in ((block.get("result") or {}).get("locations")) or []:
            record = _location_hit(kind, hit)
            key = (kind, record["location_id"], record["street"])
            if record["location_id"] and key not in seen:
                seen.add(key)
                results.append(record)
    return results


def parse_condominium_suggestions(payload):
    """A /v3/locations?fields=condominium payload -> [{id, short_id, name, address, link}]."""
    block = (payload or {}).get("condominium") or {}
    seen, results = set(), []
    for hit in ((block.get("result") or {}).get("locations")) or []:
        condo = hit.get("condominium") or {}
        uuid = _str(condo.get("uuid"))
        if not uuid or uuid in seen:
            continue
        seen.add(uuid)
        address = hit.get("address") or {}
        short = _str(condo.get("shortUuid")) or short_condominium_id(uuid)
        results.append({
            "id": uuid,
            "short_id": short,
            "name": _str(condo.get("name")),
            "address": {
                "street": _str(address.get("street")),
                "number": _str(address.get("streetNumber")),
                "neighborhood": _str(address.get("neighborhood")),
                "city": _str(address.get("city")),
                "state": _str(address.get("state")),
            },
            "link": condominium_link(short, _canonical_condo_path(_str(hit.get("url")))),
        })
    return results


def _canonical_condo_path(url):
    """The autocomplete links to /condominio/venda/<slug>/; the page lives at
    /condominio/<slug>/ (the business segment 302s there)."""
    if not url:
        return None
    return re.sub(r"^/condominio/(?:venda|aluguel)/", "/condominio/", url)


# ---- advertiser / agency ---------------------------------------------------------

def parse_account(payload):
    """The `account` block of a /v4/listings?advertiserId= payload -> the
    agency profile (glue side: CRECI, website, phones, tier, page id)."""
    account = (payload or {}).get("account") or {}
    if not account.get("id"):
        return None
    page_id = account.get("legacyVivarealId") or account.get("legacyZapId") or None
    phones = account.get("phones") or {}
    billing = (account.get("addresses") or {}).get("billing") or {}
    return {
        "id": _str(account.get("id")),
        "page_id": str(page_id) if page_id else None,
        "name": _str(account.get("name")),
        "link": company_link(page_id),
        "license_number": _str(account.get("licenseNumber")),
        "phones": _dedupe([_str(phones.get("primary")), _str(phones.get("mobile"))]) or None,
        "website": _str(account.get("websiteUrl")),
        "tier": _lower(account.get("tier")),
        "trust_score": _num(account.get("trustScore")),
        "is_verified": (account.get("config") or {}).get("verified") if isinstance(account.get("config"), dict) else None,
        "logo": photo_url(_str(account.get("logoUrl")), 400, 400),
        "address": _address(billing) if billing and account.get("showAddress") else None,
        "created_at": _iso(account.get("createdDate")),
    }


def _is_page_advertiser(obj):
    return isinstance(obj, dict) and ("officialStore" in obj or "totalCountByAdvertiser" in obj) and "address" in obj


def parse_agency_page(html):
    """/imobiliaria/<id>/ -> the page's advertiser block: rating, address,
    store branding, phones, total listings. None when the payload has none."""
    text = rsc_payload(html)
    block = rsc_object(text, '"advertiser":', _is_page_advertiser)
    if not block:
        return None
    rating = block.get("rating") or {}
    store = block.get("officialStore") or {}
    logo = (block.get("imageUrl") or {}).get("dangerousSrc") if isinstance(block.get("imageUrl"), dict) else None
    store_logo = (store.get("logoUrl") or {}).get("dangerousSrc") if isinstance(store.get("logoUrl"), dict) else None
    address = block.get("address") or {}
    pagination = rsc_object(text, '"uriPagination":') or {}
    return {
        "id": _str(block.get("id")),
        "name": _str(block.get("name")),
        "tier": _lower(block.get("tier")),
        "license_number": _str(block.get("license")),
        "phones": _dedupe([_str(p) for p in block.get("phoneNumbers") or []]) or None,
        "whatsapp": _str(block.get("whatsAppNumber")),
        "rating": {
            "score": _num(rating.get("score")),
            "ratings_count": _num(rating.get("totalRatings")),
            "feedback_count": _num(rating.get("totalFeedbacks")),
        } if rating and _num(rating.get("score")) is not None else None,
        "address": {
            "street": _str(address.get("street")),
            "number": _str(address.get("streetNumber")),
            "neighborhood": _str(address.get("neighborhood")),
            "city": _str(address.get("city")),
            "state": _str(address.get("state")) or _str(address.get("stateAcronym")),
            "zip_code": _str(address.get("zipCode")),
            "country": _str(address.get("country")),
        } if address else None,
        "logo": photo_url(_str(logo), 400, 400),
        "store": {
            "logo": _str(store_logo),
            "cover": _str((store.get("coverUrl") or {}).get("dangerousSrc")) if isinstance(store.get("coverUrl"), dict) else _str(store.get("coverUrl")),
            "description": _str(store.get("description")),
            "stamps": [_lower(s) for s in store.get("stamps") or [] if _lower(s)] or None,
        } if store else None,
        "is_verified": (block.get("config") or {}).get("verified") if isinstance(block.get("config"), dict) else None,
        "is_chat_enabled": (block.get("config") or {}).get("isChatEnabled") if isinstance(block.get("config"), dict) else None,
        "listings_count": _num(block.get("totalCountByAdvertiser")) or _num(pagination.get("totalListingCounter")),
        "created_at": _iso(block.get("createdDate")),
    }


# ---- price insights --------------------------------------------------------------

def _stats(stats):
    stats = stats or {}
    return {
        "listings_count": _num(stats.get("total_properties")),
        "average_price": _num(stats.get("avg_total_price")),
        "average_area_m2": _num(stats.get("avg_total_area")),
        "average_price_per_m2": _num(stats.get("avg_sqm")),
        "currency": CURRENCY,
    }


def parse_insights(html):
    """A list page's `averagePrice.dataZapInfo` block -> the price insights
    for its location (averages, price-range counts, top sub-locations).
    None when the page carries no block (a location the site has no
    statistics for)."""
    text = rsc_payload(html)
    block = rsc_object(text, '"averagePrice":')
    info = (block or {}).get("dataZapInfo") or {}
    main = (info.get("main_location") or {}).get("location") or {}
    if not main:
        return None
    top = info.get("top_locations") or {}
    return {
        "name": _str(main.get("name")),
        "link": _str(main.get("url")),
        "business": BUSINESS_LABEL.get(info.get("businessType"), _lower(info.get("businessType"))),
        "property_type": property_type_label([info.get("unitType")], None, None) if _str(info.get("unitType")) else None,
        "stats": _stats(main.get("stats")),
        "price_ranges": [{
            "label": _str(r.get("key")),
            "listings_count": _num(r.get("doc_count")),
            "link": _str(r.get("url")),
        } for r in main.get("price_ranges") or [] if isinstance(r, dict)] or None,
        "about": {k: _str(v) for k, v in (main.get("texts_about") or {}).items() if _str(v)} or None,
        "top_locations": [{
            "name": _str(loc.get("name")),
            "link": _str(loc.get("url")),
            "description": _str((loc.get("texts_about") or {}).get("short_description")),
            "stats": _stats(loc.get("stats")),
        } for loc in top.get("locations") or [] if isinstance(loc, dict)] or None,
    }


# ---- condominium page ------------------------------------------------------------

def parse_condominium_page(html):
    """/condominio/<slug>-id-<short>/ -> the condominium record plus the
    listings the page carries (its first page of ads)."""
    text = rsc_payload(html)
    payload = rsc_object(text, '"condominiumPayload":') or {}
    condo = payload.get("condominium") or rsc_object(text, '"condominium":', lambda o: isinstance(o, dict) and "path" in o)
    if not condo:
        return None
    address = condo.get("address") or {}
    point = address.get("point") or {}
    area = condo.get("area") or {}
    listings_block = (payload.get("listings") or {})
    rows = ((listings_block.get("result") or {}).get("listings")) or []
    pagination = rsc_object(text, '"uriPagination":') or {}
    uuid = _str(condo.get("id"))
    short = short_condominium_id(uuid) if uuid else None
    lat, lng = _num(point.get("latitude")), _num(point.get("longitude"))
    return {
        "id": uuid,
        "short_id": short,
        "name": _str(condo.get("name")),
        "link": condominium_link(short, _str(condo.get("path"))),
        "description": _str(condo.get("description")),
        "address": {
            "street": _str(address.get("street")),
            "number": _str(address.get("streetNumber")),
            "neighborhood": _str(address.get("neighborhood")),
            "city": _str(address.get("city")),
            "state": _str(address.get("state")),
            "state_code": _str(address.get("stateAcronym")),
            "zip_code": _str(address.get("zipCode")),
            "coordinates": {"latitude": lat, "longitude": lng} if lat is not None and lng is not None else None,
        },
        "area_m2": {"min": _num(area.get("from")), "max": _num(area.get("to"))} if area else None,
        "max_bedrooms": _num(condo.get("bedroomsTo")),
        "max_bathrooms": _num(condo.get("bathroomsTo")),
        "max_parking_spaces": _num(condo.get("parkingSpacesTo")),
        "sale_price_from": _money(condo.get("salePrice")),
        "rent_price_from": _money(condo.get("rentalPrice")),
        "currency": CURRENCY,
        "amenities": [a for a in condo.get("amenities") or [] if isinstance(a, str)] or None,
        "listings_count": _num(pagination.get("total")) or _num(listings_block.get("totalCount")),
        "listings": [parse_listing(e) for e in rows if isinstance(e, dict)] or None,
    }
