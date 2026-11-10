"""Reference resolvers + the vocabulary tables for /zap-imoveis/*.

ONE param per input (tripadvisor QueryOrIdField convention, never a sibling
`url`/`id` pair). Resolvers raise ValueError with a user-facing message
(schema_fields.RefField turns it into a 400); they do no I/O.

  property      numeric listing id (2886301373) OR any zapimoveis.com.br /
                vivareal.com.br listing link (/imovel/<slug>-id-<id>/,
                /lancamentos/<slug>-id-<id>/)
  company       the agency's numeric page id (814814, from
                /imobiliaria/814814/), its advertiser uuid, OR the agency link
  condominium   the condo's short id (59243c97-9ff5), full uuid, OR the
                /condominio/<slug>-id-<short>/ link
  location      a glue location id ("BR>Sao Paulo>NULL>Sao Paulo>Zona Oeste>
                Pinheiros"), a zapimoveis.com.br search link, OR free text
                ("Pinheiros, São Paulo") — the text / link slug is resolved
                through the site's own autocomplete in api.py (network)

Vocabulary (read from the site's bundle `filterRules` + `encodeGlueListingFilters`,
2026-11-07): the 21 unit types with the glue tokens the site sends for each,
the five sort orders, the construction stages and the site's own path slugs
for the property types (list page footer links, same date).
"""
import re
from urllib.parse import parse_qs, unquote, urlparse

SITE = "https://www.zapimoveis.com.br"
GLUE = "https://glue-api.zapimoveis.com.br"
X_DOMAIN = "www.zapimoveis.com.br"

CURRENCY = "BRL"
PAGE_SIZE = 30            # glue's maximum `size`; 36 -> 400
MAX_RESULTS = 1500        # glue: "From + Size is above acceptable limit" past it
MAX_PAGE = MAX_RESULTS // PAGE_SIZE   # 50; the site's ?pagina=51 is a 404 too

_SITE_HOSTS = ("zapimoveis.com.br", "vivareal.com.br")

LISTING_ID_RE = re.compile(r"^\d{5,12}$")
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
SHORT_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}$", re.I)
LOCATION_ID_RE = re.compile(r"^BR(>[^>]*){1,6}$")

_LINK_LISTING_RE = re.compile(r"(?:^|[-/])id-(\d{5,12})/?(?:[?#]|$)")
_LINK_AGENCY_RE = re.compile(r"/imobiliaria/(\d{1,12})/?")
_LINK_CONDO_RE = re.compile(r"/condominio/(?:[^/]+/)?[^/]*-id-([0-9a-f]{8}-[0-9a-f]{4})/?", re.I)
_LINK_SEARCH_RE = re.compile(
    r"^/(venda|aluguel|lancamentos)/(?:([a-z0-9\-]+)/)?([a-z]{2}\+[a-z0-9\-]+(?:\+[a-z0-9\-]*)*)/(?:(\d)-quartos/)?$")


def _is_link(value):
    return value.startswith(("http://", "https://", "//"))


def _parse_site_link(value, what):
    url = value if not value.startswith("//") else "https:" + value
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if not any(host == h or host.endswith("." + h) for h in _SITE_HOSTS):
        raise ValueError(f"Must be a zapimoveis.com.br {what} link.")
    return parsed


# ---- property ----------------------------------------------------------------

def resolve_property(value):
    """Bare numeric listing id or a ZAP / VivaReal listing link -> the id."""
    value = (value or "").strip()
    if LISTING_ID_RE.match(value):
        return value
    if _is_link(value):
        parsed = _parse_site_link(value, "listing")
        match = _LINK_LISTING_RE.search(parsed.path)
        if match:
            return match.group(1)
        raise ValueError("Must be a zapimoveis.com.br listing link "
                         "(https://www.zapimoveis.com.br/imovel/<slug>-id-<id>/).")
    raise ValueError("Must be a numeric listing id (2886301373) or a zapimoveis.com.br listing link.")


def property_link(listing_id, href=None):
    """The canonical listing link: the site's own href when the payload has
    one, else the id-only form (any slug 302s to the canonical one)."""
    if href:
        return href if href.startswith("http") else SITE + href
    return f"{SITE}/imovel/id-{listing_id}/"


# ---- company (advertiser / agency) ---------------------------------------------

def resolve_company(value):
    """Agency page id (814814), advertiser uuid, or /imobiliaria/<id>/ link ->
    the id string (digits = page id, uuid = advertiser id)."""
    value = (value or "").strip()
    if value.isdigit() and 1 <= len(value) <= 12:
        return value
    if UUID_RE.match(value):
        return value.lower()
    if _is_link(value):
        parsed = _parse_site_link(value, "agency")
        match = _LINK_AGENCY_RE.search(parsed.path)
        if match:
            return match.group(1)
        raise ValueError("Must be a zapimoveis.com.br agency link "
                         "(https://www.zapimoveis.com.br/imobiliaria/<id>/).")
    raise ValueError("Must be an agency id (814814), an advertiser uuid or a "
                     "zapimoveis.com.br agency link.")


