"""Reusable hierarchy filter UI for dashboard pages.

Turns a DataFrame of distinct N-level hierarchy rows into a nested
`streamlit-tree-select` tree with search, "All"/"None" buttons, and
returns a SQL WHERE fragment that other code can splice into its
templates.

Drop this in for any page with a multi-level hierarchy (different number
of levels, different column names, different table alias).

Usage::

    import pandas as pd
    import streamlit as st
    from lib.hierarchy_filter import render_hierarchy_filter

    df = load_distinct_hierarchy_rows()  # caller is responsible for caching

    with st.sidebar:
        hierarchy_filter = render_hierarchy_filter(
            df,
            level_columns=["LEVEL1", "LEVEL2", "LEVEL3"],
            key_prefix="my_hier",
            table_alias="t",
            label="Hierarchy",
        )

    # hierarchy_filter is now a string like "1=1", "1=0", or
    # "(t.LEVEL1 = 'A' AND t.LEVEL2 = 'B') OR ..."
    # → splice into your SQL templates alongside other WHERE fragments.
"""

from __future__ import annotations

import json
from typing import Sequence

import pandas as pd
import streamlit as st
from streamlit_tree_select import tree_select


__all__ = [
    "render_hierarchy_filter",
    "build_hierarchy_tree",
    "build_hierarchy_sql_filter",
    "filter_tree_by_query",
    "collect_node_values",
    "collect_match_values",
]


def build_hierarchy_tree(
    df: pd.DataFrame,
    level_columns: Sequence[str],
    *,
    max_label_chars: int | None = 30,
) -> tuple[list[dict], list[str]]:
    """Build nested tree nodes from a DataFrame of distinct hierarchy rows.

    Each node's `value` is a JSON-encoded path tuple (e.g. '["A","B"]'),
    which is both unique and parseable back into the level segments when
    the SQL filter is built. The `title` attribute holds the full label
    so browsers render a native hover tooltip for truncated nodes.

    Parameters
    ----------
    df, level_columns
        See `render_hierarchy_filter` — caller supplies a distinct-rows
        DataFrame and an ordered list of column names.
    max_label_chars : int | None, default 30
        If set, labels longer than this will be truncated to
        ``max_label_chars - 1`` characters + ``"…"``. The original full
        label is always preserved in the node's `title` attribute so a
        hover tooltip reveals it. Pass None to disable truncation.
        Truncation exists because streamlit-tree-select's iframe doesn't
        wrap long labels and the sidebar width is finite.

    Returns
    -------
    (nodes, all_values) where `all_values` is the flat list of every
    node's value — useful as a default `checked` argument to make the
    tree start fully selected.
    """
    levels = list(level_columns)
    root: dict = {}
    for _, row in df.iterrows():
        path: list[str] = []
        for lvl in levels:
            v = row.get(lvl)
            if pd.isna(v) or v is None or str(v).strip() == "":
                break
            path.append(str(v).strip())
        node = root
        for name in path:
            node = node.setdefault(name, {})

    all_values: list[str] = []

    def _shorten(name: str) -> str:
        if max_label_chars is None or len(name) <= max_label_chars:
            return name
        return name[: max_label_chars - 1] + "…"

    def to_nodes(d: dict, prefix: list[str]) -> list:
        result = []
        for name in sorted(d.keys()):
            path = prefix + [name]
            value = json.dumps(path, ensure_ascii=False)
            all_values.append(value)
            children = to_nodes(d[name], path)
            entry = {"label": _shorten(name), "value": value, "title": name}
            if children:
                entry["children"] = children
            result.append(entry)
        return result

    nodes = to_nodes(root, [])
    return nodes, all_values


def filter_tree_by_query(nodes: list, query: str) -> list:
    """Return a pruned copy of `nodes` keeping only branches whose label
    (or any descendant's label) matches the case-insensitive query.

    If a node's own label matches, its full subtree is kept so the user
    can still drill in.
    """
    q = query.lower().strip()
    if not q:
        return nodes
    result = []
    for node in nodes:
        if q in node["label"].lower():
            result.append(node)
            continue
        children = node.get("children", [])
        pruned = filter_tree_by_query(children, query) if children else []
        if pruned:
            entry = {k: v for k, v in node.items() if k != "children"}
            entry["children"] = pruned
            result.append(entry)
    return result


