from fastapi import FastAPI, Request

from app.routes import admin, cart, checkout, config, downloads, events, health, orders, seo, webhook

app = FastAPI(
    title="PhotoStore API",
    description="Self-hosted sports event photo proofing and sales.",
    version="0.1.0",
)


@app.middleware("http")
async def protect_non_public_documents(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith(("/api/", "/d/")):
        response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    return response

app.include_router(health.router)
app.include_router(seo.router)
app.include_router(config.router)
app.include_router(events.public_router)
app.include_router(events.router)
app.include_router(cart.router)
app.include_router(checkout.router)
app.include_router(orders.router)
app.include_router(downloads.router)
app.include_router(webhook.router)
app.include_router(admin.router)
