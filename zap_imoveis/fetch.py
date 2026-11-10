"""ZAP Imóveis transport: plain curl_cffi with browser-impersonated TLS. No
browser, no login, no cookies — everything this package reads is what a
logged-out visitor gets.

Upstream surfaces (researched 2026-11-07, research note
zap-imoveis-scraper-research):

  * GLUE    https://glue-api.zapimoveis.com.br — the portal's own JSON
            backend (the same index serves VivaReal). Two headers decide
            everything: `x-domain: www.zapimoveis.com.br` is mandatory
            (400 MISSING-DOMAIN-HEADER without it) and `includeFields` is
            mandatory (400 without it).
              GET /v4/listings      search; `size` <= 30, from + size <= 1,500,
                                    pads every page to 30 rows with promoted
                                    listings (dedupe by id); categoryPage=
                                    ADVERTISER + advertiserId = one agency's
                                    listings (RESULT ignores advertiserId;
                                    `page` in includeFields 500s there)
              GET /v2/listing/<id>  one listing (+ account, medias, link);
                                    410 GONE when expired, 404 when unknown
              GET /v3/locations     autocomplete (fields=neighborhood,city,
                                    street | condominium)
  * PAGES   www.zapimoveis.com.br's Next.js pages — the data rides in the
            React Server Components payload (`self.__next_f.push` rows,
            parsers.rsc_payload): the list page (price insights block
            `averagePrice.dataZapInfo`, server-side only), the agency page
            /imobiliaria/<id>/ (rating, address, store) and the condominium
            page /condominio/<slug>-id-<short>/. Unknown ids answer HTTP 404
            with the `__next_error__` shell.

Egress (pod probe 2026-11-07 10:38 UTC, scrapers-patchright-depl-74fddd498d-rfmk6,
table in config.py's zap imoveis block): the pod's own IP is 200 on all 7
surfaces, so are 2/2 datacenter and 2/2 BR residential ports — direct tier
(config.ZAP_IMOVEIS_EXIT). Cloudflare fronts both hosts and refuses some
networks outright ("Attention Required" 1020: a Mac in India, about 2 in 3
datacenter exits), so a block drops the session and moves new sessions to
the datacenter fallback for ZAP_IMOVEIS_BLOCK_COOLDOWN seconds.

Failure taxonomy (scraper_errors, mapped to HTTP by route_glue):
  ZapImoveisUpstreamError  transport failure / 5xx / malformed payload  — retryable
  ZapImoveisBlocked        403 / 429 / Cloudflare page                   — retryable on a fresh exit
  ZapImoveisBadRequest     upstream 400                                 — never retried
  ZapImoveisNotFound       unknown / expired id, 404 shell page         — never retried
"""
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import egress
from scraper_errors import BadRequest, Blocked, NotFound, UpstreamError
from zap_imoveis.refs import GLUE, SITE, X_DOMAIN

IMPERSONATE = "chrome"
GLUE_TIMEOUT = 30
PAGE_TIMEOUT = 40     # list / agency / condo pages are 1.4-1.8 MB

_BLOCK_MARKERS = ("attention required", "just a moment", "cf-error-details", "cf-chl", "access denied")
_NOT_FOUND_SHELL = 'id="__next_error__"'


class ZapImoveisUpstreamError(UpstreamError):
    """Transport failure, 5xx or a payload we cannot read — retryable."""


class ZapImoveisBlocked(ZapImoveisUpstreamError, Blocked):
    """403 / 429 or a Cloudflare page where JSON/HTML was expected — retryable."""


class ZapImoveisBadRequest(BadRequest):
    """Upstream 400 — never retried."""


class ZapImoveisNotFound(NotFound):
    """Listing / agency / condominium / location does not exist — never retried."""


# One session per cheroot worker thread: a curl handle must not be shared
# across threads; these GETs are stateless so thread-lifetime sessions with
# keep-alive are enough. A block on the default tier starts the fallback
# cooldown for every thread (crexi/fetch.py pattern).
_local = threading.local()
_fallback_until = 0.0
_fallback_lock = threading.Lock()


