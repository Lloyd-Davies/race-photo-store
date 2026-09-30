"""Read immutable, non-secret build identity baked into an application image."""
import json
from pathlib import Path
import re


def read_build_info(component: str) -> dict:
    try:
        data = json.loads(Path('/app/build-info.json').read_text())
        revision = data['revision']
        if data['component'] == component and re.fullmatch(r'[0-9a-f]{40}', revision):
            return {'component': component, 'revision': revision}
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return {'component': component, 'revision': 'unknown'}
