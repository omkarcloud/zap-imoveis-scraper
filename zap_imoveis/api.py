"""The /zap-imoveis/* endpoint functions (route_glue's route_table calls them
with the schema's loaded kwargs).

Caching (cache.cached_call, keyed on the validated params):

  * every location lookup (free text or a link's slug -> the glue location
    id + the site's path slug) is cached for a week under
    zap_imoveis.locations, so repeated searches for "Pinheiros, São Paulo"
    resolve once;
  * companies/details and companies/properties share ONE cached agency
    record (zap_imoveis.company: the agency page block + the glue account
    block), so a client reading both pays the two upstream calls once;
  * the other endpoints cache their own response.

Pagination: glue serves 30 rows a page and refuses `from + size` past 1,500,
so total_pages is capped at 50 and a page past the end is an empty page.
"""
import math
import re
import unicodedata

from cache import cached_call
from zap_imoveis import cache_config as ttl
from zap_imoveis import parsers, refs
from zap_imoveis.fetch import (ZapImoveisNotFound, fetch_account, fetch_agency_page, fetch_condominium_page,
                               fetch_count, fetch_list_page, fetch_listing, fetch_locations, fetch_search)


# How much better a neighbourhood's autocomplete score must be than a
# same-named city's for a bare name to mean the neighbourhood (api._pick_by_text).
NEIGHBOURHOOD_LEAD = 1.5