def _proxy():
    proxy = config.zap_imoveis_proxy()
    if proxy is None and time.time() < _fallback_until:
        proxy = config.zap_imoveis_fallback_proxy()
    return proxy


def _session():
    sess = getattr(_local, "session", None)
    if sess is None:
        from curl_cffi import requests as curl_requests
        proxy = _proxy()
        sess = curl_requests.Session(impersonate=IMPERSONATE)
        if proxy:
            sess.proxies = {"http": proxy, "https": proxy}
        sess.headers["accept-language"] = egress.accept_language(proxy)
        _local.session = sess
    return sess


def _drop_session(blocked=False):
    """Close the thread's session (fresh exit next time); a block on the
    default tier also starts the fallback cooldown for every thread."""
    global _fallback_until
    sess = getattr(_local, "session", None)
    _local.session = None
    if sess is not None:
        try:
            sess.close()
        except Exception:
            pass
    if blocked and config.zap_imoveis_proxy() is None and config.zap_imoveis_fallback_proxy() is not None:
        with _fallback_lock:
            _fallback_until = max(_fallback_until, time.time() + config.ZAP_IMOVEIS_BLOCK_COOLDOWN)


def _retrying(fn):
    """Run fn() under the shared retry policy (ZapImoveisUpstreamError only;
    NotFound / BadRequest surface immediately)."""
    last = None
    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            return fn()
        except ZapImoveisBlocked as e:
            last = e
            _drop_session(blocked=True)
        except ZapImoveisUpstreamError as e:
            last = e
            _drop_session()
        if attempt < config.MAX_RETRIES:
            time.sleep(config.RETRY_BACKOFF * attempt)
    raise last


def _looks_blocked(text):
    head = (text or "")[:4000].lower()
    return any(marker in head for marker in _BLOCK_MARKERS)


def _classify(resp, label):
    """Map an HTTP status to the error taxonomy (200 falls through)."""
    status = resp.status_code
    if status in (404, 410):
        raise ZapImoveisNotFound(f"{label} not found")
    if status == 400:
        raise ZapImoveisBadRequest(f"upstream rejected {label}: {resp.text[:160]}")
    if status in (401, 403, 429):
        raise ZapImoveisBlocked(f"HTTP {status} for {label}")
    if status != 200:
        raise ZapImoveisUpstreamError(f"HTTP {status} for {label}")


# ---- glue -----------------------------------------------------------------------

def glue_get(path, params, label):
    """GET a glue route -> the JSON dict."""
    headers = {"x-domain": X_DOMAIN, "accept": "application/json",
               "origin": SITE, "referer": SITE + "/"}

    def once():
        try:
            resp = _session().get(GLUE + path, params=params, headers=headers, timeout=GLUE_TIMEOUT)
        except Exception as e:
            raise ZapImoveisUpstreamError(f"request failed: {type(e).__name__}: {e}")
        if resp.status_code != 200 and _looks_blocked(resp.text):
            raise ZapImoveisBlocked(f"Cloudflare page for {label} (HTTP {resp.status_code})")
        _classify(resp, label)
        try:
            payload = resp.json()
        except Exception:
            if _looks_blocked(resp.text):
                raise ZapImoveisBlocked(f"Cloudflare page for {label}")
            raise ZapImoveisUpstreamError(f"non-JSON glue response for {label}: {resp.text[:120]}")
        if not isinstance(payload, dict):
            raise ZapImoveisUpstreamError(f"unexpected glue payload for {label}")
        if "err" in payload and len(payload) == 1:
            raise ZapImoveisUpstreamError(f"glue error for {label}: {str(payload['err'])[:160]}")
        return payload
    return _retrying(once)


SEARCH_FIELDS = ("search(result(listings(listing,account,medias,accountLink,link,"
                 "children(id,usableAreas,totalAreas,bedrooms,bathrooms,parkingSpaces,pricingInfos))),"
                 "totalCount)")
