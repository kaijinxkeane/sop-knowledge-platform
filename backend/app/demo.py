"""Fictional demo accounts (development only; seeded by `python -m app.cli seed-demo`).

With SOP_ENV=development and SOP_DEMO_SKIP_2FA=true these accounts, and only
these, sign in without a two-factor code (app/api/auth.py). The setting is
refused anywhere else (app/config.py), and every other account still needs one.
"""

from app.config import get_settings

DEMO_PASSWORD = "demo-password-2026"
# Fictional staff of the demo training company (names match demo-vault owners).
DEMO_USERS = [
    (
        "jordan.ng@staff.example.com",
        "Jordan Ng (CEO)",
        ["employee", "core-lead", "ceo", "platform-admin"],
        "core",
    ),
    ("avery.tan@staff.example.com", "Avery Tan", ["employee", "core-staff"], "core"),
    ("sam.lee@staff.example.com", "Sam Lee", ["employee", "core-staff"], "core"),
    ("morgan.lim@staff.example.com", "Morgan Lim", ["employee", "core-staff"], "core"),
    ("riley.ong@staff.example.com", "Riley Ong", ["employee", "it-lead"], "it"),
    ("casey.wong@staff.example.com", "Casey Wong", ["employee", "hr-staff", "hr-lead"], "hr"),
    ("taylor.goh@staff.example.com", "Taylor Goh (new hire)", ["employee"], None),
]

DEMO_EMAILS = frozenset(email for email, *_ in DEMO_USERS)


def skips_two_factor(email: str) -> bool:
    settings = get_settings()
    return (
        settings.environment == "development"
        and settings.demo_skip_2fa
        and email.strip().lower() in DEMO_EMAILS
    )
