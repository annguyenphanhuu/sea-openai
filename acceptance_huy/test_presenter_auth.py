"""Presenter API access checks without external credentials or HTTP mocks."""
from email.message import Message

import pytest

from platform_huy.presenter_auth import PresenterAuth


@pytest.mark.parametrize('host', ['127.0.0.1', 'localhost', '::1'])
def test_loopback_without_key_allows_local_access(host):
    auth = PresenterAuth(host, environ={})
    assert auth.required is False
    assert auth.authorized({}) is True


@pytest.mark.parametrize('host', ['0.0.0.0', '::', '192.168.1.2', 'example.test'])
@pytest.mark.parametrize('environ', [{}, {'LIVE_PRESENTER_KEY': ''}, {'LIVE_PRESENTER_KEY': '   '}])
def test_nonloopback_requires_configured_nonempty_key(host, environ):
    with pytest.raises(ValueError, match='LIVE_PRESENTER_KEY is required'):
        PresenterAuth(host, environ=environ)


@pytest.mark.parametrize('host', ['127.0.0.1', '0.0.0.0'])
def test_configured_key_protects_loopback_and_remote(host):
    auth = PresenterAuth(host, environ={'LIVE_PRESENTER_KEY': 'presenter-test-key'})
    assert auth.required is True
    assert auth.authorized({}) is False
    assert auth.authorized({'X-Presenter-Key': 'wrong-key'}) is False
    assert auth.authorized({'X-Presenter-Key': 'presenter-test-key'}) is True
    assert auth.authorized({'x-presenter-key': 'presenter-test-key'}) is True
    assert auth.authorized({'Authorization': 'Bearer presenter-test-key'}) is False


def test_unicode_key_compares_utf8_bytes():
    auth = PresenterAuth('0.0.0.0', environ={'LIVE_PRESENTER_KEY': 'demo-khoa-\u0111'})
    headers = Message()
    headers['x-presenter-key'] = 'demo-khoa-\u0111'
    assert auth.authorized(headers) is True
    headers.replace_header('x-presenter-key', 'demo-khoa-d')
    assert auth.authorized(headers) is False


def test_openai_api_key_cannot_authorize_presenter():
    with pytest.raises(ValueError, match='LIVE_PRESENTER_KEY is required'):
        PresenterAuth('0.0.0.0', environ={'OPENAI_API_KEY': 'unrelated-test-value'})
    auth = PresenterAuth('0.0.0.0', environ={'LIVE_PRESENTER_KEY': 'presenter', 'OPENAI_API_KEY': 'unrelated-test-value'})
    assert auth.authorized({'X-Presenter-Key': 'unrelated-test-value'}) is False


def test_duplicate_or_nonstring_header_fails_closed():
    auth = PresenterAuth('0.0.0.0', environ={'LIVE_PRESENTER_KEY': 'presenter'})
    headers = Message()
    headers['X-Presenter-Key'] = 'presenter'
    headers['x-presenter-key'] = 'different'
    assert auth.authorized(headers) is False
    assert auth.authorized({'X-Presenter-Key': None}) is False
    assert auth.authorized({'X-Presenter-Key': b'presenter'}) is False


def test_error_message_never_includes_environment_values():
    with pytest.raises(ValueError) as error:
        PresenterAuth('0.0.0.0', environ={'OPENAI_API_KEY': 'do-not-echo-this'})
    assert str(error.value) == 'LIVE_PRESENTER_KEY is required for a non-loopback host'
