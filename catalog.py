"""Deterministic, read-only adapter for the public DummyJSON product catalog."""
from __future__ import annotations
import math
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib.parse import quote
from security import clean_text, safe_catalog_image

BASE_URL = "https://dummyjson.com"  # Never derived from user input.
MAX_RESULTS = 6


class CatalogError(Exception):
    pass


class ProductCatalog:
    def __init__(self, session=None):
        self.session = session or requests.Session()
        if session is None:
            retry = Retry(total=1, backoff_factor=0.3,
                          status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET"])
            self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.session.headers.update({"Accept": "application/json", "User-Agent": "ProductPilot-Streamlit/1.0"})

    def _get(self, path: str, params=None):
        if not path.startswith("/products") or "//" in path or ".." in path:
            raise CatalogError("Catalog endpoint not allowed.")
        try:
            response = self.session.get(BASE_URL + path, params=params, timeout=(5, 12))
            response.raise_for_status()
            if len(response.content) > 1_200_000:
                raise CatalogError("Catalog response is too large.")
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            raise CatalogError("The product catalog is temporarily unavailable.") from exc

    @staticmethod
    def _safe_product(raw):
        if not isinstance(raw, dict):
            return None
        pid = raw.get("id")
        if isinstance(pid, bool) or not isinstance(pid, int) or not 0 < pid < 1_000_000:
            return None
        price = raw.get("price")
        if isinstance(price, bool) or not isinstance(price, (int, float)) or not math.isfinite(price) or price < 0:
            return None
        stock = raw.get("stock", 0)
        stock = stock if isinstance(stock, int) and not isinstance(stock, bool) and 0 <= stock <= 1_000_000 else 0
        rating = raw.get("rating")
        rating = float(rating) if (isinstance(rating, (float, int)) and not isinstance(rating, bool) and math.isfinite(rating) and 0 <= rating <= 5) else None
        item = {
            "id": pid,
            "title": clean_text(raw.get("title"), 110),
            "description": clean_text(raw.get("description"), 340),
            "brand": clean_text(raw.get("brand"), 65),
            "category": clean_text(raw.get("category"), 65),
            "price": round(float(price), 2),
            "stock": stock,
            "rating": rating,
            "thumbnail": safe_catalog_image(raw.get("thumbnail")),
            "warrantyInformation": clean_text(raw.get("warrantyInformation"), 160),
            "returnPolicy": clean_text(raw.get("returnPolicy"), 160),
            "shippingInformation": clean_text(raw.get("shippingInformation"), 160),
            "url": f"https://dummyjson.com/products/{pid}",
        }
        return item

    def categories(self):
        data = self._get("/products/category-list")
        if not isinstance(data, list):
            raise CatalogError("Unexpected catalog response.")
        return {"categories": [clean_text(v, 65) for v in data[:80]]}

    def get_product(self, product_id):
        if isinstance(product_id, bool) or not isinstance(product_id, int) or not 0 < product_id < 1_000_000:
            raise ValueError("product_id must be a positive integer.")
        data = self._get(f"/products/{product_id}")
        product = self._safe_product(data)
        if product is None:
            raise CatalogError("Product details are unavailable.")
        return {"product": product}

    def search(self, query="", category=None, max_price=None, limit=4):
        if not isinstance(query, str) or len(query) > 100:
            raise ValueError("Search query must be a short string.")
        query = query.strip()
        if category is not None and (not isinstance(category, str) or len(category) > 70):
            raise ValueError("Invalid product category.")
        category = (category or "").strip().lower()
        if not query and not category:
            raise ValueError("Enter a product keyword or category.")
        if max_price is not None:
            if isinstance(max_price, bool) or not isinstance(max_price, (int, float)) or not math.isfinite(max_price) or not 0 <= max_price <= 1_000_000:
                raise ValueError("Invalid maximum price.")
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise ValueError("Invalid result limit.")
        limit = max(1, min(limit, MAX_RESULTS))
        if category:
            # Category slug is URL-encoded, and cannot change the fixed API host.
            data = self._get("/products/category/" + quote(category, safe=""), {"limit": 0})
        else:
            data = self._get("/products/search", {"q": query, "limit": 0})
        if not isinstance(data, dict) or not isinstance(data.get("products"), list):
            raise CatalogError("Unexpected product search response.")
        matches = []
        for raw in data["products"][:400]:
            product = self._safe_product(raw)
            if product is None:
                continue
            if category and product["category"].lower() != category:
                continue
            if query and category:
                haystack = " ".join(str(raw.get(x) or "")[:500] for x in ("title", "description", "brand", "category", "tags")).lower()
                if query.lower() not in haystack:
                    continue
            if max_price is not None and product["price"] > max_price:
                continue
            if product["stock"] < 1:
                continue
            matches.append(product)
        matches.sort(key=lambda p: (p["price"], -(p["rating"] or 0)))
        return {"query": query, "category": category or None, "max_price": max_price,
                "matching_count": len(matches), "products": matches[:limit]}


TOOLS = [
    {"type": "function", "name": "search_products", "description": "Search the catalog using a short keyword such as laptop, phone, watch or perfume. Filter by maximum price in USD.",
     "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "max_price": {"type": "number"}, "category": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["query"], "additionalProperties": False}},
    {"type": "function", "name": "browse_category", "description": "Browse product category slug (laptops, smartphones, fragrances, mens-watches).",
     "parameters": {"type": "object", "properties": {"category": {"type": "string"}, "max_price": {"type": "number"}, "limit": {"type": "integer"}}, "required": ["category"], "additionalProperties": False}},
    {"type": "function", "name": "get_product_details", "description": "Retrieve exact product ID with warranty, shipping and return information.",
     "parameters": {"type": "object", "properties": {"product_id": {"type": "integer"}}, "required": ["product_id"], "additionalProperties": False}},
    {"type": "function", "name": "list_categories", "description": "List available categories.",
     "parameters": {"type": "object", "properties": {}, "additionalProperties": False}},
]

# Keep optional search filters genuinely optional in the Responses API.
for _tool in TOOLS:
    _tool["strict"] = False


def dispatch_tool(catalog: ProductCatalog, name: str, args):
    if not isinstance(args, dict):
        return {"error": "Invalid tool arguments."}
    allowed = {"search_products": {"query", "category", "max_price", "limit"},
               "browse_category": {"category", "max_price", "limit"},
               "get_product_details": {"product_id"}, "list_categories": set()}
    if name not in allowed or set(args) - allowed[name]:
        return {"error": "Tool or parameters not allowed."}
    try:
        if name == "search_products":
            if "query" not in args:
                raise ValueError("A keyword is required.")
            return catalog.search(args["query"], args.get("category"), args.get("max_price"), args.get("limit", 4))
        if name == "browse_category":
            return catalog.search(category=args["category"], max_price=args.get("max_price"), limit=args.get("limit", 4))
        if name == "get_product_details":
            return catalog.get_product(args["product_id"])
        return catalog.categories()
    except (KeyError, TypeError, ValueError, CatalogError) as exc:
        return {"error": str(exc)}
