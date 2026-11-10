"""Marshmallow request schemas for every /zap-imoveis/* route.

ONE param per input (tripadvisor QueryOrIdField convention, never a sibling
`url`/`id` pair):

    location      glue location id ("BR>Sao Paulo>NULL>Sao Paulo>Zona Oeste>
                  Pinheiros", from /zap-imoveis/locations/search), a
                  zapimoveis.com.br search link, or free text ("Pinheiros,
                  São Paulo" — the site's own autocomplete picks the place)
    property      numeric listing id OR a ZAP / VivaReal listing link
    company       agency page id (814814), advertiser uuid OR the
                  /imobiliaria/<id>/ link
    condominium   short id (59243c97-9ff5), uuid OR the condominium link

The filter vocabulary (property types, sort orders, construction stages) is
the site's own, read from its bundle on 2026-11-07 (zap_imoveis/refs.py).
"""
from marshmallow import validate

from schema_fields import (BaseSchema, ChoiceField, CommaListField, Flag, LimitField, NonNegativeNumber,
                           PageField, PositiveInt, QueryField, RefField)
from zap_imoveis import refs


class LocationRefField(RefField):
    resolver = staticmethod(refs.resolve_location)


class PropertyRefField(RefField):
    resolver = staticmethod(refs.resolve_property)


class CompanyRefField(RefField):
    resolver = staticmethod(refs.resolve_company)


class CondominiumRefField(RefField):
    resolver = staticmethod(refs.resolve_condominium)


class _Area(NonNegativeNumber):
    """Square metres, whole numbers."""

    def _deserialize(self, value, attr, data, **kwargs):
        number = super()._deserialize(value, attr, data, **kwargs)
        return int(number) if number is not None else None


# ---- locations -------------------------------------------------------------------

class LocationsSearchSchema(BaseSchema):
    query = QueryField(max_length=120, metadata={
        "description": "place name to look up: a neighbourhood, city or street (Pinheiros, Copacabana, Rua Oscar Freire)"})
    limit = LimitField(default=10, max_size=20, metadata={
        "description": "maximum places per type (neighbourhoods, cities, streets), 1-20"})


# ---- property search filters ----------------------------------------------------

class _FiltersSchema(BaseSchema):
    location = LocationRefField(metadata={
        "description": ("where to search: a location id from /locations/search (BR>Sao Paulo>NULL>Sao Paulo>"
                        "Zona Oeste>Pinheiros), a zapimoveis.com.br search link, or a place name "
                        "(\"Pinheiros, São Paulo\")")})
    business = ChoiceField(refs.BUSINESS, load_default="SALE", metadata={
        "description": "sale (venda) or rent (aluguel); default sale"})
    property_type = CommaListField(allowed=list(refs.UNIT_TYPES), upper=False, max_items=21, metadata={
        "description": "comma list of property types: " + ", ".join(refs.UNIT_TYPES)})
    min_bedrooms = PositiveInt(max_value=20, metadata={"description": "minimum bedrooms (4 = 4 or more)"})
    min_bathrooms = PositiveInt(max_value=20, metadata={"description": "minimum bathrooms (4 = 4 or more)"})
    min_parking = PositiveInt(max_value=20, metadata={"description": "minimum parking spaces (4 = 4 or more)"})
    min_price = NonNegativeNumber(metadata={"description": "minimum price in BRL (monthly rent for business=rent)"})
    max_price = NonNegativeNumber(metadata={"description": "maximum price in BRL"})
    min_area = _Area(metadata={"description": "minimum usable area in m²"})
    max_area = _Area(metadata={"description": "maximum usable area in m²"})
    min_condo_fee = NonNegativeNumber(metadata={"description": "minimum monthly condo fee (condomínio) in BRL"})
    max_condo_fee = NonNegativeNumber(metadata={"description": "maximum monthly condo fee (condomínio) in BRL"})
    amenities = CommaListField(max_items=20, metadata={
        "description": ("comma list of amenity codes every result must have (POOL, GYM, ELEVATOR, BALCONY, "
                        "PETS_ALLOWED, FURNISHED, ...; /properties/count lists the codes with their counts)")})
    below_market = Flag(metadata={"description": "true = only ads the site marks as priced below the market"})
    no_guarantor = Flag(metadata={"description": "true = rentals that need no guarantor (sem fiador); rent only"})
    near_transit = Flag(metadata={"description": "true = only properties near a metro or train station"})
    virtual_tour = Flag(metadata={"description": "true = only ads with a virtual tour"})


class PropertiesSearchSchema(_FiltersSchema):
    sort = ChoiceField(list(refs.SORTS), load_default="relevance", metadata={
        "description": "relevance (default), newest, price_asc, price_desc, area_asc, area_desc"})
    page = PageField(max_page=refs.MAX_PAGE, metadata={
        "description": f"1-based page of 30 results; the site serves at most {refs.MAX_RESULTS} results per search"})


class PropertiesCountSchema(_FiltersSchema):
    """The same filters as /properties/search, without sort or page."""


class DevelopmentsSearchSchema(_FiltersSchema):
    business = ChoiceField({"sale": "SALE"}, load_default="SALE", metadata={
        "description": "new developments are for sale; accepted for symmetry"})
    construction_status = ChoiceField(refs.CONSTRUCTION_STATUS, metadata={
        "description": "planned (na planta), under_construction (em obras) or ready (pronto para morar)"})
    sort = ChoiceField(list(refs.SORTS), load_default="relevance", metadata={
        "description": "relevance (default), newest, price_asc, price_desc, area_asc, area_desc"})
    page = PageField(max_page=refs.MAX_PAGE, metadata={
        "description": f"1-based page of 30 results; the site serves at most {refs.MAX_RESULTS} results per search"})


# ---- single records ---------------------------------------------------------------

class PropertySchema(BaseSchema):
    property = PropertyRefField(metadata={
        "description": "listing id (2886301373) or a zapimoveis.com.br / vivareal.com.br listing link"})


class CompanySchema(BaseSchema):
    company = CompanyRefField(metadata={
        "description": "agency id (814814), advertiser uuid or a zapimoveis.com.br/imobiliaria/<id>/ link"})


class CompanyPropertiesSchema(CompanySchema):
    business = ChoiceField(refs.BUSINESS, load_default="SALE", metadata={
        "description": "sale (venda) or rent (aluguel); default sale"})
    page = PageField(max_page=refs.MAX_PAGE, metadata={"description": "1-based page of 30 listings"})


class LocationInsightsSchema(BaseSchema):
    location = LocationRefField(metadata={
        "description": ("the place: a location id from /locations/search, a zapimoveis.com.br search link, "
                        "or a place name (\"Moema, São Paulo\")")})
    business = ChoiceField(refs.BUSINESS, load_default="SALE", metadata={
        "description": "sale (venda) or rent (aluguel) market; default sale"})
    property_type = ChoiceField(list(refs.UNIT_TYPES), metadata={
        "description": "one property type to narrow the statistics to (apartment, house, ...); default all"})


class CondominiumsSearchSchema(BaseSchema):
    query = QueryField(max_length=120, metadata={"description": "condominium / building name to look up"})
    limit = LimitField(default=10, max_size=20, metadata={"description": "maximum condominiums, 1-20"})


class CondominiumSchema(BaseSchema):
    condominium = CondominiumRefField(metadata={
        "description": "condominium id (59243c97-9ff5), its uuid or a zapimoveis.com.br/condominio/ link"})
