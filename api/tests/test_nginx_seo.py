from pathlib import Path


def test_nginx_routes_seo_documents_before_genuine_static_404_fallback():
    config = (Path(__file__).parents[2] / "nginx" / "nginx.conf").read_text(encoding="utf-8")
    # Ordering matters within the public listener, not the separate internal one.
    config = config.split("listen 8080;", 1)[1]

    assert "location = /robots.txt" in config
    assert "location = /sitemap.xml" in config
    assert "location ^~ /covers/" in config
    assert "try_files $uri =404;" in config
    assert "try_files $uri $uri/ /index.html" not in config
    assert config.index("location = /robots.txt") < config.index("location / {")
