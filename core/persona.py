"""
persona.py – Generates coherent synthetic user personas.

A "persona" groups related fake data so that browser entries (autofill,
passwords, credit cards, etc.) look like they belong to the same person.
"""
from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field
from typing import List

from faker import Faker

_fake = Faker("en_US")


# ──────────────────────────────────────────────────────────────────────────────
# Data classes
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class Address:
    first_name: str
    last_name: str
    company: str
    street: str
    city: str
    state: str
    zip_code: str
    country: str
    phone: str
    email: str


@dataclass
class CreditCard:
    card_type: str
    number: str
    expiry_month: int
    expiry_year: int
    cvv: str
    cardholder_name: str
    billing_zip: str

    @property
    def expiry(self) -> str:
        return f"{self.expiry_month:02d}/{self.expiry_year}"


@dataclass
class SavedPassword:
    site_url: str
    signon_realm: str
    username: str
    password: str
    site_title: str


@dataclass
class Persona:
    guid: str
    full_name: str
    first_name: str
    last_name: str
    email: str
    phone: str
    username: str
    address: Address
    passwords: List[SavedPassword] = field(default_factory=list)
    cards: List[CreditCard] = field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────────────
# Demo sites & card data
# ──────────────────────────────────────────────────────────────────────────────

_DEMO_SITES = [
    ("https://mail.google.com/",                   "Google Mail",      "mail.google.com"),
    ("https://github.com/login",                   "GitHub",           "github.com"),
    ("https://www.linkedin.com/login",             "LinkedIn",         "linkedin.com"),
    ("https://accounts.microsoft.com/",            "Microsoft",        "microsoft.com"),
    ("https://www.amazon.com/ap/signin",           "Amazon",           "amazon.com"),
    ("https://www.dropbox.com/login",              "Dropbox",          "dropbox.com"),
    ("https://slack.com/signin",                   "Slack",            "slack.com"),
    ("https://www.netflix.com/login",              "Netflix",          "netflix.com"),
    ("https://www.reddit.com/login",               "Reddit",           "reddit.com"),
    ("https://twitter.com/i/flow/login",           "X / Twitter",      "twitter.com"),
    ("https://www.instagram.com/accounts/login/",  "Instagram",        "instagram.com"),
    ("https://www.facebook.com/login",             "Facebook",         "facebook.com"),
    ("https://app.hubspot.com/login",              "HubSpot",          "hubspot.com"),
    ("https://login.salesforce.com/",              "Salesforce",       "salesforce.com"),
    ("https://bitbucket.org/account/signin/",      "Bitbucket",        "bitbucket.org"),
    ("https://gitlab.com/users/sign_in",           "GitLab",           "gitlab.com"),
    ("https://www.figma.com/login",                "Figma",            "figma.com"),
    ("https://app.asana.com/",                     "Asana",            "asana.com"),
    ("https://trello.com/login",                   "Trello",           "trello.com"),
    ("https://zoom.us/signin",                     "Zoom",             "zoom.us"),
]

_CARD_TYPES = ["Visa", "Mastercard", "American Express", "Discover"]
_CARD_PREFIX = {"Visa": "4", "Mastercard": "5", "American Express": "37", "Discover": "6011"}


def _luhn_card(card_type: str) -> str:
    """Generate a Luhn-valid synthetic card number (NEVER a real card)."""
    prefix = _CARD_PREFIX.get(card_type, "4")
    length = 15 if card_type == "American Express" else 16
    digits = list(prefix)
    while len(digits) < length - 1:
        digits.append(str(random.randint(0, 9)))
    total = sum(
        (n * 2 - 9 if (n := int(d) * 2) > 9 else n) if i % 2 == 0 else int(d)
        for i, d in enumerate(reversed(digits))
    )
    digits.append(str((10 - total % 10) % 10))
    return "".join(digits)


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def generate_persona(seed: int | None = None) -> Persona:
    """Create a single coherent synthetic persona."""
    if seed is not None:
        Faker.seed(seed)
        random.seed(seed)

    first, last = _fake.first_name(), _fake.last_name()
    username = f"{first.lower()}.{last.lower()}{random.randint(10, 99)}"
    email, phone = _fake.email(), _fake.phone_number()

    addr = Address(
        first_name=first, last_name=last, company=_fake.company(),
        street=_fake.street_address(), city=_fake.city(),
        state=_fake.state_abbr(), zip_code=_fake.postcode(),
        country="US", phone=phone, email=email,
    )

    # Passwords – random subset of demo sites
    num_pw = random.randint(6, min(len(_DEMO_SITES), 14))
    passwords = [
        SavedPassword(
            site_url=url, signon_realm=f"https://{host}/",
            username=username if random.random() > 0.3 else email,
            password=_fake.password(length=random.randint(10, 18)),
            site_title=title,
        )
        for url, title, host in random.sample(_DEMO_SITES, num_pw)
    ]

    # Credit cards
    cards = [
        CreditCard(
            card_type=(ct := random.choice(_CARD_TYPES)),
            number=_luhn_card(ct),
            expiry_month=random.randint(1, 12),
            expiry_year=random.randint(2025, 2030),
            cvv=str(random.randint(100, 999)),
            cardholder_name=f"{first} {last}",
            billing_zip=addr.zip_code,
        )
        for _ in range(random.randint(1, 3))
    ]

    return Persona(
        guid=str(uuid.uuid4()), full_name=f"{first} {last}",
        first_name=first, last_name=last, email=email,
        phone=phone, username=username, address=addr,
        passwords=passwords, cards=cards,
    )


def generate_personas(count: int = 1, base_seed: int | None = None) -> list[Persona]:
    """Generate *count* distinct personas. Same base_seed → same personas."""
    return [
        generate_persona(seed=(base_seed + i * 31) if base_seed is not None else None)
        for i in range(count)
    ]
