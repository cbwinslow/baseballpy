"""Kalshi request signing (RSA-PSS, SHA-256): optional, only raises the read budget.

Kalshi signs ``<timestamp ms><METHOD><path without query>`` with the account's private key and
reads the key id, the timestamp and the signature from three headers. The key file is read once,
the signature is made per attempt (a retry minutes later must not reuse an old timestamp), and
nothing secret is ever logged or stored.
"""

import base64
import time
from collections.abc import Callable
from urllib.parse import urlparse

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from baseballpy.core.config import KALSHI_HOST, KalshiAuthConfig
from baseballpy.core.http import HttpClient


class KalshiSigner:
    """Builds the three Kalshi auth headers for one request."""

    def __init__(
        self,
        key_id: str,
        private_key_pem: bytes,
        clock: Callable[[], float] = time.time,
    ) -> None:
        key = serialization.load_pem_private_key(private_key_pem, password=None)
        if not isinstance(key, rsa.RSAPrivateKey):
            raise TypeError("the Kalshi private key must be an RSA key")
        self._key = key
        self._key_id = key_id
        self._clock = clock

    @classmethod
    def from_config(cls, config: KalshiAuthConfig | None = None) -> "KalshiSigner | None":
        """A signer when the user's environment names a key id and an existing key file, else ``None``."""
        config = config or KalshiAuthConfig()
        if not config.configured or config.key_id is None or config.private_key_path is None:
            return None
        return cls(config.key_id, config.private_key_path.read_bytes())

    def headers(self, method: str, url: str) -> dict[str, str]:
        """Auth headers for ``method`` ``url`` (the query string is not signed)."""
        timestamp = str(int(self._clock() * 1000))
        message = (timestamp + method.upper() + urlparse(url).path).encode()
        signature = self._key.sign(
            message,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
            hashes.SHA256(),
        )
        return {
            "KALSHI-ACCESS-KEY": self._key_id,
            "KALSHI-ACCESS-TIMESTAMP": timestamp,
            "KALSHI-ACCESS-SIGNATURE": base64.b64encode(signature).decode(),
        }


def sign_with_environment(http: HttpClient) -> bool:
    """Sign this host's requests when the user's environment has Kalshi credentials; say whether it did."""
    signer = KalshiSigner.from_config()
    if signer is None:
        return False
    http.set_header_hook(KALSHI_HOST, signer.headers)
    return True


__all__ = ["KalshiSigner", "sign_with_environment"]
