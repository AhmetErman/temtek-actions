"""Company newsroom scrapers (Phase 1 of the company tracker).

Each top home-appliance company exposes its press releases differently, but
their individual article pages almost always carry uniform Open Graph / JSON-LD
metadata. So the engine works in two steps:

  1. Collect article URLs from a company's listing pages (a simple per-company
     URL pattern + pagination).
  2. Enrich each article from its own page meta tags (title, date, summary,
     image) - uniform across sites.

See base.py for the engine and config.py (COMPANIES) for per-company settings.
"""
from .base import scrape_company  # noqa: F401
