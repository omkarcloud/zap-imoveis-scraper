# 🏡 Zap Imoveis Scraper

Zap Imoveis Scraper is a **free and open-source** scraper that gets you **unlimited** detailed ZAP Imóveis property data for free.

## ✨ What Can I Get?

- 🏡 **Full details on 4.6M+ Brazilian listings** — price, condo fee, IPTU, m², rooms, GPS, every photo & agent phones
- 🔍 **Search any city, neighborhood or street** — 16 filters, sale or rent, 30 listings per page
- 📊 **Price insights for any place** — average price, R$/m², price bands & the priciest neighborhoods
- 🏢 **Agencies, new developments & condos** — CRECI licenses, ratings, developers, construction stages & unit prices

## 🎥 Example: A Full ZAP Imóveis Listing

```json
{
  "id": "2811582233",
  "link": "https://www.zapimoveis.com.br/imovel/venda-cobertura-5-quartos-com-piscina-ipanema-zona-sul-rio-de-janeiro-rj-375m2-id-2811582233/",
  "title": "Cobertura Duplex em Ipanema",
  "description": "Real Up Vende: Excelente cobertura duplex com linda vista mar! ...",
  "business": "sale",
  "property_type": "penthouse",
  "pricing": { "price": 42000000, "currency": "BRL", "condo_fee_monthly": 12500, "iptu": 29257, "iptu_period": "yearly" },
  "price_per_m2": 112000.0,
  "bedrooms": 5,
  "bathrooms": 7,
  "suites": 3,
  "parking_spaces": 5,
  "usable_area_m2": 375,
  "amenities": ["PETS_ALLOWED", "ELEVATOR", "GATED_COMMUNITY", "SEA_VIEW", "POOL"],
  "address": {
    "street": "Rua Vinícius de Moraes",
    "number": "83",
    "neighborhood": "Ipanema",
    "city": "Rio de Janeiro",
    "state_code": "RJ",
    "zip_code": "22411010",
    "coordinates": { "latitude": -22.984441, "longitude": -43.20309 }
  },
  "photos": ["https://resizedimgs.zapimoveis.com.br/img/vr-listing/62640e0d08f4b144f18af6b9d7e9a577/imagem.jpg?action=fit-in&dimension=1920x1080"],
  "photo_count": 52,
  "advertiser": {
    "name": "Real Up Imoveis",
    "license_number": "7357-J-RJ",
    "phones": ["2122748888", "21998593444"],
    "whatsapp": "21998593444",
    "link": "https://www.zapimoveis.com.br/imobiliaria/572230/"
  },
  "nearby_transport": { "within_1km": ["Metrô General Osório", "Metrô Nossa Senhora Da Paz"] },
  "created_at": "2025-06-05T05:51:48Z",
  "updated_at": "2026-09-02T17:36:38Z"
}
```

*Trimmed for readability.*

## 🚀 Unlimited Free ZAP Imóveis Data — Get It in 60 Seconds

1️⃣ Clone and install:
```bash
git clone https://github.com/omkarcloud/zap-imoveis-scraper
cd zap-imoveis-scraper
python -m pip install -r requirements.txt
```

2️⃣ Start the API:
```bash
python run.py
```

ZAP Imóveis' Cloudflare protection refuses some networks outright. Getting `blocked` errors? Start it on a residential proxy instead, ideally a Brazilian one:
```bash
ZAP_IMOVEIS_PROXY=http://user:pass@host:port python run.py
```

3️⃣ Get your first data:
```bash
curl "http://localhost:8000/properties/details?property=2811582233"
```

```json
{
  "id": "2811582233",
  "link": "https://www.zapimoveis.com.br/imovel/venda-cobertura-5-quartos-com-piscina-ipanema-zona-sul-rio-de-janeiro-rj-375m2-id-2811582233/",
  "title": "Cobertura Duplex em Ipanema",
  "business": "sale",
  "property_type": "penthouse",
  "pricing": { "price": 42000000, "currency": "BRL", "condo_fee_monthly": 12500, "iptu": 29257, "iptu_period": "yearly" },
  "price_per_m2": 112000.0,
  "bedrooms": 5,
  "bathrooms": 7,
  "usable_area_m2": 375,
  "address": { "street": "Rua Vinícius de Moraes", "neighborhood": "Ipanema", "city": "Rio de Janeiro", "state_code": "RJ" },
  "photo_count": 52,
  "advertiser": { "name": "Real Up Imoveis", "license_number": "7357-J-RJ", "phones": ["2122748888", "21998593444"] },
  "created_at": "2025-06-05T05:51:48Z"
}
```

