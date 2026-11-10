"""Offline tests for the /zap-imoveis/* request schemas and reference
resolvers.

    python -m pytest zap_imoveis/test_schemas.py -q
"""
import os
import sys

import pytest
from marshmallow import ValidationError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zap_imoveis import refs, schemas  # noqa: E402

PINHEIROS = "BR>Sao Paulo>NULL>Sao Paulo>Zona Oeste>Pinheiros"


# ---- property -----------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("2886301373", "2886301373"),
    (" 2886301373 ", "2886301373"),
    ("https://www.zapimoveis.com.br/imovel/venda-apartamento-1-quarto-bela-vista-sp-35m2-id-2886301373/", "2886301373"),
    ("https://www.zapimoveis.com.br/imovel/id-2886301373/?x=1", "2886301373"),
    ("https://www.zapimoveis.com.br/lancamentos/mundo-apto-mooca-id-2852736120/", "2852736120"),
    ("https://www.vivareal.com.br/imovel/apartamento-1-quartos-bela-vista-id-2886301373/", "2886301373"),
])
def test_resolve_property(value, expected):
    assert refs.resolve_property(value) == expected
    assert schemas.PropertySchema().load({"property": value}) == {"property": expected}


@pytest.mark.parametrize("value", ["", "abc", "12", "https://example.com/imovel/x-id-2886301373/",
                                   "https://www.zapimoveis.com.br/venda/imoveis/sp+sao-paulo/"])
def test_resolve_property_invalid(value):
    with pytest.raises(ValueError):
        refs.resolve_property(value)
    with pytest.raises(ValidationError):
        schemas.PropertySchema().load({"property": value})


def test_property_schema_rejects_sibling_params():
    with pytest.raises(ValidationError):
        schemas.PropertySchema().load({"property": "2886301373", "id": "2886301373"})


# ---- company ------------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("814814", "814814"),
    ("https://www.zapimoveis.com.br/imobiliaria/814814/", "814814"),
    ("https://www.zapimoveis.com.br/imobiliaria/814814/?pagina=2&transacao=venda", "814814"),
    ("1B5A8B4C-5AE5-4ADB-00DF-BAD221AF754C", "1b5a8b4c-5ae5-4adb-00df-bad221af754c"),
])
def test_resolve_company(value, expected):
    assert refs.resolve_company(value) == expected
    assert schemas.CompanySchema().load({"company": value}) == {"company": expected}


@pytest.mark.parametrize("value", ["", "marcos pimenta", "https://www.zapimoveis.com.br/imovel/x-id-2886301373/",
                                   "https://example.com/imobiliaria/814814/"])
def test_resolve_company_invalid(value):
    with pytest.raises(ValueError):
        refs.resolve_company(value)


def test_company_properties_schema():
    loaded = schemas.CompanyPropertiesSchema().load({"company": "814814", "business": "Rent", "page": "3"})
    assert loaded == {"company": "814814", "business": "RENTAL", "page": 3}
    assert schemas.CompanyPropertiesSchema().load({"company": "814814"})["business"] == "SALE"
    with pytest.raises(ValidationError):
        schemas.CompanyPropertiesSchema().load({"company": "814814", "page": "51"})
    with pytest.raises(ValidationError):
        schemas.CompanyPropertiesSchema().load({"company": "814814", "business": "lease"})


# ---- condominium ----------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("59243c97-9ff5", "59243c97-9ff5"),
    ("59243C97-9FF5", "59243c97-9ff5"),
    ("59243c97-5032-49f4-9cf9-a688f0179ff5", "59243c97-9ff5"),
    ("https://www.zapimoveis.com.br/condominio/sp-sao-paulo-bela-vista-edificio-brasil-id-59243c97-9ff5/", "59243c97-9ff5"),
    ("https://www.zapimoveis.com.br/condominio/venda/sp-sao-paulo-bela-vista-edificio-brasil-id-59243c97-9ff5/", "59243c97-9ff5"),
])
def test_resolve_condominium(value, expected):
    assert refs.resolve_condominium(value) == expected
    assert schemas.CondominiumSchema().load({"condominium": value}) == {"condominium": expected}


@pytest.mark.parametrize("value", ["", "edificio brasil", "59243c97", "https://www.zapimoveis.com.br/imobiliaria/814814/"])
def test_resolve_condominium_invalid(value):
    with pytest.raises(ValueError):
        refs.resolve_condominium(value)


# ---- location -----------------------------------------------------------------------

def test_resolve_location_id():
    assert refs.resolve_location(PINHEIROS) == {"kind": "id", "location_id": PINHEIROS}


