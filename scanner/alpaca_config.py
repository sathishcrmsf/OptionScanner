"""Utility module to load Alpaca API credentials.

The module reads the following environment variables:
- ``APCA_API_KEY_ID`` – your Alpaca API key.
- ``APCA_API_SECRET_KEY`` – your Alpaca secret.
- ``APCA_API_BASE_URL`` – base URL (paper: ``https://paper-api.alpaca.markets``;
  live: ``https://api.alpaca.markets``). If not set, the paper URL is used by default.

Usage::

    from alpaca_config import get_alpaca_credentials
    creds = get_alpaca_credentials()
    # creds = {"key_id": ..., "secret_key": ..., "base_url": ...}

The function raises ``RuntimeError`` if the required variables are missing.
"""

import os
from dataclasses import dataclass

@dataclass(frozen=True)
class AlpacaCredentials:
    key_id: str
    secret_key: str
    base_url: str

def get_alpaca_credentials() -> AlpacaCredentials:
    """Read Alpaca credentials from environment variables.

    Returns
    -------
    AlpacaCredentials
        A frozen dataclass with the three required fields.

    Raises
    ------
    RuntimeError
        If ``APCA_API_KEY_ID`` or ``APCA_API_SECRET_KEY`` is not defined.
    """
    key_id = os.getenv("APCA_API_KEY_ID")
    secret_key = os.getenv("APCA_API_SECRET_KEY")
    base_url = os.getenv("APCA_API_BASE_URL", "https://paper-api.alpaca.markets")

    if not key_id or not secret_key:
        raise RuntimeError(
            "Alpaca API credentials not found. Set APCA_API_KEY_ID and APCA_API_SECRET_KEY in your environment."
        )
    return AlpacaCredentials(key_id=key_id, secret_key=secret_key, base_url=base_url)