def is_uuid(value):
    return bool(UUID_RE.match(value or ""))


def company_link(page_id):
    return f"{SITE}/imobiliaria/{page_id}/" if page_id else None


# ---- condominium ---------------------------------------------------------------

def short_condominium_id(uuid):
    """The site's short condo id = the uuid's first 8 + last 4 hex chars
    (59243c97-5032-49f4-9cf9-a688f0179ff5 -> 59243c97-9ff5)."""
    return f"{uuid[:8]}-{uuid[-4:]}".lower()


def resolve_condominium(value):
    """Short id, full uuid or /condominio/...-id-<short>/ link -> the short id."""
    value = (value or "").strip()
    if SHORT_UUID_RE.match(value):
        return value.lower()
    if UUID_RE.match(value):
        return short_condominium_id(value)
    if _is_link(value):
        parsed = _parse_site_link(value, "condominium")
        match = _LINK_CONDO_RE.search(parsed.path)
        if match:
            return match.group(1).lower()
        raise ValueError("Must be a zapimoveis.com.br condominium link "
                         "(https://www.zapimoveis.com.br/condominio/<slug>-id-<short id>/).")
    raise ValueError("Must be a condominium id (59243c97-9ff5), its uuid or a "
                     "zapimoveis.com.br condominium link.")


def condominium_link(short_id, path=None):
    if path:
        return path if path.startswith("http") else SITE + path
    return f"{SITE}/condominio/condominio-id-{short_id}/"


# ---- location ------------------------------------------------------------------

# The site's ?onde= value: ",<state>,<city>,<zone>,<neighborhood>,<street>,
# <number>,<type>,<locationId>,<lat>,<lng>," (comma-separated, positional).
_ONDE_LOCATION_INDEX = 8

# Site query params a pasted search link may carry -> our filter names.
_LINK_QUERY_FILTERS = {
    "precoMinimo": "min_price", "precoMaximo": "max_price",
    "areaMinima": "min_area", "areaMaxima": "max_area",
    "quartos": "min_bedrooms", "banheiros": "min_bathrooms", "vagas": "min_parking",
    "pagina": "page",
}


def resolve_location(value):
    """Location id / search link / free text -> a descriptor dict:

        {"kind": "id",   "location_id": "BR>...", "query": None}
        {"kind": "link", "slug": "sp+sao-paulo+zona-oeste+pinheiros", "location_id": <from ?onde= or None>,
                         "filters": {business, listing_type, property_type_slug, min_bedrooms, ...}}
        {"kind": "text", "query": "Pinheiros, São Paulo"}

    Text and link slugs are turned into a location id by api.py through the
    site's autocomplete (network), never here."""
    value = (value or "").strip()
    if not value:
        raise ValueError("Must not be empty.")
    if LOCATION_ID_RE.match(value):
        return {"kind": "id", "location_id": value}
    if _is_link(value):
        parsed = _parse_site_link(value, "search")
        path = unquote(parsed.path or "/")
        match = _LINK_SEARCH_RE.match(path if path.endswith("/") else path + "/")
        if not match:
            raise ValueError("Must be a zapimoveis.com.br search link "
                             "(https://www.zapimoveis.com.br/venda/apartamentos/sp+sao-paulo/).")
        section, type_slug, slug, bedrooms = match.groups()
        query = {k: v[0] for k, v in parse_qs(parsed.query).items() if v}
        filters = {
            "business": "RENTAL" if section == "aluguel" else "SALE",
            "listing_type": "DEVELOPMENT" if section == "lancamentos" else "USED",
            "property_type": PATH_SLUG_TO_TYPE.get(type_slug) if type_slug else None,
        }
        if bedrooms:
            filters["min_bedrooms"] = int(bedrooms)
        for site_key, ours in _LINK_QUERY_FILTERS.items():
            raw = query.get(site_key)
            if raw and raw.split(",")[0].strip().isdigit():
                filters[ours] = int(raw.split(",")[0])
        if query.get("ordem"):
            filters["sort"] = SITE_SORT_LABELS.get(query["ordem"].strip().lower())
        location_id = None
        onde = query.get("onde")
        if onde:
            parts = onde.split(",")
            if len(parts) > _ONDE_LOCATION_INDEX and LOCATION_ID_RE.match(parts[_ONDE_LOCATION_INDEX].strip()):
                location_id = parts[_ONDE_LOCATION_INDEX].strip()
        return {"kind": "link", "slug": slug, "location_id": location_id,
                "filters": {k: v for k, v in filters.items() if v is not None}}
    if len(value) > 120:
        raise ValueError("Location text is too long (120 characters max).")
    return {"kind": "text", "query": value}


