"""Offline tests for the ZAP Imóveis parsers and the endpoint glue in api.py
(location resolution, filter encoding, the merged agency record), with the
network replaced by the captured fixtures.

    python -m pytest zap_imoveis/test_parsers.py -q

Fixtures are real glue payloads / site pages captured 2026-11-07
(zap_imoveis/fixtures/, listed in parsers.py's docstring). No network.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scraper_errors import NotFound  # noqa: E402
from zap_imoveis import api, parsers as P, refs  # noqa: E402

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
PINHEIROS = "BR>Sao Paulo>NULL>Sao Paulo>Zona Oeste>Pinheiros"
MARCOS = "1b5a8b4c-5ae5-4adb-00df-bad221af754c"


def fixture(name):
    with open(os.path.join(FX, name), encoding="utf-8") as f:
        return json.load(f) if name.endswith(".json") else f.read()


@pytest.fixture(scope="module")
def sale():
    return P.parse_search(fixture("search_sale_pinheiros.json"), "SALE")


@pytest.fixture(scope="module")
def rent():
    return P.parse_search(fixture("search_rent_pinheiros_filtered.json"), "RENTAL")


@pytest.fixture(scope="module")
def developments():
    return P.parse_search(fixture("search_developments_sp.json"), "SALE")


@pytest.fixture(scope="module")
def detail():
    return P.parse_listing_detail(fixture("listing_used_2886301373.json"), "SALE")


# ---- value helpers ------------------------------------------------------------------

def test_num_and_money():
    assert P._num("400000") == 400000 and P._num(400000) == 400000 and P._num("3.5") == 3.5
    assert P._num("") is None and P._num(None) is None and P._num("abc") is None and P._num(True) is None
    assert P._money(0) is None and P._money("0") is None and P._money("702") == 702


def test_range_and_iso():
    assert P._range([30, 56]) == {"min": 30, "max": 56}
    assert P._range(["35"]) is None and P._range([2, 2]) is None and P._range(None) is None
    assert P._iso("2026-05-13T03:51:05.042Z") == "2026-05-13T03:51:05Z"
    assert P._iso("2023-09-13T18:54:27Z") == "2023-09-13T18:54:27Z"
    assert P._iso("") is None


def test_clean_nulls_rsc_placeholders():
    assert P._clean({"a": "$undefined", "b": ["$3c", "text"], "c": {"d": "$5:props"}}) == \
        {"a": None, "b": [None, "text"], "c": {"d": None}}


# ---- search -----------------------------------------------------------------------------

def test_parse_search_sale(sale):
    assert sale["total_count"] == 23725
    assert sale["page_total"] == 23725
    assert len(sale["results"]) == 30
    assert len({r["id"] for r in sale["results"]}) == 30
    assert sale["facets"]["ELEVATOR"] == 12077
    first = sale["results"][0]
    assert first["id"] == "2919742080"
    assert first["link"].startswith("https://www.zapimoveis.com.br/imovel/venda-sobrados-4-quartos")
    assert first["business"] == "sale" and first["listing_type"] == "used"
    assert first["property_type"] == "two_story_house" and first["usage"] == "residential"
    assert first["pricing"] == {"business": "sale", "price": 13995000, "currency": "BRL", "condo_fee_monthly": None,
                                "iptu": 3000, "iptu_period": "yearly", "rent_total_monthly": None,
                                "rent_period": None, "warranties": None}
    assert first["other_pricing"] is None
    assert first["price_per_m2"] == 19171.23
    assert (first["bedrooms"], first["bathrooms"], first["suites"], first["parking_spaces"]) == (4, 6, 4, 5)
    assert first["usable_area_m2"] == 730 and first["total_area_m2"] == 680
    assert first["address"]["neighborhood"] == "Vila Madalena"
    assert first["address"]["coordinates"] == {"latitude": -23.560394, "longitude": -46.693716}
    assert first["address"]["location_id"] == PINHEIROS
    assert first["photo_count"] == 20
    assert first["photos"][0].endswith("/imagem.jpg?action=fit-in&dimension=1920x1080")
    assert first["advertiser"]["name"] == "Marcio de Paula Pinto"
    assert first["advertiser"]["link"] == "https://www.zapimoveis.com.br/imobiliaria/299039/"
    assert first["advertiser"]["license_number"] == "205467"
    assert first["advertiser"]["phones"] == ["11944493237"] and first["advertiser"]["whatsapp"] == "11944493237"
    assert first["advertiser"]["type"] == "agency"
    assert first["portals"] == ["olx", "vivareal", "zap"]
    assert first["quality_score"] == 93
    assert first["created_at"] == "2026-10-28T15:20:17Z"
    assert first["is_below_market"] is False and first["construction"] is None and first["units"] is None


def test_search_has_no_empty_strings_or_missing_keys(sale):
    keys = {k for r in sale["results"] for k in r}
    for record in sale["results"]:
        assert set(record) == keys

    def walk(value):
        if isinstance(value, dict):
            for v in value.values():
                walk(v)
        elif isinstance(value, list):
            for v in value:
                walk(v)
        else:
            assert value != "" and value != "N/A" and not (isinstance(value, str) and value.startswith("$"))
    walk(sale["results"])


def test_search_both_businesses_and_videos(sale):
    both = [r for r in sale["results"] if r["other_pricing"]]
    assert both, "the page carries ads listed for sale and rent"
    assert both[0]["pricing"]["business"] == "sale" and both[0]["other_pricing"][0]["business"] == "rent"
    assert any(r["videos"] for r in sale["results"])
    assert any(r["virtual_tours"] and r["has_virtual_tour"] for r in sale["results"])


def test_parse_search_rent(rent):
    assert rent["total_count"] == 455
    first = rent["results"][0]
    assert first["pricing"]["business"] == "rent"
    assert first["pricing"]["price"] == 2000
    assert first["pricing"]["condo_fee_monthly"] == 720
    assert first["pricing"]["rent_total_monthly"] == 2720 and first["pricing"]["rent_period"] == "monthly"
    assert first["pricing"]["iptu"] is None     # 0 = not informed
    assert all(r["bedrooms"] == 2 for r in rent["results"])
    assert all(r["pricing"]["price"] <= 6000 for r in rent["results"])


def test_parse_search_developments(developments):
    assert developments["total_count"] == 996
    first = developments["results"][0]
    assert first["listing_type"] == "new_development"
    assert first["construction"]["status"] == "ready"
    assert first["construction"]["developer"]["name"] == "VIVAZ RESIDENCIAL"
    assert first["construction"]["timeline"][0] == {"date": "2022-07", "status": "pre_launch"}
    assert first["unit_ranges"]["usable_area_m2"] == {"min": 30, "max": 56}
    assert first["unit_ranges"]["bedrooms"] == {"min": 1, "max": 3}
    assert first["units"][0] == {"id": "2869116981", "price": 265200, "currency": "BRL", "usable_area_m2": 30,
                                 "total_area_m2": 45, "bedrooms": 1, "bathrooms": 1, "parking_spaces": 0}
    assert first["condominium_name"] == "VIVAZ PRIME VILA PRUDENTE"
    assert any(r["floor_plans"] for r in developments["results"])


def test_parse_search_empty_and_sparse():
    assert P.parse_search(fixture("search_empty.json")) == {"total_count": 0, "page_total": 0, "results": [],
                                                           "facets": None}
    assert P.parse_search({})["results"] == []
    assert P.parse_search(None)["total_count"] is None
    sparse = P.parse_listing({"listing": {"id": "1"}})
    assert sparse["id"] == "1" and sparse["link"] == "https://www.zapimoveis.com.br/imovel/id-1/"
    assert sparse["pricing"] is None and sparse["photos"] is None and sparse["advertiser"]["id"] is None


def test_parse_facets():
    facets = P.parse_facets(fixture("count_sale_pinheiros.json"))
    assert list(facets)[:2] == ["ELEVATOR", "POOL"] and facets["POOL"] == 10716


# ---- listing detail -----------------------------------------------------------------------

def test_parse_listing_detail(detail):
    assert detail["id"] == "2886301373"
    assert detail["title"].startswith("Apartamento à venda, 35 m²")
    assert detail["description"].startswith("Studio 35m2")
    assert detail["pricing"] == {"business": "sale", "price": 400000, "currency": "BRL", "condo_fee_monthly": 702,
                                 "iptu": 122, "iptu_period": "monthly", "rent_total_monthly": None,
                                 "rent_period": None, "warranties": None}
    assert detail["price_per_m2"] == 11428.57
    assert detail["property_type"] == "apartment"
    assert detail["address"]["street"] == "Rua Santo Antônio" and detail["address"]["number"] == "722"
    assert detail["address"]["zip_code"] == "01314000" and detail["address"]["zone"] == "Centro"
    assert detail["photo_count"] == 51 and detail["videos"] == ["https://youtu.be/sgj8z4LXucA"]
    assert detail["advertiser"]["website"] == "http://www.marcospimenta.com.br/"
    assert detail["advertiser"]["link"] == "https://www.zapimoveis.com.br/imobiliaria/814814/"
    assert detail["advertiser"]["phones"] == ["1142103280", "11996559346"]
    assert detail["advertiser"]["is_verified"] is True and detail["advertiser"]["tier"] == "diamond"
    assert detail["nearby_transport"]["within_1km"] == ["Metrô Anhangabaú", "Metrô Higienópolis Mackenzie",
                                                        "Metrô República"]
    assert detail["points_of_interest"][0] == {"type": "bus_stop", "name": "Inss B/C"}
    assert detail["is_below_market"] is True
    assert "GYM" in detail["amenities"]
    assert detail["construction"]["delivered_at"] == "2015-11-07T03:51:00Z"
    assert detail["updated_at"] == "2026-11-07T03:52:30Z"


def test_parse_listing_detail_development():
    record = P.parse_listing_detail(fixture("listing_development_2852736120.json"))
    assert record["title"] == "MUNDO APTO MOOCA"
    assert record["listing_type"] == "new_development"
    assert record["construction"]["status"] == "under_construction"
    assert record["construction"]["developer"]["name"] == "MUNDO APTO"
    assert record["construction"]["timeline"][-1] == {"date": "2026-12", "status": "ready"}
    assert record["unit_ranges"]["usable_area_m2"] == {"min": 24, "max": 51}
    assert record["pricing"]["price"] == 358070 and record["other_pricing"][0]["price"] == 366558
    assert record["advertiser"]["type"] == "developer"


# ---- locations ----------------------------------------------------------------------------

def test_parse_locations():
    hits = P.parse_locations(fixture("locations_pinheiros.json"))
    assert hits[0]["type"] == "neighborhood" and hits[0]["name"] == "Pinheiros"
    assert hits[0]["location_id"] == PINHEIROS
    assert hits[0]["slug"] == "sp+sao-paulo+zona-oeste+pinheiros"
    assert hits[0]["link"] == "https://www.zapimoveis.com.br/venda/imoveis/sp+sao-paulo+zona-oeste+pinheiros/"
    assert hits[0]["coordinates"] == {"latitude": -23.563579, "longitude": -46.691607}
    assert len({(h["type"], h["location_id"], h["street"]) for h in hits}) == len(hits)
    streets = [h for h in hits if h["type"] == "street"]
    assert streets and streets[0]["street"] == "Rua dos Pinheiros"
    assert P.parse_locations(fixture("locations_nomatch.json")) == []
    assert P.parse_locations(None) == []


def test_parse_condominium_suggestions():
    condos = P.parse_condominium_suggestions(fixture("condominiums_edificio_brasil.json"))
    assert condos[0]["id"] == "59243c97-5032-49f4-9cf9-a688f0179ff5"
    assert condos[0]["short_id"] == "59243c97-9ff5" and condos[0]["name"] == "Edificio Brasil"
    assert condos[0]["address"]["neighborhood"] == "Bela Vista"
    assert condos[0]["link"] == ("https://www.zapimoveis.com.br/condominio/"
                                 "sp-sao-paulo-bela-vista-edificio-brasil-id-59243c97-9ff5/")
    assert len({c["id"] for c in condos}) == len(condos)
    assert P.parse_condominium_suggestions({}) == []


# ---- agency ----------------------------------------------------------------------------------

def test_parse_account():
    account = P.parse_account(fixture("account_marcos_pimenta.json"))
    assert account["id"] == MARCOS and account["page_id"] == "814814"
    assert account["link"] == "https://www.zapimoveis.com.br/imobiliaria/814814/"
    assert account["website"] == "http://www.marcospimenta.com.br/"
    assert account["phones"] == ["1142103280", "11996559346"]
    assert account["license_number"] is None and account["is_verified"] is True
    assert P.parse_account(fixture("account_unknown.json")) is None


def test_parse_agency_page():
    agency = P.parse_agency_page(fixture("agency_page_814814.html"))
    assert agency["id"] == MARCOS and agency["name"] == "Marcos Pimenta Imoveis"
    assert agency["rating"] == {"score": 4, "ratings_count": 14, "feedback_count": 50}
    assert agency["address"]["street"] == "Rua Santa Branca" and agency["address"]["zip_code"] == "01331040"
    assert agency["listings_count"] == 1528
    assert agency["store"]["stamps"] == ["quality"]
    assert agency["phones"] == ["1142103280", "11996559346"]
    assert P.parse_agency_page(fixture("agency_page_unknown.html")) is None
    assert P.parse_agency_page("") is None


def test_parse_company_properties_are_the_advertisers():
    parsed = P.parse_search(fixture("company_properties_marcos_pimenta.json"), "SALE")
    assert parsed["total_count"] == 1299
    assert {r["advertiser"]["id"] for r in parsed["results"]} == {MARCOS}


# ---- insights / condominium pages ---------------------------------------------------------

def test_parse_insights():
    insights = P.parse_insights(fixture("list_page_sale_sao_paulo.html"))
    assert insights["name"] == "São Paulo" and insights["business"] == "sale"
    assert insights["stats"] == {"listings_count": 854298, "average_price": 952549, "average_area_m2": 114,
                                 "average_price_per_m2": 8374, "currency": "BRL"}
    assert insights["price_ranges"][0] == {"label": "Até R$ 300 mil", "listings_count": 42073,
                                           "link": "https://www.zapimoveis.com.br/venda/imoveis/sp+sao-paulo/?precoMaximo=300000"}
    assert len(insights["price_ranges"]) == 5
    assert insights["about"]["mobility"].startswith("Extensa rede")
    assert insights["top_locations"][0]["name"] == "Brooklin"
    assert insights["top_locations"][0]["stats"]["average_price_per_m2"] == 13176
    assert P.parse_insights(fixture("list_page_unknown.html")) is None
    assert P.parse_insights("<html></html>") is None


def test_parse_condominium_page():
    condo = P.parse_condominium_page(fixture("condominium_page_edificio_brasil.html"))
    assert condo["id"] == "59243c97-5032-49f4-9cf9-a688f0179ff5" and condo["short_id"] == "59243c97-9ff5"
    assert condo["name"] == "Edificio Brasil"
    assert condo["link"] == ("https://www.zapimoveis.com.br/condominio/"
                             "sp-sao-paulo-bela-vista-edificio-brasil-id-59243c97-9ff5/")
    assert condo["address"]["coordinates"] == {"latitude": -23.551702, "longitude": -46.64531}
    assert condo["area_m2"] == {"min": 34, "max": 139}
    assert condo["sale_price_from"] == 250000 and condo["rent_price_from"] == 2200
    assert "POOL" in condo["amenities"]
    assert condo["listings_count"] == 86 and len(condo["listings"]) == 5
    assert condo["listings"][0]["id"] == "2916510945" and condo["listings"][0]["pricing"]["price"] == 250000
    assert P.parse_condominium_page(fixture("condominium_page_unknown.html")) is None


def test_rsc_object_picks_the_matching_occurrence():
    text = 'x "k":{"a":1} y "k":{"a":2,"flag":true}'
    assert P.rsc_object(text, '"k":') == {"a": 1}
    assert P.rsc_object(text, '"k":', lambda o: o.get("flag")) == {"a": 2, "flag": True}
    assert P.rsc_object(text, '"missing":') is None


# ---- api glue (network replaced by fixtures) ---------------------------------------------

@pytest.fixture
def offline(monkeypatch):
    """Route every fetch to a fixture and bypass the cache."""
    calls = []

    def fake_locations(query, fields="neighborhood,city,street", size=10):
        calls.append(("locations", query, fields))
        if fields == "condominium":
            return fixture("condominiums_edificio_brasil.json")
        if "pinheiros" in query.lower():
            return fixture("locations_pinheiros.json")
        if "paulo" in query.lower():
            return fixture("locations_sao_paulo_city.json")
        return fixture("locations_nomatch.json")

    def fake_search(params, label="search"):
        calls.append(("search", dict(params)))
        if params.get("categoryPage") == "ADVERTISER":
            return fixture("company_properties_marcos_pimenta.json")
        if params.get("listingType") == "DEVELOPMENT":
            return fixture("search_developments_sp.json")
        if params.get("business") == "RENTAL":
            return fixture("search_rent_pinheiros_filtered.json")
        return fixture("search_sale_pinheiros.json")

    def fake_account(advertiser_id):
        calls.append(("account", advertiser_id))
        if advertiser_id == MARCOS:
            return fixture("account_marcos_pimenta.json")
        raise api.ZapImoveisNotFound("advertiser not found")

    def fake_agency_page(page_id, page=1):
        calls.append(("agency_page", page_id))
        if page_id == "814814":
            return fixture("agency_page_814814.html")
        raise api.ZapImoveisNotFound("agency not found")

    monkeypatch.setattr(api, "fetch_locations", fake_locations)
    monkeypatch.setattr(api, "fetch_search", fake_search)
    monkeypatch.setattr(api, "fetch_count", lambda params, label="count": fixture("count_sale_pinheiros.json"))
    monkeypatch.setattr(api, "fetch_listing", lambda listing_id: fixture("listing_used_2886301373.json"))
    monkeypatch.setattr(api, "fetch_account", fake_account)
    monkeypatch.setattr(api, "fetch_agency_page", fake_agency_page)
    monkeypatch.setattr(api, "fetch_list_page", lambda path: fixture("list_page_sale_sao_paulo.html"))
    monkeypatch.setattr(api, "fetch_condominium_page",
                        lambda short_id: fixture("condominium_page_edificio_brasil.html"))
    monkeypatch.setattr(api, "cached_call", lambda ns, data, fn, ttl, **kw: fn(**data))
    return calls


def test_resolve_location_text_prefers_the_neighbourhood_in_the_named_city(offline):
    resolved = api.resolve_location(refs.resolve_location("Pinheiros, São Paulo"))
    assert resolved["location_id"] == PINHEIROS and resolved["slug"] == "sp+sao-paulo+zona-oeste+pinheiros"
    assert resolved["type"] == "neighborhood"


def test_resolve_location_text_bare_city(offline):
    resolved = api.resolve_location(refs.resolve_location("São Paulo"))
    assert resolved["location_id"] == "BR>Sao Paulo>NULL>Sao Paulo" and resolved["type"] == "city"


def _hit(kind, name, city, state_code, score):
    return {"type": kind, "name": name, "neighborhood": name if kind == "neighborhood" else None, "zone": None,
            "city": city, "state": None, "state_code": state_code, "street": None, "score": score,
            "location_id": f"{kind}:{name}:{city}", "slug": None}


def test_pick_by_text_rules():
    # a bare "São Paulo": the BH neighbourhood edges the SP city 5.44 to 5.42 -> still the city
    hits = [_hit("neighborhood", "São Paulo", "Belo Horizonte", "MG", 5.44),
            _hit("neighborhood", "São Paulo", "Marília", "SP", 4.71),
            _hit("city", "São Paulo", "São Paulo", "SP", 5.42),
            _hit("city", "São Paulo do Potengi", "São Paulo do Potengi", "RN", 0.0),
            _hit("street", "São Paulo", "São Paulo", "SP", 0.0)]
    assert api._pick_by_text(hits, "São Paulo")["location_id"] == "city:São Paulo:São Paulo"
    # the scoped form picks the neighbourhood in that city
    assert api._pick_by_text(hits, "Sao Paulo, Belo Horizonte")["location_id"] == "neighborhood:São Paulo:Belo Horizonte"
    # "Pinheiros": the SP neighbourhood (9.4) beats the ES town (2.84)
    hits = [_hit("neighborhood", "Pinheiros", "São Paulo", "SP", 9.4),
            _hit("neighborhood", "Pinheiros", "Londrina", "PR", 4.0),
            _hit("city", "Pinheiros", "Pinheiros", "ES", 2.84)]
    assert api._pick_by_text(hits, "pinheiros")["location_id"] == "neighborhood:Pinheiros:São Paulo"
    assert api._pick_by_text(hits, "Pinheiros, PR")["location_id"] == "neighborhood:Pinheiros:Londrina"
    assert api._pick_by_text(hits, "Pinheiros, ES")["location_id"] == "city:Pinheiros:Pinheiros"
    # "Curitiba": only the city carries the name
    hits = [_hit("neighborhood", "Centro", "Curitiba", "PR", 0.0), _hit("city", "Curitiba", "Curitiba", "PR", 7.9)]
    assert api._pick_by_text(hits, "Curitiba")["type"] == "city"
    # streets only when nothing else matched
    assert api._pick_by_text([_hit("street", "Rua X", "Y", "SP", 0.0)], "Rua X")["type"] == "street"
    assert api._pick_by_text([], "x") is None


def test_resolve_location_text_unknown_is_404(offline):
    with pytest.raises(NotFound):
        api.resolve_location(refs.resolve_location("Xqzvbnmlk"))


def test_resolve_location_link_slug(offline):
    resolved = api.resolve_location(refs.resolve_location(
        "https://www.zapimoveis.com.br/aluguel/apartamentos/sp+sao-paulo+zona-oeste+pinheiros/?precoMaximo=6000"))
    assert resolved["location_id"] == PINHEIROS
    assert resolved["filters"] == {"business": "RENTAL", "listing_type": "USED", "property_type": "apartment",
                                   "max_price": 6000}


def test_resolve_location_id_finds_its_slug(offline):
    resolved = api.resolve_location(refs.resolve_location(PINHEIROS))
    assert resolved["slug"] == "sp+sao-paulo+zona-oeste+pinheiros" and resolved["name"] == "Pinheiros"


def test_glue_search_params_encode_like_the_site():
    params = api._glue_search_params(PINHEIROS, "RENTAL", "USED", 3, sort="price_asc", property_type=["apartment"],
                                     min_bedrooms=2, min_price=1000, max_price=6000.5, min_area=50,
                                     amenities=["POOL"], below_market=True, no_guarantor=True, near_transit=True,
                                     virtual_tour=True, min_condo_fee=100)
    assert params["from"] == 60 and params["size"] == 30
    assert params["bedrooms"] == "2,3,4"
    assert params["priceMin"] == 1000 and params["priceMax"] == 6000.5 and params["usableAreasMin"] == 50
    assert params["priceMinCondo"] == 100 and "priceMaxCondo" not in params
    assert params["amenities"] == "POOL"
    assert params["stamps"] == "DATAZAP_APPROVED_RENTAL" and params["warranties"] == "zapway"
    assert params["transportNearBy"] == 2 and params["hasVirtualTour"] == "true"
    assert params["unitTypes"] == "APARTMENT" and params["unitTypesV3"] == "APARTMENT"
    assert params["sort"] == "pricingInfos.price ASC sortFilter:pricingInfos.businessType:'RENTAL'"
    relevance = api._glue_search_params(PINHEIROS, "SALE", "USED", 1)
    assert "sort" not in relevance and "warranties" not in relevance and "stamps" not in relevance
    assert api._glue_search_params(PINHEIROS, "SALE", "USED", 1, no_guarantor=True).get("warranties") is None


def test_properties_search_end_to_end(offline):
    out = api.properties_search(location=refs.resolve_location("Pinheiros, São Paulo"), business="SALE",
                                sort="relevance", page=2, property_type=None, min_bedrooms=None,
                                min_bathrooms=None, min_parking=None, min_price=None, max_price=None,
                                min_area=None, max_area=None, min_condo_fee=None, max_condo_fee=None,
                                amenities=None, below_market=None, no_guarantor=None, near_transit=None,
                                virtual_tour=None)
    assert out["location"]["location_id"] == PINHEIROS
    assert out["location"]["link"] == "https://www.zapimoveis.com.br/venda/imoveis/sp+sao-paulo+zona-oeste+pinheiros/"
    assert out["business"] == "sale" and out["listing_type"] == "used"
    assert len(out["results"]) == 30
    assert out["pagination"] == {"page": 2, "items_per_page": 30, "total_pages": 50, "total_count": 23725}
    search_call = next(c for c in offline if c[0] == "search")[1]
    assert search_call["from"] == 30 and search_call["addressLocationId"] == PINHEIROS


def test_properties_search_link_fills_unset_filters(offline):
    link = "https://www.zapimoveis.com.br/aluguel/apartamentos/sp+sao-paulo+zona-oeste+pinheiros/2-quartos/?precoMaximo=6000"
    out = api.properties_search(location=refs.resolve_location(link), business="RENTAL", sort="relevance", page=1,
                                property_type=None, min_bedrooms=None, min_bathrooms=None, min_parking=None,
                                min_price=None, max_price=None, min_area=None, max_area=None, min_condo_fee=None,
                                max_condo_fee=None, amenities=None, below_market=None, no_guarantor=None,
                                near_transit=None, virtual_tour=None)
    assert out["filters"]["property_type"] == ["apartment"]
    assert out["filters"]["min_bedrooms"] == 2 and out["filters"]["max_price"] == 6000
    search_call = next(c for c in offline if c[0] == "search")[1]
    assert search_call["bedrooms"] == "2,3,4" and search_call["priceMax"] == 6000
    assert out["pagination"]["total_pages"] == 16     # ceil(455 / 30)


def test_properties_count(offline):
    out = api.properties_count(location=refs.resolve_location(PINHEIROS), business="SALE", property_type=None,
                               min_bedrooms=None, min_bathrooms=None, min_parking=None, min_price=None,
                               max_price=None, min_area=None, max_area=None, min_condo_fee=None,
                               max_condo_fee=None, amenities=None, below_market=None, no_guarantor=None,
                               near_transit=None, virtual_tour=None)
    assert out["total_count"] == 23724 and out["pages_available"] == 50
    assert list(out["amenities"])[0] == "ELEVATOR"


def test_company_record_from_page_id_and_from_uuid(offline):
    by_page = api._company_record("814814")
    assert by_page["id"] == MARCOS and by_page["page_id"] == "814814"
    assert by_page["website"] == "http://www.marcospimenta.com.br/"
    assert by_page["rating"]["score"] == 4 and by_page["listings_count"] == 1528
    assert by_page["address"]["street"] == "Rua Santa Branca"
    assert by_page["tier"] == "diamond"
    by_uuid = api._company_record(MARCOS)
    assert by_uuid == by_page
    with pytest.raises(NotFound):
        api._company_record("999999999")
    with pytest.raises(NotFound):
        api._company_record("00000000-0000-0000-0000-000000000000")


def test_companies_properties(offline):
    out = api.companies_properties(company="814814", business="SALE", page=1)
    assert out["company"]["id"] == MARCOS and out["company"]["link"].endswith("/imobiliaria/814814/")
    assert len(out["results"]) == 30
    assert out["pagination"]["total_count"] == 1299 and out["pagination"]["total_pages"] == 44
    search_call = next(c for c in offline if c[0] == "search")[1]
    assert search_call["categoryPage"] == "ADVERTISER" and search_call["advertiserId"] == MARCOS


def test_locations_insights(offline):
    out = api.locations_insights(location=refs.resolve_location("São Paulo"), business="SALE", property_type=None)
    assert out["source_link"] == "https://www.zapimoveis.com.br/venda/imoveis/sp+sao-paulo/"
    assert out["stats"]["average_price_per_m2"] == 8374
    assert out["top_locations"][0]["name"] == "Brooklin"


def test_condominiums(offline):
    out = api.condominiums_search(query="edificio brasil", limit=10)
    assert out["count"] == 6 and out["results"][0]["short_id"] == "59243c97-9ff5"
    details = api.condominiums_details(condominium="59243c97-9ff5")
    assert details["name"] == "Edificio Brasil" and len(details["listings"]) == 5


def test_properties_details(offline):
    out = api.properties_details(property="2886301373")
    assert out["id"] == "2886301373" and out["nearby_transport"]["within_1km"]
