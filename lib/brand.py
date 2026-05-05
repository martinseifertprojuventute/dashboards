"""
Brand color palette.

Three tiers, seven hues — use these constants in every chart instead
of plotly defaults so the app stays on-brand.

Usage rules:

1. **Primary accent = yellow** (`BRAND_YELLOW = #ffc300`). Reserved for
   branded elements: Streamlit theme (handled via .streamlit/config.toml),
   KPI highlight, focal chart color for the single most important
   series on a page.

2. **Categorical** encoding uses `CATEGORICAL` (primary-tier palette
   ordered yellow → green → blue → red → purple → pink → brown). For
   more than 7 categories, extend with SECONDARY_CATEGORICAL or fall
   back to plotly's `Plotly` qualitative scale.

3. **Sequential / gradient** scales use one of `SEQUENTIAL_GREEN`,
   `SEQUENTIAL_BLUE`, `SEQUENTIAL_BROWN`, etc. — NOT yellow. Gradients
   diverge from the primary color so yellow stays recognizable as the
   discrete brand accent.

4. **Semantic pairs** for two-series comparisons: `SEMANTIC_POSITIVE`
   (green) vs `SEMANTIC_NEGATIVE` (red); or `SEMANTIC_NEUTRAL` (blue)
   vs `SEMANTIC_WARNING` (red).

Plotly integration examples::

    import plotly.express as px
    from lib.brand import CATEGORICAL, SEQUENTIAL_GREEN

    fig = px.line(df, x="x", y="y", color="category",
                  color_discrete_sequence=CATEGORICAL)

    fig = px.imshow(matrix, color_continuous_scale=SEQUENTIAL_GREEN)
"""

from __future__ import annotations

# ----- Primary tier (saturated) -----
BRAND_YELLOW = "#ffc300"  # primary accent — reserved for branded/focal elements
BRAND_GREEN = "#146e5a"
BRAND_RED = "#b93c50"
BRAND_BLUE = "#3c6ea0"
BRAND_PURPLE = "#5a4696"
BRAND_BROWN = "#82786e"
BRAND_PINK = "#b93278"

# ----- Secondary tier (medium) -----
BRAND_YELLOW_2 = "#ffdc82"
BRAND_GREEN_2 = "#00a582"
BRAND_RED_2 = "#ff5a64"
BRAND_BLUE_2 = "#00aaf0"
BRAND_PURPLE_2 = "#8c82c8"
BRAND_BROWN_2 = "#b9aa96"
BRAND_PINK_2 = "#e164a5"

# ----- Tertiary tier (light / pastel) -----
BRAND_YELLOW_3 = "#ffe7a3"
BRAND_GREEN_3 = "#96dcc8"
BRAND_RED_3 = "#ffa5a0"
BRAND_BLUE_3 = "#73d7fa"
BRAND_PURPLE_3 = "#c3bef0"
BRAND_BROWN_3 = "#e6dccd"
BRAND_PINK_3 = "#ffa0cd"

# ----- Categorical sequences (for color_discrete_sequence) -----
CATEGORICAL: list[str] = [
    BRAND_YELLOW,
    BRAND_GREEN,
    BRAND_BLUE,
    BRAND_RED,
    BRAND_PURPLE,
    BRAND_PINK,
    BRAND_BROWN,
]

SECONDARY_CATEGORICAL: list[str] = [
    BRAND_YELLOW_2,
    BRAND_GREEN_2,
    BRAND_BLUE_2,
    BRAND_RED_2,
    BRAND_PURPLE_2,
    BRAND_PINK_2,
    BRAND_BROWN_2,
]

TERTIARY_CATEGORICAL: list[str] = [
    BRAND_YELLOW_3,
    BRAND_GREEN_3,
    BRAND_BLUE_3,
    BRAND_RED_3,
    BRAND_PURPLE_3,
    BRAND_PINK_3,
    BRAND_BROWN_3,
]

# Extended palette (14 distinct colors — primary + secondary tiers)
# for stacked bars with many categories.
CATEGORICAL_EXTENDED: list[str] = CATEGORICAL + SECONDARY_CATEGORICAL

# ----- Sequential color scales (for color_continuous_scale) -----
# Each scale goes light → dark within ONE hue.

SEQUENTIAL_YELLOW: list[str] = [BRAND_YELLOW_3, BRAND_YELLOW_2, BRAND_YELLOW]
SEQUENTIAL_GREEN: list[str] = [BRAND_GREEN_3, BRAND_GREEN_2, BRAND_GREEN]
SEQUENTIAL_BLUE: list[str] = [BRAND_BLUE_3, BRAND_BLUE_2, BRAND_BLUE]
SEQUENTIAL_RED: list[str] = [BRAND_RED_3, BRAND_RED_2, BRAND_RED]
SEQUENTIAL_PURPLE: list[str] = [BRAND_PURPLE_3, BRAND_PURPLE_2, BRAND_PURPLE]
SEQUENTIAL_BROWN: list[str] = [BRAND_BROWN_3, BRAND_BROWN_2, BRAND_BROWN]
SEQUENTIAL_PINK: list[str] = [BRAND_PINK_3, BRAND_PINK_2, BRAND_PINK]

# ----- Semantic aliases -----
SEMANTIC_POSITIVE = BRAND_GREEN  # retention, growth, won, active
SEMANTIC_NEGATIVE = BRAND_RED  # lost, returned, churned, inactive
SEMANTIC_NEUTRAL = BRAND_BLUE  # informational, "just a count"
SEMANTIC_WARNING = BRAND_RED_2  # attention-needed but not fatal
SEMANTIC_ACCENT = BRAND_YELLOW  # the one branded/focal series on a page