def location_slug_from_url(url):
    """'/venda/imoveis/rj+rio-de-janeiro+zona-sul+copacabana/' -> the
    'rj+rio-de-janeiro+zona-sul+copacabana' segment (None when absent)."""
    match = _LINK_SEARCH_RE.match(url or "")
    return match.group(3) if match else None


def search_path(slug, business="SALE", listing_type="USED", type_slug=None):
    """The site's list-page path for a location slug (the page whose server
    payload carries the price insights)."""
    section = "lancamentos" if listing_type == "DEVELOPMENT" else ("aluguel" if business == "RENTAL" else "venda")
    return f"/{section}/{type_slug or 'imoveis'}/{slug}/"


# ---- vocabulary ----------------------------------------------------------------

BUSINESS = {"sale": "SALE", "rent": "RENTAL"}
BUSINESS_LABEL = {"SALE": "sale", "RENTAL": "rent"}
LISTING_TYPE_LABEL = {"USED": "used", "DEVELOPMENT": "new_development"}

# public slug -> (unitType, unitSubTypes, usageType, unitTypeV3, site path slug, label)
# The glue request sends unitTypes / unitSubTypes ("|"-joined per type) /
# usageTypes / unitTypesV3 exactly as the site's determineUnityAttributes does.
UNIT_TYPES = {
    "apartment":           ("APARTMENT", ("UnitSubType_NONE", "DUPLEX", "TRIPLEX"), "RESIDENTIAL", "APARTMENT", "apartamentos", "Apartamento"),
    "studio":              ("APARTMENT", ("STUDIO",), "RESIDENTIAL", "STUDIO", "studio", "Studio"),
    "kitnet":              ("APARTMENT", ("KITNET",), "RESIDENTIAL", "KITNET", "quitinetes", "Kitnet"),
    "house":               ("HOME", ("UnitSubType_NONE", "SINGLE_STOREY_HOUSE", "KITNET"), "RESIDENTIAL", "HOME", "casas", "Casa"),
    "condo_house":         ("HOME", ("CONDOMINIUM",), "RESIDENTIAL", "CONDOMINIUM", "casas-de-condominio", "Casa de Condomínio"),
    "village_house":       ("HOME", ("VILLAGE_HOUSE",), "RESIDENTIAL", "VILLAGE_HOUSE", "casas-de-vila", "Casa de Vila"),
    "penthouse":           ("APARTMENT", ("PENTHOUSE",), "RESIDENTIAL", "PENTHOUSE", "cobertura", "Cobertura"),
    "flat":                ("APARTMENT", ("FLAT",), "RESIDENTIAL", "FLAT", "flat", "Flat"),
    "loft":                ("APARTMENT", ("LOFT",), "RESIDENTIAL", "LOFT", "loft", "Loft"),
    "residential_land":    ("ALLOTMENT_LAND", ("UnitSubType_NONE", "CONDOMINIUM", "VILLAGE_HOUSE"), "RESIDENTIAL", "RESIDENTIAL_ALLOTMENT_LAND", "terrenos-lotes-condominios", "Terreno / Lote / Condomínio"),
    "two_story_house":     ("HOME", ("TWO_STORY_HOUSE",), "RESIDENTIAL", "TWO_STORY_HOUSE", "sobrados", "Sobrado"),
    "farm":                ("FARM", ("UnitSubType_NONE", "CONDOMINIUM"), "RESIDENTIAL", "FARM", "fazendas-sitios-chacaras", "Fazenda / Sítio / Chácara"),
    "store":               ("BUSINESS", ("UnitSubType_NONE", "RETAIL_CENTER", "GALLERY", "SHOPPING"), "COMMERCIAL", "BUSINESS", "loja-salao", "Loja / Salão / Ponto Comercial"),
    "office":              ("OFFICE", ("UnitSubType_NONE", "CLINIC", "OFFICE"), "COMMERCIAL", "OFFICE", "conjunto-comercial-sala", "Conjunto Comercial / Sala"),
    "commercial_house":    ("HOME", ("UnitSubType_NONE",), "COMMERCIAL", "COMMERCIAL_PROPERTY", "casa-comercial", "Casa Comercial"),
    "hotel":               ("HOTEL", ("UnitSubType_NONE",), "COMMERCIAL", "HOTEL", "hoteis-moteis-pousadas", "Hotel / Motel / Pousada"),
    "commercial_floor":    ("OFFICE", ("FLOOR",), "COMMERCIAL", "FLOOR", "andares-lajes-corporativas", "Andar / Laje Corporativa"),
    "commercial_building": ("BUILDING", ("UnitSubType_NONE",), "COMMERCIAL", "COMMERCIAL_BUILDING", "predio-inteiro", "Prédio Inteiro"),
    "commercial_land":     ("ALLOTMENT_LAND", ("UnitSubType_NONE",), "COMMERCIAL", "COMMERCIAL_ALLOTMENT_LAND", "terrenos-lotes-comerciais", "Terrenos / Lotes Comerciais"),
    "warehouse":           ("SHED_DEPOSIT_WAREHOUSE", ("UnitSubType_NONE",), "COMMERCIAL", "SHED_DEPOSIT_WAREHOUSE", "galpao-deposito-armazem", "Galpão / Depósito / Armazém"),
    "parking_space":       ("PARKING_SPACE", ("UnitSubType_NONE",), "COMMERCIAL", "PARKING_SPACE", "box-garagem", "Garagem"),
}