LISTING_FIELDS = "listing,account,medias,link,accountLink"
ACCOUNT_FIELDS = ("search(totalCount),account(config,id,name,logoUrl,licenseNumber,websiteUrl,showAddress,"
                  "legacyVivarealId,legacyZapId,createdDate,phones(primary,mobile),trustScore,tier,"
                  "addresses(billing(city,street,streetNumber,zipCode,neighborhood,state,stateAcronym,"
                  "locationId,zone)))")
LOCATION_FIELDS = "address,url"
CONDOMINIUM_FIELDS = "condominium,address,url"


def fetch_search(params, label="search"):
    """GET /v4/listings for an encoded filter set (api._glue_search_params);
    `page(uriPagination)` and `facets` ride along on RESULT searches."""
    query = dict(params)
    query.setdefault("categoryPage", "RESULT")
    fields = SEARCH_FIELDS
    if query["categoryPage"] == "RESULT":
        fields += ",page(uriPagination)"
    query["includeFields"] = fields
    return glue_get("/v4/listings", query, label)


def fetch_count(params, label="count"):
    """GET /v4/listings with only the total and the amenity facets."""
    query = dict(params, size=1)
    query["from"] = 0
    query.setdefault("categoryPage", "RESULT")
    query["includeFields"] = "search(totalCount),facets"
    return glue_get("/v4/listings", query, label)


def fetch_listing(listing_id):
    """GET /v2/listing/<id> -> {listing, account, medias, link, accountLink}."""
    return glue_get(f"/v2/listing/{listing_id}", {"includeFields": LISTING_FIELDS}, f"listing {listing_id}")


def fetch_account(advertiser_id):
    """GET the advertiser's account record (rides the search route: the
    `account` include answers the profile when advertiserId is set).
    An unknown uuid is a glue 404."""
    params = {"categoryPage": "RESULT", "advertiserId": advertiser_id, "size": 1, "from": 0,
              "includeFields": ACCOUNT_FIELDS}
    return glue_get("/v4/listings", params, f"advertiser {advertiser_id}")


def fetch_locations(query, fields="neighborhood,city,street", size=10):
    """GET /v3/locations autocomplete -> {<field>: {totalCount, result: {locations}}}."""
    params = {"q": query, "portal": "ZAP", "size": size, "fields": fields,
              "includeFields": CONDOMINIUM_FIELDS if fields == "condominium" else LOCATION_FIELDS}
    return glue_get("/v3/locations", params, f"locations {query!r}")


# ---- site pages ------------------------------------------------------------------

def _page(path, label):
    headers = {"accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
                          "image/avif,image/webp,*/*;q=0.8"),
               "upgrade-insecure-requests": "1"}

    def once():
        try:
            resp = _session().get(SITE + path, headers=headers, timeout=PAGE_TIMEOUT, allow_redirects=True)
        except Exception as e:
            raise ZapImoveisUpstreamError(f"request failed: {type(e).__name__}: {e}")
        text = resp.text
        if resp.status_code != 200 and _looks_blocked(text):
            raise ZapImoveisBlocked(f"Cloudflare page for {label} (HTTP {resp.status_code})")
        _classify(resp, label)
        if _looks_blocked(text) and "self.__next_f" not in text:
            raise ZapImoveisBlocked(f"Cloudflare page for {label}")
        if _NOT_FOUND_SHELL in text[:2000]:
            raise ZapImoveisNotFound(f"{label} not found")
        if "self.__next_f" not in text:
            raise ZapImoveisUpstreamError(f"unexpected page for {label} (no server payload)")
        return text
    return _retrying(once)


def fetch_list_page(path):
    """GET a search list page (/venda/<tipo>/<slug>/) for its server payload."""
    return _page(path, f"list page {path}")


def fetch_agency_page(page_id, page=1):
    """GET /imobiliaria/<id>/ (the agency's own page)."""
    path = f"/imobiliaria/{page_id}/" + (f"?pagina={page}" if page > 1 else "")
    return _page(path, f"agency {page_id}")


def fetch_condominium_page(short_id):
    """GET /condominio/<any slug>-id-<short>/ (302s to the canonical slug;
    the slug must be present — /condominio/id-<short>/ alone is a 404)."""
    return _page(f"/condominio/condominio-id-{short_id}/", f"condominium {short_id}")
