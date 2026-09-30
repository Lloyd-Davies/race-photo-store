from unittest.mock import patch


def test_internal_metadata_reports_only_build_identities(client):
    from app.routes import health
    identity = {'component': 'worker', 'revision': 'b' * 40, 'secret': 'must-not-leave'}
    with patch.object(health, 'read_build_info', return_value={'component': 'api', 'revision': 'a' * 40}), \
         patch.object(health.celery_app.control, 'broadcast', return_value=[{'worker-host': identity}]) as inspect:
        response = client.get('/internal/build-info')
    assert response.status_code == 200
    assert response.json() == {'api': {'component': 'api', 'revision': 'a' * 40},
                               'workers': [{'component': 'worker', 'revision': 'b' * 40}]}
    inspect.assert_called_once_with('photostore_build_info', reply=True, timeout=2)
    assert 'worker-host' not in response.text
    assert 'secret' not in response.text


def test_missing_workers_does_not_hide_api_identity(client):
    from app.routes import health
    with patch.object(health.celery_app.control, 'broadcast', side_effect=ConnectionError):
        response = client.get('/internal/build-info')
    assert response.status_code == 200
    assert response.json()['workers'] == []


def test_baked_identity_is_required_and_runtime_environment_cannot_override_it(monkeypatch):
    from photostore import build_info
    monkeypatch.setenv('BUILD_REVISION', 'c' * 40)
    with patch.object(build_info.Path, 'read_text', return_value='{"component":"api","revision":"' + 'a' * 40 + '"}'):
        assert build_info.read_build_info('api')['revision'] == 'a' * 40
        assert build_info.read_build_info('worker')['revision'] == 'unknown'
    with patch.object(build_info.Path, 'read_text', side_effect=FileNotFoundError):
        assert build_info.read_build_info('api')['revision'] == 'unknown'