PATH_SLUG_TO_TYPE = {spec[4]: slug for slug, spec in UNIT_TYPES.items()}

# glue (unitType, unitSubType) -> public slug, most specific first.
_SUBTYPE_TO_TYPE = {}
for _slug, _spec in UNIT_TYPES.items():
    for _sub in _spec[1]:
        _SUBTYPE_TO_TYPE.setdefault((_spec[0], _sub, _spec[2]), _slug)


def property_type_label(unit_types, unit_sub_types, usage_types):
    """The public slug for a listing's glue unitTypes / unitSubTypes /
    usageTypes (the first of each); the raw glue type lower-cased when the
    combination is not in the table."""
    unit = (unit_types or [None])[0]
    sub = (unit_sub_types or ["UnitSubType_NONE"])[0] or "UnitSubType_NONE"
    usage = (usage_types or ["RESIDENTIAL"])[0] or "RESIDENTIAL"
    if not unit:
        return None
    for key in ((unit, sub, usage), (unit, "UnitSubType_NONE", usage), (unit, sub, "RESIDENTIAL"),
                (unit, "UnitSubType_NONE", "RESIDENTIAL"), (unit, "UnitSubType_NONE", "COMMERCIAL")):
        if key in _SUBTYPE_TO_TYPE:
            return _SUBTYPE_TO_TYPE[key]
    return unit.lower()


def unit_type_params(slugs):
    """The four glue params for a list of public property-type slugs."""
    if not slugs:
        return {}
    specs = [UNIT_TYPES[s] for s in slugs if s in UNIT_TYPES]
    return {
        "unitTypes": ",".join(dict.fromkeys(spec[0] for spec in specs)),
        "unitSubTypes": "|".join(",".join(spec[1]) for spec in specs),
        "usageTypes": ",".join(dict.fromkeys(spec[2] for spec in specs)),
        "unitTypesV3": ",".join(spec[3] for spec in specs),
    }


# Sort: public value -> glue `sort` (None = the site's relevance ranking).
# Price sorts need the sortFilter for the business the user searches.
SORTS = {
    "relevance": None,
    "newest": "createdAt DESC",
    "price_asc": "pricingInfos.price ASC sortFilter:pricingInfos.businessType:'{business}'",
    "price_desc": "pricingInfos.price DESC sortFilter:pricingInfos.businessType:'{business}'",
    "area_asc": "usableAreas ASC",
    "area_desc": "usableAreas DESC",
}
# The site's own ?ordem= labels (a pasted link) -> our sort values.
SITE_SORT_LABELS = {
    "mais relevantes": "relevance", "mais recente": "newest", "menor preço": "price_asc",
    "maior preço": "price_desc", "maior área": "area_desc",
}

CONSTRUCTION_STATUS = {"planned": "PLAN_ONLY", "under_construction": "UNDER_CONSTRUCTION", "ready": "BUILT"}
CONSTRUCTION_STATUS_LABEL = {
    "PLAN_ONLY": "planned", "PRE_LAUNCH": "pre_launch", "UNDER_CONSTRUCTION": "under_construction",
    "BUILT": "ready", "ConstructionStatus_NONE": None, None: None, "": None,
}

# Glue reads bedrooms / bathrooms / parkingSpaces as a list of exact counts
# where the site's top button (4) means "4 or more": bedrooms=4 and
# bedrooms=4,5,6,7,8 answer the same 1,584 (2026-11-07), so a minimum of N is
# the list N..4.
ROOM_FILTER_CAP = 4


def min_count_param(minimum):
    if not minimum:
        return None
    minimum = min(int(minimum), ROOM_FILTER_CAP)
    return ",".join(str(n) for n in range(minimum, ROOM_FILTER_CAP + 1))


def photo_url(template, width=1920, height=1080):
    """Fill the CDN template
    .../{description}.jpg?action={action}&dimension={width}x{height}
    (any description word serves the image; verified 2026-11-07)."""
    if not template:
        return None
    return (template.replace("{description}", "imagem").replace("{action}", "fit-in")
            .replace("{width}", str(width)).replace("{height}", str(height)))
