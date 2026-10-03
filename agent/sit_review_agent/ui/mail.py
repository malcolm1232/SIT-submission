"""The Email action of a finished review (decision #36, 2026-10-03).

Sends the HTML export (``ui.export``) and ``report.md`` as two attachments to one typed address, from
this computer, through the SMTP server in ``config/ui.yaml`` (``email``: ``host``, ``port``,
``starttls``, ``username``, ``from``). The password is read from :data:`PASSWORD_ENV` at the moment
of sending and is never written anywhere. Without the config or the variable the page shows the
button disabled with :data:`NOT_CONFIGURED`; the server refuses the same way, never a silent no-op.
With ``starttls: true`` a server that does not offer STARTTLS is a failed send, not a clear-text one.
Each attempt is logged to ``runs/<id>/ui/outbox.jsonl`` (recipient, time, sizes, result), never the
content.
"""

from __future__ import annotations

import json
import os
import re
import smtplib
import ssl
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import yaml

from sit_review_agent.ui.rundata import UI_DIR

PASSWORD_ENV = "SIT_UI_SMTP_PASSWORD"
NOT_CONFIGURED = "Email is not configured: see config/ui.yaml"
OUTBOX = "outbox.jsonl"
TIMEOUT_S = 30.0
#: One plain address: no display name, no list, no whitespace or angle brackets; the same rule as the page.
ADDRESS_RE = re.compile(r"^[^\s@,;<>\"]+@[^\s@,;<>\"]+\.[^\s@,;<>\"]+$")
MAX_ADDRESS_CHARS = 254


class EmailRefused(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass(frozen=True)
class SmtpConfig:
    host: str
    port: int
    starttls: bool
    username: str
    sender: str


def valid_address(addr: str) -> bool:
    return len(addr) <= MAX_ADDRESS_CHARS and bool(ADDRESS_RE.match(addr))


def load_smtp(path: Path) -> tuple[SmtpConfig | None, str]:
    """The SMTP settings in ``path`` (``config/ui.yaml``), or ``None`` and what is missing."""
    if not path.is_file():
        return None, "there is no config/ui.yaml"
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        return None, f"config/ui.yaml does not parse ({type(exc).__name__})"
    email = doc.get("email") if isinstance(doc, dict) else None
    if not isinstance(email, dict):
        return None, "config/ui.yaml has no email section"
    host, user, sender = (str(email.get(k) or "").strip() for k in ("host", "username", "from"))
    missing = [k for k, v in (("host", host), ("username", user), ("from", sender)) if not v]
    if missing:
        return None, f"config/ui.yaml leaves {', '.join(missing)} empty"
    port = email.get("port", 587)
    if not isinstance(port, int) or isinstance(port, bool) or not 0 < port < 65536:
        return None, "config/ui.yaml email.port is not a port number"
    if not valid_address(sender):
        return None, "config/ui.yaml email.from is not one plain address"
    return SmtpConfig(host=host, port=port, starttls=email.get("starttls", True) is not False, username=user,
                      sender=sender), ""


def status(cfg: SmtpConfig | None, detail: str = "") -> dict[str, Any]:
    """What the page shows: enabled, or disabled with :data:`NOT_CONFIGURED` and what is missing."""
    if cfg is None:
        return {"enabled": False, "reason": NOT_CONFIGURED, "detail": detail or "no SMTP settings were loaded",
                "from": None, "host": None}
    if not os.environ.get(PASSWORD_ENV):
        return {"enabled": False, "reason": NOT_CONFIGURED,
                "detail": f"{PASSWORD_ENV} is not set in the environment of dra ui", "from": cfg.sender,
                "host": cfg.host}
    return {"enabled": True, "reason": None, "detail": None, "from": cfg.sender, "host": cfg.host}


def build_message(cfg: SmtpConfig, to: str, run_id: str, title: str,
                  attachments: list[tuple[str, bytes, str, str]]) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = cfg.sender
    msg["To"] = to
    msg["Subject"] = f"Design review: {title} ({run_id})"
    names = " and ".join(a[0] for a in attachments)
    msg.set_content(f"The design review of {title} (run {run_id}) is attached as {names}.\n"
                    "Open the .html file in a browser; report.md is the same review as plain text.\n\n"
                    "Sent from the SIT review page (dra ui).\n")
    for name, data, maintype, subtype in attachments:
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=name,
                           params={"charset": "utf-8"} if maintype == "text" else None)
    return msg


def _log(run_dir: Path, row: dict[str, Any]) -> None:
    p = run_dir / UI_DIR / OUTBOX
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


def send(run_dir: Path, to: str, cfg: SmtpConfig | None, *, title: str,
         attachments: list[tuple[str, bytes, str, str]],
         smtp_factory: Callable[..., smtplib.SMTP] = smtplib.SMTP) -> dict[str, Any]:
    """Send ``attachments`` to ``to`` and log the attempt. Raises :class:`EmailRefused` before any
    connection when email is not configured (409) or the address is not one plain address (400), and
    after a failed attempt (502, logged)."""
    st = status(cfg)
    if not st["enabled"] or cfg is None:
        raise EmailRefused(409, f"{NOT_CONFIGURED} ({st['detail']}).")
    to = to.strip()
    if not valid_address(to):
        raise EmailRefused(400, "Type one email address, such as name@example.org.")
    password = os.environ.get(PASSWORD_ENV, "")
    msg = build_message(cfg, to, run_dir.name, title, attachments)
    raw = msg.as_bytes()
    row: dict[str, Any] = {"at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "to": to, "from": cfg.sender,
                           "smtp_host": f"{cfg.host}:{cfg.port}",
                           "attachments": [{"name": a[0], "bytes": len(a[1])} for a in attachments],
                           "message_bytes": len(raw), "result": "sent", "error": None}
    try:
        with smtp_factory(cfg.host, cfg.port, timeout=TIMEOUT_S) as smtp:
            smtp.ehlo()
            if cfg.starttls:
                smtp.starttls(context=ssl.create_default_context())
                smtp.ehlo()
            smtp.login(cfg.username, password)
            smtp.send_message(msg, from_addr=cfg.sender, to_addrs=[to])
    except (OSError, smtplib.SMTPException) as exc:
        error = f"{type(exc).__name__}: {exc}"
        if password:
            error = error.replace(password, "<password>")
        row.update(result="failed", error=error[:500])
        _log(run_dir, row)
        raise EmailRefused(502, f"The mail was not sent: {row['error']}") from None
    _log(run_dir, row)
    return row
