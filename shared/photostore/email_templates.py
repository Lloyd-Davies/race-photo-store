"""Email template rendering.

All templates are app-rendered using Jinja2 with autoescaping enabled.
Each render function returns (html: str, text: str).
"""

from __future__ import annotations

from jinja2 import Environment, select_autoescape

_env = Environment(autoescape=select_autoescape(["html", "xml"]))


# ---------------------------------------------------------------------------
# Order confirmed
# ---------------------------------------------------------------------------

_ORDER_CONFIRMED_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Order Confirmed</title></head>
<body style="font-family:sans-serif;max-width:600px;margin:auto;padding:24px">
  <h1>Order Confirmed</h1>
  <p>Hi {{ customer_email }},</p>
  <p>Thanks for your order! We've received your payment for <strong>{{ event_name }}</strong>.</p>
  <p>Your photos are being prepared. We'll email you again as soon as your download is ready.</p>
  <p><strong>Order reference:</strong> #{{ order_id }}</p>
  <p>
    <a href="{{ order_status_url }}">View your order status</a>
  </p>
  <hr>
  <p style="font-size:12px;color:#666">
    {{ site_name }} &mdash; Questions? <a href="mailto:{{ support_email }}">{{ support_email }}</a>
  </p>
</body>
</html>
"""

_ORDER_CONFIRMED_TEXT = """\
Order Confirmed — {{ site_name }}

Hi {{ customer_email }},

Thanks for your order! We have received your payment for {{ event_name }}.

Your photos are being prepared. We will email you again as soon as your download is ready.

Order reference: #{{ order_id }}
Order status: {{ order_status_url }}

Questions? {{ support_email }}
"""


# ---------------------------------------------------------------------------
# Download ready
# ---------------------------------------------------------------------------

_DOWNLOAD_READY_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Your Photos Are Ready</title></head>
<body style="font-family:sans-serif;max-width:600px;margin:auto;padding:24px">
  <h1>Your Photos Are Ready</h1>
  <p>Hi {{ customer_email }},</p>
  <p>Your photos from <strong>{{ event_name }}</strong> are ready to download.</p>
  <p><strong>Order reference:</strong> #{{ order_id }}</p>
  <p>
    <a href="{{ direct_download_url }}" style="background:#2563eb;color:#fff;padding:12px 24px;text-decoration:none;border-radius:4px;display:inline-block">
      Download Your Photos
    </a>
  </p>
  <p>Or <a href="{{ order_status_url }}">view your order status page</a>.</p>
  <p style="font-size:13px;color:#666">
    This link expires {{ download_expires_at }} and can be used up to {{ max_downloads }} time(s).
  </p>
  <hr>
  <p style="font-size:12px;color:#666">
    {{ site_name }} &mdash; Questions? <a href="mailto:{{ support_email }}">{{ support_email }}</a>
  </p>
</body>
</html>
"""

_DOWNLOAD_READY_TEXT = """\
Your Photos Are Ready — {{ site_name }}

Hi {{ customer_email }},

Your photos from {{ event_name }} are ready to download.

Order reference: #{{ order_id }}

Download your photos: {{ direct_download_url }}

Or view your order status: {{ order_status_url }}

This link expires {{ download_expires_at }} and can be used up to {{ max_downloads }} time(s).

Questions? {{ support_email }}
"""


# ---------------------------------------------------------------------------
# Delivery reset
# ---------------------------------------------------------------------------

_DELIVERY_RESET_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Fresh Download Link Issued</title></head>
<body style="font-family:sans-serif;max-width:600px;margin:auto;padding:24px">
  <h1>Fresh Download Link Issued</h1>
  <p>Hi {{ customer_email }},</p>
  <p>A fresh download link has been issued for your order from <strong>{{ event_name }}</strong>.</p>
  <p><strong>Order reference:</strong> #{{ order_id }}</p>
  <p>
    <a href="{{ direct_download_url }}" style="background:#2563eb;color:#fff;padding:12px 24px;text-decoration:none;border-radius:4px;display:inline-block">
      Download Your Photos
    </a>
  </p>
  <p>Or <a href="{{ order_status_url }}">view your order status page</a>.</p>
  <p style="font-size:13px;color:#666">
    This link expires {{ download_expires_at }} and can be used up to {{ max_downloads }} time(s).
  </p>
  <hr>
  <p style="font-size:12px;color:#666">
    {{ site_name }} &mdash; Questions? <a href="mailto:{{ support_email }}">{{ support_email }}</a>
  </p>
</body>
</html>
"""

_DELIVERY_RESET_TEXT = """\
Fresh Download Link Issued — {{ site_name }}

Hi {{ customer_email }},

A fresh download link has been issued for your order from {{ event_name }}.

Order reference: #{{ order_id }}

Download your photos: {{ direct_download_url }}

Or view your order status: {{ order_status_url }}

This link expires {{ download_expires_at }} and can be used up to {{ max_downloads }} time(s).

Questions? {{ support_email }}
"""


# ---------------------------------------------------------------------------
# Public render API
# ---------------------------------------------------------------------------

def _render(html_tpl: str, text_tpl: str, ctx: dict) -> tuple[str, str]:
    return (
        _env.from_string(html_tpl).render(**ctx),
        _env.from_string(text_tpl).render(**ctx),
    )


def render_order_confirmed(ctx: dict) -> tuple[str, str]:
    return _render(_ORDER_CONFIRMED_HTML, _ORDER_CONFIRMED_TEXT, ctx)


def render_download_ready(ctx: dict) -> tuple[str, str]:
    return _render(_DOWNLOAD_READY_HTML, _DOWNLOAD_READY_TEXT, ctx)


def render_delivery_reset(ctx: dict) -> tuple[str, str]:
    return _render(_DELIVERY_RESET_HTML, _DELIVERY_RESET_TEXT, ctx)
