"""Process-local presenter access checks for the demo HTTP API."""
import hmac
import os
from collections.abc import Mapping


class PresenterAuth:
    """Require a dedicated presenter secret whenever the server is exposed.

    The controller applies this check to API operations. Static HTML can load
    first so the presenter may enter the key. No credential is written or logged.
    """

    def __init__(self, host: str, environ: Mapping[str, str] | None = None) -> None:
        environment = os.environ if environ is None else environ
        configured = environment.get('LIVE_PRESENTER_KEY', '')
        if not isinstance(configured, str):
            raise ValueError('LIVE_PRESENTER_KEY must be a nonempty string')
        try:
            self._key = configured.encode('utf-8') if configured.strip() else None
        except UnicodeEncodeError:
            raise ValueError('LIVE_PRESENTER_KEY must be valid UTF-8') from None
        if self._key is None and host.casefold() not in ('127.0.0.1', 'localhost', '::1'):
            raise ValueError('LIVE_PRESENTER_KEY is required for a non-loopback host')

    @property
    def required(self) -> bool:
        return self._key is not None

    def authorized(self, headers) -> bool:
        if self._key is None:
            return True
        values = [value for name, value in headers.items()
                  if isinstance(name, str) and name.casefold() == 'x-presenter-key']
        if len(values) != 1 or not isinstance(values[0], str):
            return False
        try:
            supplied = values[0].encode('utf-8')
        except UnicodeEncodeError:
            return False
        return hmac.compare_digest(self._key, supplied)
