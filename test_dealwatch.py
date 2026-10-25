import os
import sys

import yaml
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import dealwatch as dw

CFG = yaml.safe_load(open(os.path.join(os.path.dirname(__file__), "..", "config.yaml"), encoding="utf-8"))


def test_price_parsing():
    assert dw.to_price("CHF 1’299.00") == 1299.0
    assert dw.to_price("49,90 €") == 49.9


def test_jsonld_and_discount():
    html = '''<script type="application/ld+json">{"@type":"Product","name":"Puma Kinder Sneaker Gr. 30",
    "url":"/p/1","offers":{"price":"30.00","highPrice":"60.00"}}</script>'''
    items = dw.parse_jsonld(BeautifulSoup(html, "html.parser"), "https://x.ch/", "X")
    assert items[0][1:3] == (30.0, 60.0)


def test_size_filter():
    cat = CFG["categories"]["kinderschuhe"]
    assert dw.matches(cat, "Nike Kinder Schuh Gr. 36", 30, 60)
    assert not dw.matches(cat, "Nike Kinder Schuh Gr. 38", 30, 60)
    assert not dw.matches(cat, "Reebok Kinder Schuh Gr. 36", 30, 60)


def test_lamm_origin():
    cat = CFG["categories"]["lamm"]
    assert dw.matches(cat, "Lammgigot Schweiz", 10, 20)
    assert not dw.matches(cat, "Lammgigot Neuseeland", 10, 20)
    assert not dw.matches(cat, "Lammgigot", 10, 20)  # Herkunft unbekannt -> nicht aufnehmen


def test_threshold_and_message():
    good = dw.Deal("Legaris Reserva", "Denner", "Wein", 14.0, 20.0, "https://d.ch/1")
    bad = dw.Deal("Legaris Reserva", "Denner", "Wein", 18.0, 20.0, "https://d.ch/2")
    assert good.discount >= 0.30 > bad.discount
    title, body = dw.build_message(dw.RunResult([good], {"Galaxus"}), 8)
    assert "-30%" in body and "Nicht erreichbar: Galaxus" in body
