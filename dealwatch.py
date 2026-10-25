#!/usr/bin/env python3
"""Angebots-Wächter: sucht Angebote (>= min_discount) und schickt 1x täglich eine ntfy-Push-Nachricht."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from urllib.parse import quote_plus, urljoin

import requests
import yaml
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; dealwatch/1.0; private use)",
    "Accept-Language": "de-CH,de;q=0.9",
}
PRICE_RE = re.compile(r"(\d{1,4}(?:[’'.,]\d{3})*(?:[.,]\d{1,2})?)")


@dataclass
class Deal:
    title: str
    shop: str
    category: str
    price: float
    old_price: float
    url: str
    currency: str = "CHF"
    source_ok: bool = True

    @property
    def discount(self) -> float:
        return 1 - self.price / self.old_price if self.old_price else 0.0

    def key(self) -> str:
        return f"{self.shop}|{self.url or self.title}|{self.price:.2f}"


@dataclass
class RunResult:
    deals: list[Deal] = field(default_factory=list)
    failed_sources: set[str] = field(default_factory=set)


def to_price(text: str) -> float | None:
    m = PRICE_RE.search(text.replace("\xa0", " "))
    if not m:
        return None
    s = m.group(1).replace("’", "").replace("'", "")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


# ---------- Parser ----------
def parse_jsonld(soup: BeautifulSoup, base: str, shop: str) -> list[tuple[str, float, float | None, str]]:
    """Liest schema.org Product/Offer-Daten (bei vielen Shops vorhanden)."""
    out = []

    def walk(node):
        if isinstance(node, list):
            for n in node:
                walk(n)
        elif isinstance(node, dict):
            t = node.get("@type")
            if t == "Product" or (isinstance(t, list) and "Product" in t):
                offers = node.get("offers") or {}
                if isinstance(offers, list):
                    offers = offers[0] if offers else {}
                price = to_price(str(offers.get("price", "")))
                high = to_price(str(offers.get("highPrice", ""))) if offers.get("highPrice") else None
                if price:
                    out.append((str(node.get("name", "")), price, high, urljoin(base, str(node.get("url", "")))))
            for v in node.values():
                if isinstance(v, (list, dict)):
                    walk(v)

    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            walk(json.loads(tag.string or ""))
        except (json.JSONDecodeError, TypeError):
            continue
    return out


def parse_cards(soup: BeautifulSoup, base: str) -> list[tuple[str, float, float | None, str]]:
    """Fallback: Kacheln mit Titel, Aktionspreis und durchgestrichenem Preis / '-xx%'."""
    out = []
    for a in soup.find_all("a", href=True):
        card = a.find_parent(["article", "li", "div"]) or a
        text = card.get_text(" ", strip=True)
        if len(text) < 8 or len(text) > 600:
            continue
        old = None
        strike = card.find(["del", "s", "strike"]) or card.find(class_=re.compile(r"(old|was|strike|statt|original)", re.I))
        if strike:
            old = to_price(strike.get_text(" ", strip=True))
        if old is None:
            m = re.search(r"statt\s*(?:CHF|Fr\.|€)?\s*([\d.,’']+)", text, re.I)
            old = to_price(m.group(1)) if m else None
        prices = [p for p in (to_price(x) for x in re.findall(r"(?:CHF|Fr\.|€)\s*[\d.,’']+|[\d.,’']+\s*(?:CHF|€)", text)) if p]
        if not prices:
            continue
        price = min(prices)
        if old is None and len(prices) > 1:
            old = max(prices)
        if old is None:
            m = re.search(r"-\s?(\d{2})\s?%", text)
            if m:
                old = price / (1 - int(m.group(1)) / 100)
        title = (a.get("title") or a.get_text(" ", strip=True) or text)[:140]
        out.append((title, price, old, urljoin(base, a["href"])))
    return out


# ---------- Filter ----------
def matches(cat: dict, title: str, price: float, old: float) -> bool:
    if not re.search(cat["require"], title):
        return False
    if cat.get("exclude") and re.search(cat["exclude"], title):
        return False
    if cat.get("size_regex") and not re.search(cat["size_regex"], title):
        return False
    if cat.get("origin_regex") and not re.search(cat["origin_regex"], title):
        return False
    if cat.get("brands") and not re.search(cat["brands"], title):
        return False
    return old > price > 0


def collect(cfg: dict, session: requests.Session, delay: float = 1.5) -> RunResult:
    res = RunResult()
    seen = set()
    for cat_id, cat in cfg["categories"].items():
        for shop_id in cat["shops"]:
            shop = cfg["shops"][shop_id]
            for q in cat["queries"]:
                url = shop["search_url"].format(q=quote_plus(q))
                try:
                    r = session.get(url, headers=HEADERS, timeout=20)
                    r.raise_for_status()
                except requests.RequestException as e:
                    print(f"[WARN] {shop['name']} '{q}': {e}", file=sys.stderr)
                    res.failed_sources.add(shop["name"])
                    continue
                soup = BeautifulSoup(r.text, "html.parser")
                items = parse_jsonld(soup, url, shop["name"]) + parse_cards(soup, url)
                for title, price, old, link in items:
                    if not old or not matches(cat, title, price, old):
                        continue
                    d = Deal(title.strip(), shop["name"], cat["label"], price, old, link, shop.get("currency", "CHF"))
                    if d.discount >= cfg["min_discount"] and d.key() not in seen:
                        seen.add(d.key())
                        res.deals.append(d)
                time.sleep(delay)
    res.deals.sort(key=lambda d: d.discount, reverse=True)
    return res


# ---------- Push ----------
def build_message(res: RunResult, limit: int) -> tuple[str, str]:
    if not res.deals:
        body = "Heute keine Angebote ab 30 % gefunden."
    else:
        lines = []
        for d in res.deals[:limit]:
            lines.append(f"-{d.discount:.0%} {d.category}: {d.title[:70]}\n  {d.currency} {d.price:.2f} statt {d.old_price:.2f} ({d.shop})\n  {d.url}")
        extra = len(res.deals) - limit
        body = "\n\n".join(lines) + (f"\n\n… und {extra} weitere" if extra > 0 else "")
    if res.failed_sources:
        body += "\n\nNicht erreichbar: " + ", ".join(sorted(res.failed_sources))
    title = f"{len(res.deals)} Angebote ab 30 %" if res.deals else "Keine Angebote heute"
    return title, body


def push_ntfy(topic: str, title: str, body: str) -> None:
    r = requests.post(
        f"https://ntfy.sh/{topic}",
        data=body.encode("utf-8"),
        headers={"Title": title.encode("utf-8"), "Tags": "moneybag", "Priority": "default"},
        timeout=20,
    )
    r.raise_for_status()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(os.path.dirname(__file__), "config.yaml"))
    ap.add_argument("--dry-run", action="store_true", help="nur anzeigen, nichts senden")
    ap.add_argument("--test-push", action="store_true", help="Test-Nachricht senden")
    args = ap.parse_args()

    cfg = yaml.safe_load(open(args.config, encoding="utf-8"))
    topic = os.environ.get(cfg["ntfy_topic_env"], "")

    if args.test_push:
        if not topic:
            print("Umgebungsvariable NTFY_TOPIC fehlt", file=sys.stderr)
            return 2
        push_ntfy(topic, "Angebots-Wächter", "Test erfolgreich – Push funktioniert.")
        return 0

    res = collect(cfg, requests.Session())
    title, body = build_message(res, cfg["max_items_per_push"])
    print(title + "\n" + body)
    if args.dry_run:
        return 0
    if not topic:
        print("Umgebungsvariable NTFY_TOPIC fehlt", file=sys.stderr)
        return 2
    push_ntfy(topic, title, body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
