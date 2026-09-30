"""Assert the standalone Compose definition cannot inherit production settings."""
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
environment = dict(os.environ)
for key in ("ADMIN_TOKEN", "STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET", "BREVO_API_KEY", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "CLOUDFLARE_TUNNEL_TOKEN", "IMAGE_TAG"):
    environment[key] = "hostile-environment-must-not-be-inherited"
environment["EMAIL_ENABLED"] = "true"
environment["STORAGE_BACKEND"] = "r2"
environment["COMPOSE_FILE"] = "docker-compose.yml"
environment["COMPOSE_PROJECT_NAME"] = "production-must-not-be-used"
environment["DOCKER_CONTEXT"] = "production-must-not-be-used"
result = subprocess.run(["docker", "--context", "desktop-linux", "compose", "--env-file", "scripts/local.env", "-p", "race-photo-local", "-f", "compose.local.yml", "config", "--format", "json"], cwd=ROOT, env=environment, check=True, capture_output=True, text=True)
config = json.loads(result.stdout)
assert config["name"] == "race-photo-local"
assert set(config["services"]) == {"postgres", "redis", "api", "worker", "worker-beat", "nginx"}
assert config["networks"]["default"]["internal"] is True
for name, service in config["services"].items():
    assert "container_name" not in service
    assert "env_file" not in service
    assert "hostile-environment-must-not-be-inherited" not in json.dumps(service)
    for mount in service.get("volumes", []):
        if mount["type"] == "bind":
            expected = ROOT / ".localdata" / "collaboration" / "photos"
            assert Path(mount["source"]).resolve() == expected.resolve()
    if name != "nginx":
        assert not service.get("ports")
        assert set(service["networks"]) == {"default"}
for name in ("api", "worker", "worker-beat"):
    values = config["services"][name]["environment"]
    assert values["EMAIL_ENABLED"] == "false"
    assert values["ADMIN_TOKEN"] == "local-only-admin"
    for key in ("STORAGE_BACKEND", "ZIP_STORAGE_BACKEND", "PROOF_STORAGE_BACKEND", "ORIGINAL_STORAGE_BACKEND"):
        assert values[key] == "local"
    for key in ("STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET", "BREVO_API_KEY", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY"):
        assert values[key] == ""
port = config["services"]["nginx"]["ports"]
assert len(port) == 1 and port[0]["host_ip"] == "127.0.0.1" and str(port[0]["published"]) == "18081"
print("PASS: local project, volumes, loopback port, internal application network and integration settings remain isolated under hostile host environment values.")