All 10 endpoints are now live at `http://localhost:8000`.

## 📚 Endpoints

10 endpoints cover everything you need.

| Endpoint | Path | Returns |
|---|---|---|
| Property Details | `/properties/details` | Every detail of one listing: price, fees, photos, agent phones |
| Search Properties | `/properties/search` | 30 listings per page for any place, 16 filters, sortable |
| Location Autocomplete | `/locations/search` | Location IDs for neighborhoods, cities and streets |
| Count Properties | `/properties/count` | Total matching listings, plus counts per amenity |
| Search New Developments | `/developments/search` | New developments with developer, construction stage and unit prices |
| Location Price Insights | `/locations/insights` | Average price, R$/m², price bands and top neighborhoods |
| Agency Details | `/companies/details` | CRECI license, phones, website, rating and listing count |
| Agency Listings | `/companies/properties` | Every live listing of one agency, 30 per page |
| Condominium Search | `/condominiums/search` | Condominium IDs and addresses by building name |
| Condominium Details | `/condominiums/details` | Amenities, unit sizes, starting prices and current listings |

## 🔍 Exploring Parameters

The same API is published on RapidAPI, and its playground is the easiest place to try parameters and see raw responses. Once a request looks right, run it locally for **unlimited free** data.

1. [Subscribe to the free plan](https://rapidapi.com/OmkarCloud/api/best-zap-imoveis-scraper-free-1000-calls/pricing) — 1,000 calls/month, no credit card.
2. [Try the endpoints in the playground](https://rapidapi.com/OmkarCloud/api/best-zap-imoveis-scraper-free-1000-calls/playground) — every param is pre-filled, so you see real data in one click.
3. Copy the generated code and replace `https://best-zap-imoveis-scraper-free-1000-calls.p.rapidapi.com` with `http://localhost:8000`. It will now run against your local API.

```python
import requests

# generated by the playground, host swapped for the local API
response = requests.get(
    "http://localhost:8000/properties/details",
    params={"property": "2811582233"},
)
print(response.json())
```

## 💬 Have Questions? We Have Answers.

You're a developer — we know how hard completing a project can be. So we offer full support: just message us and we'll reply ✅ with a solution within 1 working day.

[![Message Us on WhatsApp about Zap Imoveis Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/whatsapp-us.png)](https://www.omkar.cloud/l/zap-imoveis-scraper-github-whatsapp)

[![Ask Us by Email about Zap Imoveis Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/ask-on-email.png)](mailto:happy.to.help@omkar.cloud?subject=Help%20with%20Zap%20Imoveis%20Scraper%20API&body=I%20need%20help%20using%20the%20Zap%20Imoveis%20Scraper%20API.)

## ⚡ Popular Scrapers by Omkar Cloud

- [**Google Maps Scraper (3,100+ GitHub Stars)**](https://github.com/omkarcloud/google-maps-scraper) — type "dentists in New York", get every business as a ready-to-call lead list: phones, emails, websites & reviews. Up to 100K free leads/month.
- [**G2 Scraper**](https://www.omkar.cloud/tools/g2-scraper) — G2 product details, ratings & AI-found contacts
- [**Website Email Contact Scraper**](https://www.omkar.cloud/tools/website-email-contact-scraper) — emails, phones & socials from any website
- [**AliExpress Scraper**](https://www.omkar.cloud/tools/aliexpress-scraper-api) — live product details, SKU variants, stock & shipping
- [**Booking Scraper**](https://www.omkar.cloud/tools/booking-scraper) — Booking.com hotels: prices, ratings, rooms & amenities
- [**Etsy Scraper**](https://www.omkar.cloud/tools/etsy-scraper) — Etsy products: prices, discounts, shops & variations

## ⭐ Love It? [Star It ⭐!](https://github.com/omkarcloud/zap-imoveis-scraper)

Star the repo ⭐ and become my star hero!

It's just 1 click, but it means the world to me.

[![Star us on GitHub](https://raw.githubusercontent.com/omkarcloud/google-maps-scraper/master/screenshots/star-us.png)](https://github.com/omkarcloud/zap-imoveis-scraper)