def _fold(text):
    """Lower-case, accent-free, single-spaced text for loose name matching."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


# ---- location resolution -----------------------------------------------------------

def _locations(query, fields="neighborhood,city,street", size=10):
    return cached_call("zap_imoveis.locations", {"query": query, "fields": fields, "size": size},
                       lambda query, fields, size: parsers.parse_locations(fetch_locations(query, fields, size)),
                       ttl.LOCATIONS_CACHE)


def _pick_by_text(hits, text):
    """The autocomplete hit for a typed place.

    "Pinheiros, São Paulo": the part after the comma scopes the hits to that
    city / state, then a neighbourhood wins over a city, an exact name over a
    partial one. A bare name ("São Paulo", "Pinheiros"): the exact-name hit
    with the best score across neighbourhoods and cities — the scores are
    comparable across the two indexes (Pinheiros: the SP neighbourhood 9.4,
    the ES town 2.8; Curitiba: the city 7.9, no neighbourhood) — where a
    neighbourhood needs a NEIGHBOURHOOD_LEAD lead over a same-named city,
    because a bare "São Paulo" means the city (its neighbourhood in Belo
    Horizonte scores 5.44 to the city's 5.42). Streets only when nothing else
    matched."""
    if not hits:
        return None
    parts = [_fold(p) for p in text.split(",") if _fold(p)]
    if not parts:
        return hits[0]
    name, rest = parts[0], parts[1:]

    def score(hit):
        return hit.get("score") or 0

    def matches_rest(hit):
        return all(any(part in _fold(hit.get(k)) for k in ("city", "state", "state_code", "zone") if hit.get(k))
                   for part in rest)

    def exact(hit):
        return _fold(hit.get("name")) == name

    pool = [h for h in hits if h["type"] in ("neighborhood", "city")] or hits
    if rest:
        scoped = [h for h in pool if matches_rest(h)] or pool
        for kind in ("neighborhood", "city"):
            typed = [h for h in scoped if h["type"] == kind]
            if typed:
                return max([h for h in typed if exact(h)] or typed, key=score)
        return scoped[0]
    candidates = [h for h in pool if exact(h)] or pool
    best_city = max((h for h in candidates if h["type"] == "city"), key=score, default=None)
    best_other = max((h for h in candidates if h["type"] != "city"), key=score, default=None)
    if best_city and best_other:
        # a neighbourhood needs a clear lead over a same-named city (Pinheiros
        # 9.4 vs 2.8 yes; São Paulo 5.44 vs 5.42 no — the city it is)
        return best_other if score(best_other) >= NEIGHBOURHOOD_LEAD * score(best_city) else best_city
    return best_city or best_other


def _lookup_hits(query):
    return _locations(query) or _locations(query, size=20)


def resolve_location(descriptor):
    """A LocationRefField descriptor -> {"location_id", "slug", "name", "type",
    "filters"} ("filters" = what a pasted link carried). Raises
    ZapImoveisNotFound when the autocomplete knows no such place."""
    kind = descriptor["kind"]
    if kind == "text":
        hit = _pick_by_text(_lookup_hits(descriptor["query"]), descriptor["query"])
        if not hit:
            raise ZapImoveisNotFound(f"no place matches {descriptor['query']!r}")
        return {"location_id": hit["location_id"], "slug": hit["slug"], "name": hit["name"],
                "type": hit["type"], "filters": {}}
    if kind == "link":
        slug = descriptor["slug"]
        filters = descriptor.get("filters") or {}
        if descriptor.get("location_id"):
            return {"location_id": descriptor["location_id"], "slug": slug, "name": None, "type": None,
                    "filters": filters}
        query = slug.split("+")[-1].replace("-", " ") or slug.split("+")[1].replace("-", " ")
        hits = [h for h in _lookup_hits(query) if h.get("slug") == slug]
        if not hits:
            # a zone-only slug (sp+sao-paulo+zona-oeste) or a city: match on the prefix
            hits = [h for h in _lookup_hits(query) if h.get("slug") and slug.startswith(h["slug"])]
        if not hits:
            raise ZapImoveisNotFound(f"no place matches the link location {slug!r}")
        hit = hits[0]
        return {"location_id": hit["location_id"], "slug": hit["slug"], "name": hit["name"],
                "type": hit["type"], "filters": filters}
    # a bare glue location id: the slug (for the insights page) comes from
    # the autocomplete hit with the same id
    location_id = descriptor["location_id"]
    name = location_id.split(">")[-1]
    hit = next((h for h in _lookup_hits(name) if h["location_id"] == location_id), None)
    return {"location_id": location_id, "slug": hit["slug"] if hit else None,
            "name": hit["name"] if hit else name, "type": hit["type"] if hit else None, "filters": {}}


def _location_summary(resolved):
    return {"location_id": resolved["location_id"], "name": resolved["name"], "type": resolved["type"],
            "link": (refs.SITE + "/venda/imoveis/" + resolved["slug"] + "/") if resolved.get("slug") else None}


# ---- glue filter encoding ----------------------------------------------------------

def _glue_search_params(location_id, business, listing_type, page, sort=None, property_type=None,
                        min_bedrooms=None, min_bathrooms=None, min_parking=None, min_price=None, max_price=None,
                        min_area=None, max_area=None, min_condo_fee=None, max_condo_fee=None, amenities=None,
                        below_market=None, no_guarantor=None, near_transit=None, virtual_tour=None,
                        construction_status=None, **_ignored):
    """The site's own encodeGlueListingFilters, for one page."""
    params = {
        "categoryPage": "RESULT",
        "business": business,
        "listingType": listing_type,
        "addressLocationId": location_id,
        "size": refs.PAGE_SIZE,
        "from": (page - 1) * refs.PAGE_SIZE,
        "images": "webp",
        "parentId": "null",
        "portal": "ZAP",
    }
    params.update(refs.unit_type_params(property_type))
    for key, value in (("bedrooms", min_bedrooms), ("bathrooms", min_bathrooms), ("parkingSpaces", min_parking)):
        encoded = refs.min_count_param(value)
        if encoded:
            params[key] = encoded
    for key, value in (("priceMin", min_price), ("priceMax", max_price), ("usableAreasMin", min_area),
                       ("usableAreasMax", max_area), ("priceMinCondo", min_condo_fee), ("priceMaxCondo", max_condo_fee)):
        if value is not None:
            params[key] = int(value) if float(value) == int(value) else value
    if amenities:
        params["amenities"] = ",".join(amenities)
    if below_market:
        params["stamps"] = f"DATAZAP_APPROVED_{business}"
    if no_guarantor and business == "RENTAL":
        params["warranties"] = "zapway"
    if near_transit:
        params["transportNearBy"] = 2
    if virtual_tour:
        params["hasVirtualTour"] = "true"
    if construction_status:
        params["constructionStatus"] = construction_status
    template = refs.SORTS.get(sort or "relevance")
    if template:
        params["sort"] = template.format(business=business)
    return params


def _pagination(page, total_count):
    capped = min(total_count or 0, refs.MAX_RESULTS)
    return {
        "page": page,
        "items_per_page": refs.PAGE_SIZE,
        "total_pages": math.ceil(capped / refs.PAGE_SIZE) if capped else 0,
        "total_count": total_count,
    }


def _filters_echo(data, keys):
    return {k: data.get(k) for k in keys}

_FILTER_KEYS = ("property_type", "min_bedrooms", "min_bathrooms", "min_parking", "min_price", "max_price",
                "min_area", "max_area", "min_condo_fee", "max_condo_fee", "amenities", "below_market",
                "no_guarantor", "near_transit", "virtual_tour")


def _merge_link_filters(data, resolved):
    """A pasted search link fills the filters the caller left unset."""
    merged = dict(data)
    carried = resolved.get("filters") or {}
    for key, value in carried.items():
        if key in ("business", "listing_type", "sort", "page"):
            continue
        if key == "property_type":
            if not merged.get("property_type") and value:
                merged["property_type"] = [value]
        elif merged.get(key) is None:
            merged[key] = value
    return merged


# ---- locations/search --------------------------------------------------------------

def _locations_search(query, limit):
    results = parsers.parse_locations(fetch_locations(query, size=limit))
    return {"query": query, "count": len(results), "results": results}


def locations_search(**data):
    return cached_call("zap_imoveis.locations_search", data, _locations_search, ttl.LOCATIONS_CACHE)


# ---- properties/search + developments/search ----------------------------------------

def _search(listing_type, data):
    resolved = resolve_location(data["location"])
    data = _merge_link_filters(data, resolved)
    page, business = data["page"], data["business"]
    params = _glue_search_params(resolved["location_id"], business, listing_type, page, **{
        k: v for k, v in data.items() if k not in ("location", "business", "page")})
    parsed = parsers.parse_search(fetch_search(params), business)
    return {
        "location": _location_summary(resolved),
        "business": refs.BUSINESS_LABEL[business],
        "listing_type": refs.LISTING_TYPE_LABEL[listing_type],
        "sort": data.get("sort") or "relevance",
        "filters": _filters_echo(data, _FILTER_KEYS + (("construction_status",) if listing_type == "DEVELOPMENT" else ())),
        "results": parsed["results"],
        "pagination": _pagination(page, parsed["total_count"]),
    }


def properties_search(**data):
    return cached_call("zap_imoveis.search", data, lambda **d: _search("USED", d), ttl.SEARCH_CACHE)


def developments_search(**data):
    return cached_call("zap_imoveis.developments", data, lambda **d: _search("DEVELOPMENT", d), ttl.SEARCH_CACHE)


# ---- properties/count ----------------------------------------------------------------

def _count(data):
    resolved = resolve_location(data["location"])
    data = _merge_link_filters(data, resolved)
    business = data["business"]
    listing_type = (resolved.get("filters") or {}).get("listing_type") or "USED"
    params = _glue_search_params(resolved["location_id"], business, listing_type, 1, **{
        k: v for k, v in data.items() if k not in ("location", "business")})
    payload = fetch_count(params)
    total = parsers._num(((payload.get("search") or {}).get("totalCount")))
    return {
        "location": _location_summary(resolved),
        "business": refs.BUSINESS_LABEL[business],
        "listing_type": refs.LISTING_TYPE_LABEL[listing_type],
        "filters": _filters_echo(data, _FILTER_KEYS),
        "total_count": total,
        "pages_available": math.ceil(min(total or 0, refs.MAX_RESULTS) / refs.PAGE_SIZE),
        "amenities": parsers.parse_facets(payload),
    }


def properties_count(**data):
    return cached_call("zap_imoveis.count", data, lambda **d: _count(d), ttl.COUNT_CACHE)


# ---- properties/details -------------------------------------------------------------

def _property_details(property):
    return parsers.parse_listing_detail(fetch_listing(property))


def properties_details(**data):
    return cached_call("zap_imoveis.listing", data, _property_details, ttl.LISTING_CACHE)


# ---- the shared agency record --------------------------------------------------------

def _company_record(company):
    """The agency page block + the glue account block, merged. `company` is a
    page id (digits) or an advertiser uuid; each side yields the other's id."""
    page_block, account = None, None
    if refs.is_uuid(company):
        account = parsers.parse_account(fetch_account(company))
        if account is None:
            raise ZapImoveisNotFound(f"advertiser {company} not found")
        if account.get("page_id"):
            try:
                page_block = parsers.parse_agency_page(fetch_agency_page(account["page_id"]))
            except ZapImoveisNotFound:
                page_block = None
    else:
        page_block = parsers.parse_agency_page(fetch_agency_page(company))
        if page_block is None:
            raise ZapImoveisNotFound(f"agency {company} not found")
        if page_block.get("id"):
            try:
                account = parsers.parse_account(fetch_account(page_block["id"]))
            except ZapImoveisNotFound:
                account = None
    page_block = page_block or {}
    account = account or {}
    page_id = account.get("page_id") or (company if not refs.is_uuid(company) else None)
    phones = []
    for source in (account.get("phones"), page_block.get("phones")):
        for phone in source or []:
            if phone not in phones:
                phones.append(phone)
    return {
        "id": account.get("id") or page_block.get("id"),
        "page_id": page_id,
        "name": account.get("name") or page_block.get("name"),
        "link": refs.company_link(page_id),
        "type": None,
        "license_number": account.get("license_number") or page_block.get("license_number"),
        "phones": phones or None,
        "whatsapp": page_block.get("whatsapp"),
        "website": account.get("website"),
        "tier": account.get("tier") or page_block.get("tier"),
        "trust_score": account.get("trust_score"),
        "rating": page_block.get("rating"),
        "is_verified": account.get("is_verified") if account.get("is_verified") is not None else page_block.get("is_verified"),
        "is_chat_enabled": page_block.get("is_chat_enabled"),
        "logo": account.get("logo") or page_block.get("logo"),
        "store": page_block.get("store"),
        "address": page_block.get("address") or account.get("address"),
        "listings_count": page_block.get("listings_count"),
        "created_at": account.get("created_at") or page_block.get("created_at"),
    }


def _record(company):
    return cached_call("zap_imoveis.company", {"company": company}, _company_record, ttl.COMPANY_CACHE)


def companies_details(company):
    record = dict(_record(company))
    record.pop("type", None)
    return record


# ---- companies/properties --------------------------------------------------------------

def _company_properties(company, business, page):
    record = _record(company)
    advertiser_id = record["id"]
    params = {
        "categoryPage": "ADVERTISER",
        "advertiserId": advertiser_id,
        "business": business,
        "size": refs.PAGE_SIZE,
        "from": (page - 1) * refs.PAGE_SIZE,
        "images": "webp",
        "portal": "ZAP",
    }
    parsed = parsers.parse_search(fetch_search(params, f"advertiser {advertiser_id} listings"), business)
    results = [r for r in parsed["results"] if (r.get("advertiser") or {}).get("id") in (advertiser_id, None)]
    return {
        "company": {"id": record["id"], "page_id": record["page_id"], "name": record["name"], "link": record["link"]},
        "business": refs.BUSINESS_LABEL[business],
        "results": results,
        "pagination": _pagination(page, parsed["total_count"]),
    }


def companies_properties(**data):
    return cached_call("zap_imoveis.company_properties", data, _company_properties, ttl.COMPANY_PROPERTIES_CACHE)


# ---- locations/insights -------------------------------------------------------------

def _insights(location, business, property_type):
    resolved = resolve_location(location)
    if not resolved.get("slug"):
        raise ZapImoveisNotFound("the site has no list page for this location")
    type_slug = refs.UNIT_TYPES[property_type][4] if property_type else None
    path = refs.search_path(resolved["slug"], business, "USED", type_slug)
    insights = parsers.parse_insights(fetch_list_page(path))
    if insights is None:
        raise ZapImoveisNotFound("the site publishes no price statistics for this location")
    return {
        "location": _location_summary(resolved),
        "business": refs.BUSINESS_LABEL[business],
        "property_type": property_type,
        "source_link": refs.SITE + path,
        **{k: v for k, v in insights.items() if k not in ("business", "property_type")},
    }


def locations_insights(**data):
    return cached_call("zap_imoveis.insights", data, _insights, ttl.INSIGHTS_CACHE)


# ---- condominiums --------------------------------------------------------------------

def _condominiums_search(query, limit):
    results = parsers.parse_condominium_suggestions(fetch_locations(query, "condominium", limit))
    return {"query": query, "count": len(results), "results": results}


def condominiums_search(**data):
    return cached_call("zap_imoveis.condominiums_search", data, _condominiums_search, ttl.CONDOMINIUMS_SEARCH_CACHE)


def _condominium_details(condominium):
    record = parsers.parse_condominium_page(fetch_condominium_page(condominium))
    if record is None:
        raise ZapImoveisNotFound(f"condominium {condominium} not found")
    return record


def condominiums_details(**data):
    return cached_call("zap_imoveis.condominium", data, _condominium_details, ttl.CONDOMINIUM_CACHE)
