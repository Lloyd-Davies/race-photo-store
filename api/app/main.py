from fastapi import FastAPI

from app.routes import admin, cart, checkout, config, downloads, events, health, orders, webhook

app = FastAPI(
    title="PhotoStore API",
    description="Self-hosted sports event photo proofing and sales.",
    version="0.1.0",
)

app.include_router(health.router)
app.include_router(config.router)
app.include_router(events.router)
app.include_router(cart.router)
app.include_router(checkout.router)
app.include_router(orders.router)
app.include_router(downloads.router)
app.include_router(webhook.router)
app.include_router(admin.router)
