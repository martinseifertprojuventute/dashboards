"""
Role-based page gating.

Each page calls `require_role("Page Name", ["ROLE_A", "ROLE_B"])` at the top.
If the caller's Snowflake role isn't in the allowed list, the page renders
an access-denied message and stops further execution.

Role resolution uses CURRENT_ROLE() on the caller's Snowpark session, which
in SPCS maps to the OAuth token's identity. Cached for 5 minutes to avoid
hammering Snowflake on every rerun.

Notes:
  - Include the role(s) you actually use during development in your
    allowed_roles list, or local dev pages will be blocked.
  - Role-level gating is a user-facing nicety. Snowflake's row-level security
    and masking policies are the real enforcement layer — all queries run as
    the calling user.
"""

from __future__ import annotations

import streamlit as st

from .snowflake import get_session


@st.cache_data(ttl=300, show_spinner=False)
def get_current_role() -> str:
    """Return the Snowflake role the current session is running as."""
    row = get_session().sql("SELECT CURRENT_ROLE()").collect()[0]
    return row[0] or ""


def require_role(page_name: str, allowed_roles: list[str]) -> None:
    """Gate a page on Snowflake role membership.

    Call at the top of a page. If the current role isn't in allowed_roles,
    shows an access-denied message and halts the page via st.stop().

    Including ``"PUBLIC"`` in ``allowed_roles`` is a wildcard: PUBLIC is
    granted implicitly to every Snowflake user, so the page is accessible
    to anyone who can reach it.
    """
    if "PUBLIC" in allowed_roles:
        return
    role = get_current_role()
    if role not in allowed_roles:
        st.error(
            f"**Zugriff verweigert — {page_name}**  \n"
            f"Diese Seite erfordert eine der folgenden Rollen: "
            f"`{', '.join(allowed_roles)}`  \n"
            f"Ihre aktuelle Rolle: `{role or '(keine)'}`",
            icon=":material/lock:",
        )
        st.stop()
