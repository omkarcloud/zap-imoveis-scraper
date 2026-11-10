"""Cache TTL per /zap-imoveis/* endpoint (cache.py, keyed on the validated
params). Property portals move daily: new ads land every hour in a big city,
prices are edited weekly, and an ad is pulled when it sells. Reference data
(locations, condominiums, agency profiles) is stable for days.
"""
from datetime import timedelta

# A filtered, paged search: the ranking reorders as ads are promoted or pulled.
SEARCH_CACHE = timedelta(hours=1)
# One listing record: price edits and status changes land within the day.
LISTING_CACHE = timedelta(hours=6)
# Total + amenity counts for a filter set move with the search index.
COUNT_CACHE = timedelta(hours=1)
# The autocomplete index of neighbourhoods / cities / streets is static.
LOCATIONS_CACHE = timedelta(days=7)
# An agency profile (name, CRECI, phones, rating) changes rarely.
COMPANY_CACHE = timedelta(hours=24)
# An agency's inventory turns over daily.
COMPANY_PROPERTIES_CACHE = timedelta(hours=1)
# The price insights block is recomputed by the site about daily.
INSIGHTS_CACHE = timedelta(hours=24)
# Condominium autocomplete: new condos are rare.
CONDOMINIUMS_SEARCH_CACHE = timedelta(days=7)
# A condominium page: static facts plus its current sale / rent ads.
CONDOMINIUM_CACHE = timedelta(hours=6)
