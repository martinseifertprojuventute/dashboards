"""
Snowpark session builder for the dashboards app.

Supports two environments:

  - SPCS (production): reads the OAuth token file that Snowflake injects at
    /snowflake/session/token and connects via the SNOWFLAKE_HOST /
    SNOWFLAKE_ACCOUNT env vars. The token refreshes automatically and
    Snowpark re-reads it on reconnection.

  - Local dev: reads a named profile from ~/.snowflake/connections.toml
    and explicitly loads the private key file (if the profile uses keypair
    auth). Profile name comes from the SNOWFLAKE_CONNECTION env var
    (default: "default"). We do NOT use Snowpark's
    `Session.builder.config("connection_name", ...)` shortcut because it
    does not translate `private_key_path` into loaded `private_key` bytes
    — the connector then fails authentication with
    `TypeError: Expected bytes or RSAPrivateKey, got NoneType`. Loading
    the key ourselves avoids the shortcut's gap.

Detection: if /snowflake/session/token exists OR SNOWFLAKE_HOST is set,
we're in SPCS. Otherwise, local dev.

The session is cached per Streamlit worker via @st.cache_resource so
multiple reruns and multiple pages share a single Snowpark session.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

import streamlit as st
from snowflake.snowpark import Session

SPCS_TOKEN_PATH = Path("/snowflake/session/token")
LOCAL_CONNECTIONS_TOML = Path.home() / ".snowflake" / "connections.toml"


def _is_spcs() -> bool:
    """Return True if we're running inside an SPCS container."""
    return SPCS_TOKEN_PATH.exists() or "SNOWFLAKE_HOST" in os.environ


def _spcs_config() -> dict:
    """Build Snowpark session config from SPCS-injected env vars + token file.

    Warehouse / database / schema fall back to env vars set on the SPCS
    service spec; if not set, Snowflake uses the role's defaults.
    """
    token = SPCS_TOKEN_PATH.read_text().strip()
    config = {
        "host": os.environ["SNOWFLAKE_HOST"],
        "account": os.environ["SNOWFLAKE_ACCOUNT"],
        "authenticator": "oauth",
        "token": token,
    }
    for env_key, cfg_key in (
        ("SNOWFLAKE_WAREHOUSE", "warehouse"),
        ("SNOWFLAKE_DATABASE", "database"),
        ("SNOWFLAKE_SCHEMA", "schema"),
    ):
        if env_key in os.environ:
            config[cfg_key] = os.environ[env_key]
    return config


def _load_local_config(profile: str) -> dict:
    """Read ~/.snowflake/connections.toml and return a Snowpark-ready config dict.

    Handles both connections.toml layouts:
      1. Top-level section:  [default]  with `default_connection_name = "default"`
      2. Nested section:     [connections.default]

    If the profile uses keypair auth (has `private_key_path`), the key file
    is loaded and decoded to PKCS#8 DER bytes, which is what the connector's
    keypair authenticator expects as `private_key`. The `private_key_path`
    and `private_key_passphrase` toml fields are dropped from the final
    config — the connector only wants the loaded bytes, not the path.
    """
    if not LOCAL_CONNECTIONS_TOML.exists():
        raise FileNotFoundError(
            f"No connections.toml at {LOCAL_CONNECTIONS_TOML}. "
            f"Run `snow connection add` or create one manually."
        )

    with open(LOCAL_CONNECTIONS_TOML, "rb") as f:
        data = tomllib.load(f)

    profiles = data.get("connections", {})
    if profile in profiles:
        conn = profiles[profile]
    elif profile in data and isinstance(data[profile], dict):
        conn = data[profile]
    else:
        raise ValueError(
            f"Profile '{profile}' not found in {LOCAL_CONNECTIONS_TOML}"
        )

    # Strip the path/passphrase fields — we'll replace them with loaded bytes
    config = {
        k: v
        for k, v in conn.items()
        if k not in ("private_key_path", "private_key_passphrase")
    }

    key_path = conn.get("private_key_path")
    if key_path:
        # Imported locally so the import isn't required in SPCS mode
        from cryptography.hazmat.primitives import serialization

        # Env var wins over toml: matches `snow` CLI convention and lets
        # users rotate the passphrase without editing connections.toml.
        passphrase = os.environ.get("PRIVATE_KEY_PASSPHRASE") or conn.get(
            "private_key_passphrase"
        )
        passphrase_bytes = passphrase.encode("utf-8") if passphrase else None
        with open(key_path, "rb") as key_file:
            loaded = serialization.load_pem_private_key(
                key_file.read(),
                password=passphrase_bytes,
            )
        config["private_key"] = loaded.private_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

    return config


@st.cache_resource(show_spinner="Connecting to Snowflake …")
def get_session() -> Session:
    """Return a cached Snowpark session for the current Streamlit worker.

    In SPCS, uses the injected OAuth token.
    Locally, reads a profile from ~/.snowflake/connections.toml via
    _load_local_config() and passes pre-loaded key bytes to Snowpark.
    Profile name comes from SNOWFLAKE_CONNECTION env var (default 'default').
    """
    if _is_spcs():
        return Session.builder.configs(_spcs_config()).create()

    profile = os.environ.get("SNOWFLAKE_CONNECTION", "default")
    return Session.builder.configs(_load_local_config(profile)).create()


def get_snowflake_connector_connection():
    """Return a fresh `snowflake.connector` connection.

    Used by `lib.populate` to stream rows via `fetch_arrow_batches`, which
    Snowpark's `Session` doesn't expose. The connector accepts the same
    config dict shape as Snowpark's `Session.builder.configs`, so we reuse
    `_spcs_config()` / `_load_local_config()` to keep one credentials path.

    The caller owns the connection and must close it.
    """
    import snowflake.connector

    if _is_spcs():
        return snowflake.connector.connect(**_spcs_config())

    profile = os.environ.get("SNOWFLAKE_CONNECTION", "default")
    return snowflake.connector.connect(**_load_local_config(profile))
