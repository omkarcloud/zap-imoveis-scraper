"""Use the scraper straight from Python — no server needed.

    python main.py

Every function returns the same JSON the API does; results are written to
output/*.json. Params go through the same schemas the API uses, so defaults
are filled in and an id or a zapimoveis.com.br link both work.
"""
import json
import os

from zap_imoveis import api, schemas

os.makedirs("output", exist_ok=True)


def save(name, data):
    path = os.path.join("output", name)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"saved {path}")


def run(schema_cls, fn, **params):
    return fn(**schema_cls().load(params))


if __name__ == "__main__":
    # a listing id or any zapimoveis.com.br listing link: price, fees, all photos, address, agent phones
    save("property_2811582233.json", run(schemas.PropertySchema, api.properties_details, property="2811582233"))

    # 30 listings per page for any place name, location id or search link, with 16 filters
    save("search_ipanema.json", run(schemas.PropertiesSearchSchema, api.properties_search,
                                    location="Ipanema, Rio de Janeiro", business="sale"))

    # average price, price per m², price bands and the priciest neighborhoods around
    save("insights_copacabana.json", run(schemas.LocationInsightsSchema, api.locations_insights,
                                         location="Copacabana, Rio de Janeiro"))