def test_resolve_location_text():
    assert refs.resolve_location(" Pinheiros, São Paulo ") == {"kind": "text", "query": "Pinheiros, São Paulo"}
    with pytest.raises(ValueError):
        refs.resolve_location("")
    with pytest.raises(ValueError):
        refs.resolve_location("x" * 121)


def test_resolve_location_link_plain():
    desc = refs.resolve_location("https://www.zapimoveis.com.br/venda/apartamentos/sp+sao-paulo+zona-oeste+pinheiros/")
    assert desc["kind"] == "link"
    assert desc["slug"] == "sp+sao-paulo+zona-oeste+pinheiros"
    assert desc["location_id"] is None
    assert desc["filters"] == {"business": "SALE", "listing_type": "USED", "property_type": "apartment"}


def test_resolve_location_link_with_filters_and_onde():
    link = ("https://www.zapimoveis.com.br/aluguel/apartamentos/sp+sao-paulo+zona-oeste+pinheiros/2-quartos/"
            "?onde=%2CS%C3%A3o+Paulo%2CS%C3%A3o+Paulo%2CZona+Oeste%2CPinheiros%2C%2C%2Cneighborhood%2C"
            "BR%3ESao+Paulo%3ENULL%3ESao+Paulo%3EZona+Oeste%3EPinheiros%2C-23.56%2C-46.69%2C"
            "&precoMaximo=6000&vagas=1&ordem=Menor%20pre%C3%A7o&pagina=2")
    desc = refs.resolve_location(link)
    assert desc["kind"] == "link"
    assert desc["location_id"] == PINHEIROS
    assert desc["slug"] == "sp+sao-paulo+zona-oeste+pinheiros"
    assert desc["filters"] == {"business": "RENTAL", "listing_type": "USED", "property_type": "apartment",
                               "min_bedrooms": 2, "max_price": 6000, "min_parking": 1, "page": 2,
                               "sort": "price_asc"}


def test_resolve_location_link_developments_and_city():
    desc = refs.resolve_location("https://www.zapimoveis.com.br/lancamentos/imoveis/sp+sao-paulo/")
    assert desc["slug"] == "sp+sao-paulo"
    assert desc["filters"]["listing_type"] == "DEVELOPMENT"
    assert "property_type" not in desc["filters"]      # "imoveis" = every type


@pytest.mark.parametrize("value", [
    "https://www.zapimoveis.com.br/imovel/x-id-2886301373/",
    "https://www.zapimoveis.com.br/",
    "https://example.com/venda/imoveis/sp+sao-paulo/",
])
def test_resolve_location_link_invalid(value):
    with pytest.raises(ValueError):
        refs.resolve_location(value)


def test_location_slug_from_url():
    assert refs.location_slug_from_url("/venda/imoveis/rj+rio-de-janeiro+zona-sul+copacabana/") == \
        "rj+rio-de-janeiro+zona-sul+copacabana"
    assert refs.location_slug_from_url("/venda/imoveis/sp+praia-grande/avenida-presidente-kennedy/") is None
    assert refs.location_slug_from_url(None) is None


def test_search_path():
    assert refs.search_path("sp+sao-paulo") == "/venda/imoveis/sp+sao-paulo/"
    assert refs.search_path("sp+sao-paulo", "RENTAL", type_slug="apartamentos") == "/aluguel/apartamentos/sp+sao-paulo/"
    assert refs.search_path("sp+sao-paulo", listing_type="DEVELOPMENT") == "/lancamentos/imoveis/sp+sao-paulo/"


# ---- search schemas ------------------------------------------------------------------

def test_properties_search_defaults():
    loaded = schemas.PropertiesSearchSchema().load({"location": PINHEIROS})
    assert loaded["location"] == {"kind": "id", "location_id": PINHEIROS}
    assert loaded["business"] == "SALE"
    assert loaded["sort"] == "relevance"
    assert loaded["page"] == 1
    assert loaded["property_type"] is None and loaded["min_bedrooms"] is None and loaded["below_market"] is None


def test_properties_search_filters():
    loaded = schemas.PropertiesSearchSchema().load({
        "location": "Pinheiros, São Paulo", "business": "rent", "property_type": "Apartment, studio",
        "min_bedrooms": "2", "min_price": "1000", "max_price": "6000.50", "min_area": "45.9",
        "amenities": "pool, gym", "no_guarantor": "yes", "near_transit": "0", "sort": "Price_Asc", "page": "50"})
    assert loaded["business"] == "RENTAL"
    assert loaded["property_type"] == ["apartment", "studio"]
    assert loaded["min_bedrooms"] == 2
    assert loaded["max_price"] == 6000.5
    assert loaded["min_area"] == 45
    assert loaded["amenities"] == ["POOL", "GYM"]
    assert loaded["no_guarantor"] is True and loaded["near_transit"] is False
    assert loaded["sort"] == "price_asc" and loaded["page"] == 50