def collect_node_values(nodes: list) -> set[str]:
    """Recursively collect every node's `value` (including children) into a set."""
    out: set[str] = set()

    def walk(ns: list) -> None:
        for n in ns:
            out.add(n["value"])
            children = n.get("children")
            if children:
                walk(children)

    walk(nodes)
    return out


def collect_match_values(nodes: list, query: str) -> set[str]:
    """Return the set of values of nodes that semantically *match* a search query.

    A node matches if its own label contains the query (case-insensitive)
    OR any of its ancestors matches — i.e. the node is part of an
    "in-match" subtree.

    Importantly, nodes kept only as **structural wrappers** in the
    visible tree (their own label does not match but a descendant's
    does) are NOT included. Without this distinction, intersecting the
    user's checked state with `visible_values` would let an ancestor
    wrapper sneak into the SQL filter — and dedup-by-shortest-prefix
    would then collapse the entire filter to that ancestor, undoing the
    search narrowing.

    With an empty query, returns every value in `nodes` (no filter).
    """
    q = query.lower().strip()
    if not q:
        return collect_node_values(nodes)

    out: set[str] = set()

    def walk(ns: list, in_match: bool) -> None:
        for n in ns:
            label_match = q in n["label"].lower()
            if in_match or label_match:
                out.add(n["value"])
                walk(n.get("children", []), True)
            else:
                walk(n.get("children", []), False)

    walk(nodes, False)
    return out


def build_hierarchy_sql_filter(
    checked: list[str],
    all_values: list[str],
    *,
    level_columns: Sequence[str],
    table_alias: str | None = None,
    allow_no_op: bool = True,
) -> str:
    """Convert a list of checked tree node values into a SQL WHERE fragment.

    Each checked value is a JSON-encoded path. The result is an OR of
    (LEVEL1='A' AND LEVEL2='B' AND ...) predicates, with ancestors-already
    -selected pruned away so the SQL stays compact.

    Semantics:
      empty selection        → '1=0' (exclude everything)
      every node selected    → '1=1' (no filter, *unless* `allow_no_op`
                                is False — in which case an OR of the
                                topmost L1 predicates is emitted so the
                                fragment still constrains the query to
                                the node set known to the tree)
      partial selection      → OR of path predicates

    `allow_no_op=False` is used when the caller's SQL deliberately does
    NOT apply the same upstream filter (e.g. the Mailings page removed
    its `k.DATUM_START BETWEEN …` clause because the hierarchy tree is
    already date-scoped). In that case "1=1" would accidentally widen
    the query to the entire fact table.
    """
    if not checked:
        return "1=0"

    if set(checked) >= set(all_values):
        if allow_no_op:
            return "1=1"
        # Fall through: emit explicit predicates for every checked path.
        # The dedup logic below collapses them to topmost (L1) entries.

    levels = list(level_columns)
    prefix = f"{table_alias}." if table_alias else ""

    paths = sorted((json.loads(v) for v in checked), key=len)
    minimal: list[list[str]] = []
    for p in paths:
        if any(len(m) <= len(p) and p[: len(m)] == m for m in minimal):
            continue
        minimal.append(p)

    predicates = []
    for p in minimal:
        parts = []
        for i, name in enumerate(p):
            col = levels[i]
            escaped = name.replace("'", "''")
            parts.append(f"{prefix}{col} = '{escaped}'")
        predicates.append("(" + " AND ".join(parts) + ")")

    return "(" + " OR ".join(predicates) + ")"


