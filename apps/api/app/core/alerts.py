# ruff: noqa: E501
"""Deadline alerts: one warning at 72h, 24h and 6h before a response is due (PRD F1).

Rules
- Only disputes still waiting on the seller (needs_response, drafted) are alerted. Approved, submitted,
  accepted, won and lost disputes never are.
- Each (dispute, threshold) is sent at most once. If a dispute is found already inside a smaller window
  (created late, or the checker was down), only the tightest crossed threshold is sent and the wider
  ones are recorded as `superseded`, so the seller is not spammed with three emails at once.
- Without SMTP settings the alert is stored as channel `simulated` and labelled so everywhere. It is
  never presented as an email that was really delivered.
"""

from __future__ import annotations

import smtplib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import EmailMessage
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.tables import AlertRow, DisputeRow
from app.settings import settings

THRESHOLDS = (72, 24, 6)
WAITING = ("needs_response", "drafted")


@dataclass(frozen=True)
class Sent:
    channel: str  # email | simulated
    to: str | None


class Notifier(Protocol):
    def send(self, subject: str, body: str) -> Sent: ...


class SimulatedNotifier:
    """No mail server configured: record the alert, deliver nothing, say so."""

    def send(self, subject: str, body: str) -> Sent:
        return Sent("simulated", settings.alert_email_to or None)


class SmtpNotifier:
    def send(self, subject: str, body: str) -> Sent:
        msg = EmailMessage()
        msg["Subject"], msg["From"], msg["To"] = (
            subject,
            settings.alert_email_from,
            settings.alert_email_to,
        )
        msg.set_content(body)
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            smtp.starttls()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)
        return Sent("email", settings.alert_email_to)


def default_notifier() -> Notifier:
    return SmtpNotifier() if settings.smtp_host and settings.alert_email_to else SimulatedNotifier()


def _message(d: DisputeRow, threshold: int, hours_left: float) -> tuple[str, str]:
    money = f"{d.amount / 100:.2f} {d.currency.upper()}"
    subject = f"[Countercase] {threshold}h left to respond: {money} dispute {d.id}"
    body = (
        f"A {money} dispute ({(d.category or 'other').replace('_', ' ')}) is due {d.deadline_at:%Y-%m-%d %H:%M} UTC "
        f"(about {hours_left:.0f}h from now). Status: {d.status.replace('_', ' ')}.\n"
        f"Open it in Countercase to review the draft and approve it before the deadline."
    )
    return subject, body


def run_alerts(
    session: Session, *, now: datetime | None = None, notifier: Notifier | None = None
) -> list[AlertRow]:
    """Check every waiting dispute once; returns the alerts sent or attempted on this run."""
    now = now or datetime.now(UTC)
    notifier = notifier or default_notifier()
    out: list[AlertRow] = []
    disputes = session.scalars(select(DisputeRow).where(DisputeRow.status.in_(WAITING))).all()
    for d in disputes:
        hours_left = (d.deadline_at - now).total_seconds() / 3600
        if hours_left <= 0:
            continue  # already overdue: an alert now would only be noise
        crossed = [t for t in THRESHOLDS if hours_left <= t]
        if not crossed:
            continue
        have = set(
            session.scalars(select(AlertRow.threshold_hours).where(AlertRow.dispute_id == d.id))
        )
        tightest = min(crossed)
        if tightest in have:
            continue
        subject, body = _message(d, tightest, hours_left)
        row = AlertRow(
            id=f"al_{uuid.uuid4().hex[:10]}",
            dispute_id=d.id,
            threshold_hours=tightest,
            channel="simulated",
            status="sent",
            subject=subject,
            body=body,
        )
        try:
            sent = notifier.send(subject, body)
            row.channel, row.to_address = sent.channel, sent.to
        except Exception as exc:  # noqa: BLE001 - record the failure, keep checking other disputes
            row.status, row.error = "failed", str(exc)[:500]
        try:
            with session.begin_nested():
                session.add(row)
                for wider in (t for t in crossed if t > tightest and t not in have):
                    session.add(
                        AlertRow(
                            id=f"al_{uuid.uuid4().hex[:10]}",
                            dispute_id=d.id,
                            threshold_hours=wider,
                            channel=row.channel,
                            status="superseded",
                            subject=subject,
                            body="Superseded by a tighter warning.",
                        )
                    )
        except IntegrityError:
            continue  # another checker got there first
        out.append(row)
    session.commit()
    return out


def list_alerts(session: Session, limit: int = 50) -> list[AlertRow]:
    return list(
        session.scalars(
            select(AlertRow)
            .where(AlertRow.status != "superseded")
            .order_by(AlertRow.sent_at.desc())
            .limit(limit)
        )
    )