@pytest.mark.parametrize("params", [
    {},                                                    # location required
    {"location": PINHEIROS, "page": "51"},                 # past the 1,500 cap
    {"location": PINHEIROS, "business": "lease"},
    {"location": PINHEIROS, "property_type": "castle"},
    {"location": PINHEIROS, "sort": "cheapest"},
    {"location": PINHEIROS, "min_price": "-1"},
    {"location": PINHEIROS, "min_bedrooms": "0"},
    {"location": PINHEIROS, "url": "x"},                   # unknown param
])
def test_properties_search_rejects(params):
    with pytest.raises(ValidationError):
        schemas.PropertiesSearchSchema().load(params)


def test_properties_count_schema_has_no_page_or_sort():
    assert "page" not in schemas.PropertiesCountSchema().load({"location": PINHEIROS})
    with pytest.raises(ValidationError):
        schemas.PropertiesCountSchema().load({"location": PINHEIROS, "page": "2"})


def test_developments_search_schema():
    loaded = schemas.DevelopmentsSearchSchema().load({"location": PINHEIROS, "construction_status": "Under_Construction"})
    assert loaded["construction_status"] == "UNDER_CONSTRUCTION"
    assert loaded["business"] == "SALE"
    with pytest.raises(ValidationError):
        schemas.DevelopmentsSearchSchema().load({"location": PINHEIROS, "business": "rent"})
    with pytest.raises(ValidationError):
        schemas.DevelopmentsSearchSchema().load({"location": PINHEIROS, "construction_status": "done"})


def test_locations_and_condominium_search_schemas():
    assert schemas.LocationsSearchSchema().load({"query": " Copacabana "}) == {"query": "Copacabana", "limit": 10}
    with pytest.raises(ValidationError):
        schemas.LocationsSearchSchema().load({"query": "x", "limit": "21"})
    with pytest.raises(ValidationError):
        schemas.LocationsSearchSchema().load({})
    assert schemas.CondominiumsSearchSchema().load({"query": "Edifício Brasil", "limit": "5"}) == \
        {"query": "Edifício Brasil", "limit": 5}


def test_location_insights_schema():
    loaded = schemas.LocationInsightsSchema().load({"location": "Moema, São Paulo", "property_type": "House"})
    assert loaded["property_type"] == "house" and loaded["business"] == "SALE"
    with pytest.raises(ValidationError):
        schemas.LocationInsightsSchema().load({"location": PINHEIROS, "property_type": "villa"})


# ---- vocabulary helpers ---------------------------------------------------------------

def test_unit_type_params_match_the_site_encoding():
    params = refs.unit_type_params(["apartment", "studio"])
    assert params == {"unitTypes": "APARTMENT", "unitSubTypes": "UnitSubType_NONE,DUPLEX,TRIPLEX|STUDIO",
                      "usageTypes": "RESIDENTIAL", "unitTypesV3": "APARTMENT,STUDIO"}
    assert refs.unit_type_params(None) == {}
    assert refs.unit_type_params(["house", "office"])["usageTypes"] == "RESIDENTIAL,COMMERCIAL"


def test_property_type_label():
    assert refs.property_type_label(["HOME"], ["TWO_STORY_HOUSE"], ["RESIDENTIAL"]) == "two_story_house"
    assert refs.property_type_label(["APARTMENT"], [], ["RESIDENTIAL"]) == "apartment"
    assert refs.property_type_label(["APARTMENT"], ["STUDIO"], None) == "studio"
    assert refs.property_type_label(["HOME"], ["UnitSubType_NONE"], ["COMMERCIAL"]) == "commercial_house"
    assert refs.property_type_label(["SPACESHIP"], None, None) == "spaceship"
    assert refs.property_type_label(None, None, None) is None


def test_min_count_param():
    assert refs.min_count_param(2) == "2,3,4"
    assert refs.min_count_param(4) == "4"
    assert refs.min_count_param(9) == "4"
    assert refs.min_count_param(None) is None


def test_photo_url_fills_the_cdn_template():
    tpl = "https://resizedimgs.zapimoveis.com.br/img/vr-listing/abc/{description}.jpg?action={action}&dimension={width}x{height}"
    assert refs.photo_url(tpl) == \
        "https://resizedimgs.zapimoveis.com.br/img/vr-listing/abc/imagem.jpg?action=fit-in&dimension=1920x1080"
    assert refs.photo_url(None) is None
