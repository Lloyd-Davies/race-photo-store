"""Email provider abstraction.

get_provider() returns either a BrevoProvider (live sending) or NoopProvider
(when EMAIL_ENABLED=False). The rest of the application only calls .send().
"""

from __future__ import annotations

from dataclasses import dataclass


class ProviderError(Exception):
    """Raised when the email provider returns a non-success response."""


@dataclass
class EmailMessage:
    to_email: str
    to_name: str
    subject: str
    html_body: str
    text_body: str
    from_email: str
    from_name: str


class BrevoProvider:
    _API_URL = "https://api.brevo.com/v3/smtp/email"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def send(self, msg: EmailMessage) -> str:
        """Send via Brevo HTTP API. Returns provider message ID."""
        import httpx

        payload = {
            "sender": {"name": msg.from_name, "email": msg.from_email},
            "to": [{"email": msg.to_email, "name": msg.to_name}],
            "subject": msg.subject,
            "htmlContent": msg.html_body,
            "textContent": msg.text_body,
            "trackClicks": False,
            "trackOpens": False,
        }
        headers = {
            "api-key": self._api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        resp = httpx.post(self._API_URL, json=payload, headers=headers, timeout=10.0)

        if resp.status_code not in (200, 201):
            raise ProviderError(
                f"Brevo returned {resp.status_code}: {resp.text[:200]}"
            )

        data = resp.json()
        return data.get("messageId", "")


class NoopProvider:
    """Used when EMAIL_ENABLED=False. Logs intent but does not send."""

    def send(self, msg: EmailMessage) -> str:
        import logging
        logging.getLogger(__name__).info(
            "EMAIL_ENABLED=False — suppressed %s to %s", msg.subject, msg.to_email
        )
        return "noop"


def get_provider() -> BrevoProvider | NoopProvider:
    from .config import settings

    if not settings.EMAIL_ENABLED:
        return NoopProvider()

    if not settings.BREVO_API_KEY:
        raise ProviderError("BREVO_API_KEY is not configured")

    return BrevoProvider(settings.BREVO_API_KEY)