def render_hierarchy_filter(
    df: pd.DataFrame,
    *,
    level_columns: Sequence[str],
    key_prefix: str,
    table_alias: str | None = None,
    label: str = "Hierarchy",
    search_placeholder: str = "Search …",
    select_all_label: str = "All",
    select_none_label: str = "None",
    empty_message: str = "_No matches._",
    max_label_chars: int | None = 30,
    allow_no_op: bool = True,
    debug: bool = False,
) -> str:
    """Render the hierarchy filter UI at the current Streamlit context and
    return a SQL WHERE fragment.

    Caller should wrap the call in `with st.sidebar:` (or similar) if a
    specific placement is desired. All widget keys are scoped by the
    `key_prefix` argument so multiple hierarchy filters can live on the
    same page without clashing.

    Parameters
    ----------
    df : pd.DataFrame
        One row per distinct hierarchy combination. Must contain the
        `level_columns`.
    level_columns : Sequence[str]
        Ordered column names, top level first. Shorter-than-max paths
        (trailing NULLs) are handled automatically.
    key_prefix : str
        Unique prefix for all widget/session-state keys produced by this
        filter. Use something like "mailings_hier".
    table_alias : str, optional
        SQL table alias to prepend to column names in the returned
        fragment — e.g. "k" gives "k.HIERARCHIE_LEVEL1 = '…'". Pass None
        if the caller's query has no alias.
    label, search_placeholder, select_all_label, select_none_label,
    empty_message : str
        User-facing strings.

    Returns
    -------
    str
        A SQL WHERE fragment. Special cases: "1=1" (all selected, no
        filter), "1=0" (nothing selected). Otherwise an OR of per-path
        conjunctions.
    """
    nodes, all_values = build_hierarchy_tree(
        df, level_columns, max_label_chars=max_label_chars
    )

    counter_key = f"{key_prefix}_counter"
    default_key = f"{key_prefix}_default_checked"
    search_key = f"{key_prefix}_search"
    btn_all_key = f"{key_prefix}_btn_all"
    btn_none_key = f"{key_prefix}_btn_none"

    if counter_key not in st.session_state:
        st.session_state[counter_key] = 0
        st.session_state[default_key] = all_values

    st.caption(f"**{label}**")

    search = st.text_input(
        label,
        placeholder=search_placeholder,
        key=search_key,
        label_visibility="collapsed",
    ) or ""

    col_all, col_none = st.columns(2)
    if col_all.button(
        select_all_label, use_container_width=True, key=btn_all_key
    ):
        st.session_state[counter_key] += 1
        st.session_state[default_key] = all_values
    if col_none.button(
        select_none_label, use_container_width=True, key=btn_none_key
    ):
        st.session_state[counter_key] += 1
        st.session_state[default_key] = []

    visible = filter_tree_by_query(nodes, search)

    if not visible:
        st.caption(empty_message)
        checked = st.session_state[default_key]
    else:
        counter = st.session_state[counter_key]
        widget_key = f"{key_prefix}_tree_{counter}"
        # Pass the widget's *previous* state back as `checked` on every
        # rerun. If react-checkbox-tree treats `checked` as a controlled
        # prop, this prevents user clicks from being reverted to the
        # original default on the next rerender. On first mount
        # session_state has no entry for the key yet, so we fall back to
        # the configured default.
        prev_state = st.session_state.get(widget_key)
        if isinstance(prev_state, dict) and "checked" in prev_state:
            initial_checked = prev_state["checked"]
        else:
            initial_checked = st.session_state[default_key]
        state = tree_select(
            visible,
            checked=initial_checked,
            show_expand_all=True,
            key=widget_key,
        )
        checked = state.get("checked", []) if isinstance(state, dict) else []

    # Treat the search box as a true filter, not just a visual narrower:
    # the effective selection is the intersection of the user's checked
    # state with the values that *actually* match the search query.
    #
    # We use `collect_match_values` (not `collect_node_values(visible)`)
    # because the visible tree includes structural ancestor wrappers
    # whose label doesn't match the query — those wrappers must NOT be
    # part of the SQL filter, otherwise dedup-by-shortest-prefix would
    # collapse the filter to the wrapper's ancestor (e.g. "L1=PFR 2026"
    # instead of "L3=DM 2603 Kinderbuch"), undoing the search narrowing.
    #
    # When search is empty, this returns every value, so the
    # intersection is a no-op and the SQL behaves as if no search were
    # active.
    visible_values = collect_match_values(nodes, search)
    effective_checked = [v for v in checked if v in visible_values]

    sql = build_hierarchy_sql_filter(
        effective_checked,
        all_values,
        level_columns=level_columns,
        table_alias=table_alias,
        allow_no_op=allow_no_op,
    )

    if debug:
        st.caption(
            f"`debug` search={search!r} | "
            f"all={len(all_values)} | "
            f"visible={len(visible_values)} | "
            f"checked={len(checked)} | "
            f"effective={len(effective_checked)}"
        )
        st.caption(f"first 5 checked: {checked[:5]}")
        st.caption(f"first 5 effective: {effective_checked[:5]}")
        st.code(sql[:600] + ("…" if len(sql) > 600 else ""), language="sql")

    return sql
