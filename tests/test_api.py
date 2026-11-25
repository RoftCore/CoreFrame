"""The HTTP surface: auth, health, scenes and widget state.

These run against the real application object, not a stub: the routes are
registered by importing coreframe.app, so a broken registration fails here.
"""


def test_token_is_served(client):
    response = client.get('/api/token')
    assert response.status_code == 200
    token = response.get_json()['token']
    assert isinstance(token, str)
    assert len(token) == 16


def test_public_endpoints_need_no_token(app_module):
    """`/api/token` and `/api/health` are open on purpose: the second-instance
    handshake and the connection dot poll them before a token exists."""
    anonymous = app_module.app.test_client()
    assert anonymous.get('/api/token').status_code == 200
    assert anonymous.get('/api/health').status_code == 200


def test_every_other_api_path_is_403_without_token(app_module):
    anonymous = app_module.app.test_client()
    for path in ('/api/extensions', '/api/scenes', '/api/widget-state',
                 '/api/marketplace/list', '/api/extensions/health'):
        assert anonymous.get(path).status_code == 403, path


def test_health_reports_version(client):
    from coreframe.config import APP_VERSION
    payload = client.get('/api/health').get_json()
    assert payload['status'] == 'ok'
    assert payload['version'] == APP_VERSION
    assert 'extensions' in payload
    assert 'clients' in payload


def test_extensions_endpoint_returns_an_object(client):
    payload = client.get('/api/extensions').get_json()
    assert isinstance(payload, dict)


def test_scene_roundtrip(client):
    created = client.post('/api/scenes').get_json()
    assert created['ok'] is True
    assert created['id'].startswith('scene_')

    scenes = client.get('/api/scenes').get_json()
    assert created['id'] in scenes['scenes']
    assert scenes['scenes'][created['id']]['cols'] == 12
    assert scenes['active'] in scenes['scenes']


def test_widget_state_roundtrip(client):
    payload = {
        'scenes': {'only': {'label': 'home', 'name': 'Only', 'cols': 12, 'rows': 6, 'widgets': {}}},
        'activeScene': 'only',
        'sceneOrder': ['only'],
    }
    assert client.post('/api/widget-state', json=payload).status_code == 200

    back = client.get('/api/widget-state').get_json()
    assert back['activeScene'] == 'only'
    assert 'only' in back['scenes']


def test_unknown_extension_action_is_404(client):
    response = client.get('/api/extension/not_installed/get_value')
    assert response.status_code == 404
