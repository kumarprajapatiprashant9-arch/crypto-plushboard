from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st


st.set_page_config(
    page_title="Pulseboard | Crypto Markets",
    page_icon="C",
    layout="wide",
    initial_sidebar_state="expanded",
)


API_BASE_URL = "https://api.coingecko.com/api/v3"

FEATURED_ASSETS = {
    "bitcoin": "Bitcoin",
    "ethereum": "Ethereum",
    "tether": "Tether",
    "binancecoin": "BNB",
    "solana": "Solana",
    "ripple": "XRP",
    "usd-coin": "USDC",
    "dogecoin": "Dogecoin",
    "cardano": "Cardano",
    "avalanche-2": "Avalanche",
    "chainlink": "Chainlink",
    "polkadot": "Polkadot",
}

CURRENCY_OPTIONS = {
    "usd": ("USD", "$"),
    "eur": ("EUR", "€"),
    "gbp": ("GBP", "£"),
    "jpy": ("JPY", "¥"),
}


class CoinGeckoError(RuntimeError):
    """Raised when the CoinGecko API request fails."""


def get_api_key() -> str | None:
    """Read the optional CoinGecko Demo API key from environment or Streamlit secrets."""
    environment_key = os.getenv("COINGECKO_API_KEY", "").strip()

    if environment_key:
        return environment_key

    try:
        streamlit_key = st.secrets.get("COINGECKO_API_KEY", "")
    except Exception:
        streamlit_key = ""

    streamlit_key = str(streamlit_key).strip()
    return streamlit_key or None


def request_json(
    endpoint: str,
    params: dict[str, Any],
    api_key: str | None = None,
) -> Any:
    """Call CoinGecko and return decoded JSON."""
    headers = {
        "accept": "application/json",
        "user-agent": "crypto-pulseboard/1.0",
    }

    if api_key:
        headers["x-cg-demo-api-key"] = api_key

    try:
        response = requests.get(
            f"{API_BASE_URL}{endpoint}",
            params=params,
            headers=headers,
            timeout=20,
        )
    except requests.RequestException as exc:
        raise CoinGeckoError(f"Network error: {exc}") from exc

    if response.status_code == 429:
        raise CoinGeckoError(
            "CoinGecko rate limit reached. Wait a moment or add a Demo API key."
        )

    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        try:
            details = response.json()
        except ValueError:
            details = response.text[:200]

        raise CoinGeckoError(
            f"CoinGecko returned HTTP {response.status_code}: {details}"
        ) from exc

    try:
        return response.json()
    except ValueError as exc:
        raise CoinGeckoError("CoinGecko returned invalid JSON.") from exc


@st.cache_data(ttl=25, max_entries=48, show_spinner=False)
def fetch_markets(
    vs_currency: str,
    per_page: int,
    api_key: str | None,
) -> tuple[pd.DataFrame, datetime]:
    """Fetch the current market table."""
    payload = request_json(
        "/coins/markets",
        {
            "vs_currency": vs_currency,
            "order": "market_cap_desc",
            "per_page": per_page,
            "page": 1,
            "sparkline": "false",
            "price_change_percentage": "24h",
            "locale": "en",
        },
        api_key,
    )

    if not isinstance(payload, list):
        raise CoinGeckoError("Unexpected market response from CoinGecko.")

    return pd.DataFrame(payload), datetime.now(timezone.utc)


@st.cache_data(ttl=55, max_entries=16, show_spinner=False)
def fetch_global(
    vs_currency: str,
    api_key: str | None,
) -> dict[str, Any]:
    """Fetch global cryptocurrency market statistics."""
    payload = request_json("/global", {}, api_key)

    if not isinstance(payload, dict):
        raise CoinGeckoError("Unexpected global response from CoinGecko.")

    return payload.get("data", {})


@st.cache_data(ttl=25, max_entries=64, show_spinner=False)
def fetch_chart(
    coin_id: str,
    vs_currency: str,
    days: int,
    api_key: str | None,
) -> pd.DataFrame:
    """Fetch historical price data for one cryptocurrency."""
    payload = request_json(
        f"/coins/{coin_id}/market_chart",
        {
            "vs_currency": vs_currency,
            "days": days,
        },
        api_key,
    )

    prices = payload.get("prices", [])

    if not prices:
        return pd.DataFrame(columns=["timestamp", "price", "time"])

    chart = pd.DataFrame(prices, columns=["timestamp", "price"])
    chart["time"] = pd.to_datetime(
        chart["timestamp"],
        unit="ms",
        utc=True,
    )

    return chart


@st.cache_data(ttl=25, max_entries=64, show_spinner=False)
def fetch_snapshot(
    coin_id: str,
    vs_currency: str,
    api_key: str | None,
) -> pd.DataFrame:
    """Fetch one asset when it is not included in the selected market page."""
    payload = request_json(
        "/coins/markets",
        {
            "vs_currency": vs_currency,
            "ids": coin_id,
            "order": "market_cap_desc",
            "per_page": 1,
            "page": 1,
            "sparkline": "false",
            "price_change_percentage": "24h",
            "locale": "en",
        },
        api_key,
    )

    if not isinstance(payload, list):
        raise CoinGeckoError("Unexpected asset response from CoinGecko.")

    return pd.DataFrame(payload)


def numeric(value: Any) -> float | None:
    """Convert a value to float safely."""
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def format_change(value: Any) -> str:
    """Format a percentage change."""
    parsed = numeric(value)

    if parsed is None:
        return "N/A"

    sign = "+" if parsed >= 0 else ""
    return f"{sign}{parsed:.2f}%"


def format_price(value: Any, currency_symbol: str) -> str:
    """Format a cryptocurrency price based on its size."""
    parsed = numeric(value)

    if parsed is None:
        return "N/A"

    if parsed >= 1:
        return f"{currency_symbol}{parsed:,.2f}"

    if parsed >= 0.01:
        return f"{currency_symbol}{parsed:,.4f}".rstrip("0").rstrip(".")

    return f"{currency_symbol}{parsed:,.8f}".rstrip("0").rstrip(".")


def format_compact(value: Any, prefix: str = "") -> str:
    """Format large values using K, M, B, or T."""
    parsed = numeric(value)

    if parsed is None:
        return "N/A"

    absolute_value = abs(parsed)

    units = [
        (1_000_000_000_000, "T"),
        (1_000_000_000, "B"),
        (1_000_000, "M"),
        (1_000, "K"),
    ]

    for divisor, suffix in units:
        if absolute_value >= divisor:
            return f"{prefix}{parsed / divisor:,.2f}{suffix}"

    return f"{prefix}{parsed:,.0f}"


def currency_value(
    data: dict[str, Any],
    field: str,
    currency: str,
) -> float | None:
    """Read a currency-specific value from the global response."""
    mapping = data.get(field, {})

    if not isinstance(mapping, dict):
        return None

    return numeric(mapping.get(currency))


def prepare_market_table(
    markets: pd.DataFrame,
    currency_symbol: str,
) -> pd.DataFrame:
    """Create a clean table for display and CSV export."""
    rows = []

    for _, coin in markets.iterrows():
        rank = numeric(coin.get("market_cap_rank"))
        symbol = str(coin.get("symbol", "")).upper()
        name = str(coin.get("name", "Unknown"))

        rows.append(
            {
                "Rank": int(rank) if rank is not None else None,
                "Asset": f"{name} ({symbol})",
                "Price": format_price(
                    coin.get("current_price"),
                    currency_symbol,
                ),
                "24h Change": format_change(
                    coin.get("price_change_percentage_24h"),
                ),
                "Market Cap": format_compact(
                    coin.get("market_cap"),
                    currency_symbol,
                ),
                "24h Volume": format_compact(
                    coin.get("total_volume"),
                    currency_symbol,
                ),
            }
        )

    return pd.DataFrame(rows)


def render_movers(
    markets: pd.DataFrame,
    ascending: bool,
    currency_symbol: str,
) -> None:
    """Render a compact gainers or losers table."""
    if markets.empty:
        st.info("No market data available.")
        return

    movers = markets.sort_values(
        "price_change_percentage_24h",
        ascending=ascending,
    ).head(5)

    display = pd.DataFrame(
        {
            "Asset": movers["name"].astype(str),
            "Symbol": movers["symbol"].astype(str).str.upper(),
            "Price": movers["current_price"].map(
                lambda value: format_price(value, currency_symbol)
            ),
            "24h": movers["price_change_percentage_24h"].map(format_change),
        }
    )

    st.dataframe(
        display,
        hide_index=True,
        use_container_width=True,
        height=235,
    )


def inject_styles() -> None:
    """Add the dashboard visual style."""
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap');

        :root {
            --ink: #112522;
            --muted: #6b7c78;
            --mint: #00b894;
            --mint-dark: #008f76;
            --cream: #f4f7f4;
            --panel: #ffffff;
            --line: #dce7e1;
            --red: #e05656;
        }

        .stApp {
            background:
                radial-gradient(circle at 86% 5%, rgba(0, 184, 148, 0.12), transparent 24rem),
                radial-gradient(circle at 4% 95%, rgba(242, 201, 76, 0.12), transparent 22rem),
                var(--cream);
            color: var(--ink);
        }

        [data-testid="stSidebar"] {
            background: #102c28;
        }

        [data-testid="stSidebar"] * {
            color: #eef8f2;
        }

        [data-testid="stSidebar"] .stCaption {
            color: #a8c1b8;
        }

        h1, h2, h3 {
            font-family: "Space Grotesk", sans-serif !important;
            color: var(--ink);
            letter-spacing: -0.04em;
        }

        p, label, div {
            font-family: "DM Sans", sans-serif;
        }

        .hero {
            padding: 1.3rem 1.5rem 1.5rem;
            border: 1px solid var(--line);
            border-radius: 24px;
            background:
                linear-gradient(120deg, rgba(255,255,255,0.95), rgba(239,250,244,0.92)),
                var(--panel);
            box-shadow: 0 18px 50px rgba(28, 71, 58, 0.08);
            margin-bottom: 1rem;
        }

        .eyebrow {
            color: var(--mint-dark);
            font-size: 0.75rem;
            font-weight: 700;
            letter-spacing: 0.16em;
            text-transform: uppercase;
        }

        .hero h1 {
            font-size: clamp(2.5rem, 6vw, 5.5rem);
            line-height: 0.95;
            margin: 0.4rem 0;
        }

        .hero p {
            color: var(--muted);
            margin: 0;
            max-width: 680px;
            font-size: 1.05rem;
        }

        .status-pill {
            display: inline-flex;
            align-items: center;
            gap: 0.45rem;
            border-radius: 999px;
            background: #dff8ed;
            color: #087c60;
            font-size: 0.75rem;
            font-weight: 700;
            padding: 0.4rem 0.75rem;
            letter-spacing: 0.08em;
        }

        .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: var(--mint);
            box-shadow: 0 0 0 5px rgba(0, 184, 148, 0.15);
        }

        [data-testid="stMetric"] {
            background: rgba(255, 255, 255, 0.82);
            border: 1px solid var(--line);
            border-radius: 18px;
            padding: 1rem;
            box-shadow: 0 10px 30px rgba(28, 71, 58, 0.05);
        }

        [data-testid="stMetricLabel"] {
            color: var(--muted);
        }

        [data-testid="stMetricValue"] {
            color: var(--ink);
            font-family: "Space Grotesk", sans-serif;
        }

        .section-card {
            background: rgba(255, 255, 255, 0.8);
            border: 1px solid var(--line);
            border-radius: 20px;
            padding: 1rem;
        }

        .sidebar-note {
            border: 1px solid rgba(255,255,255,0.15);
            border-radius: 14px;
            padding: 0.75rem;
            color: #c6ddd4;
            font-size: 0.8rem;
            line-height: 1.45;
        }

        .stButton > button {
            border-radius: 12px;
            border: 1px solid var(--mint);
            background: var(--mint);
            color: white;
            font-weight: 700;
        }

        .stButton > button:hover {
            border-color: var(--mint-dark);
            background: var(--mint-dark);
            color: white;
        }

        [data-testid="stDataFrame"] {
            border-radius: 16px;
            overflow: hidden;
        }

        .positive {
            color: var(--mint-dark);
        }

        .negative {
            color: var(--red);
        }

        footer {
            visibility: hidden;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


inject_styles()

api_key = get_api_key()

st.markdown(
    """
    <div class="hero">
        <div class="eyebrow">Crypto Market Intelligence</div>
        <h1>Pulseboard</h1>
        <p>
            A clean market command center for tracking price, momentum,
            liquidity, and historical trends.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("## Control Room")

    auto_refresh = st.toggle(
        "Automatic refresh",
        value=True,
        help="Refresh the dashboard without manually reloading the page.",
    )

    refresh_seconds = st.slider(
        "Refresh interval",
        min_value=30,
        max_value=300,
        value=60,
        step=30,
        disabled=not auto_refresh,
        help="30 seconds is the lowest recommended interval for the public API.",
    )

    currency = st.selectbox(
        "Display currency",
        options=list(CURRENCY_OPTIONS.keys()),
        format_func=lambda value: CURRENCY_OPTIONS[value][0],
    )

    market_count = st.slider(
        "Assets to display",
        min_value=10,
        max_value=100,
        value=25,
        step=5,
    )

    selected_coin = st.selectbox(
        "Focus asset",
        options=list(FEATURED_ASSETS.keys()),
        format_func=lambda coin_id: FEATURED_ASSETS[coin_id],
    )

    chart_days = st.select_slider(
        "Chart range",
        options=[1, 7, 30, 90],
        value=7,
    )

    if st.button("Refresh data now", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    mode_label = "Demo API key" if api_key else "Keyless public API"

    st.markdown(
        f"""
        <div class="sidebar-note">
            <strong>Data connection</strong><br>
            {mode_label}<br><br>
            CoinGecko REST data is periodically refreshed.
            For production traffic, use a dedicated API key.
        </div>
        """,
        unsafe_allow_html=True,
    )

currency_name, currency_symbol = CURRENCY_OPTIONS[currency]
run_every = f"{refresh_seconds}s" if auto_refresh else None


@st.fragment(run_every=run_every)
def render_dashboard() -> None:
    try:
        markets, fetched_at = fetch_markets(
            currency,
            market_count,
            api_key,
        )
    except CoinGeckoError as exc:
        st.error(str(exc))
        st.info(
            "If this continues, create a CoinGecko Demo API key and add it "
            "to .streamlit/secrets.toml."
        )
        return

    if markets.empty:
        st.warning("No market data was returned.")
        return

    try:
        global_data = fetch_global(currency, api_key)
    except CoinGeckoError:
        global_data = {}
        st.warning("Global market statistics are temporarily unavailable.")

    try:
        chart_data = fetch_chart(
            selected_coin,
            currency,
            chart_days,
            api_key,
        )
    except CoinGeckoError:
        chart_data = pd.DataFrame()
        st.warning("Historical chart data is temporarily unavailable.")

    total_market_cap = currency_value(
        global_data,
        "total_market_cap",
        currency,
    )

    total_volume = currency_value(
        global_data,
        "total_volume",
        currency,
    )

    btc_dominance = numeric(
        global_data.get("market_cap_percentage", {}).get("btc")
    )

    active_coins = numeric(
        global_data.get("active_cryptocurrencies")
    )

    top_row = st.columns(4)

    with top_row[0]:
        st.metric(
            "Total market cap",
            format_compact(total_market_cap, currency_symbol),
        )

    with top_row[1]:
        st.metric(
            "24h volume",
            format_compact(total_volume, currency_symbol),
        )

    with top_row[2]:
        st.metric(
            "BTC dominance",
            f"{btc_dominance:.2f}%" if btc_dominance is not None else "N/A",
        )

    with top_row[3]:
        st.metric(
            "Active assets",
            format_compact(active_coins),
        )

    st.caption(
        f"Last poll: {fetched_at.strftime('%Y-%m-%d %H:%M:%S UTC')} | "
        f"Currency: {currency_name} | "
        f"Refresh: {'on' if auto_refresh else 'manual'}"
    )

    market_tab, detail_tab = st.tabs(
        ["Market Overview", "Asset Detail"]
    )

    with market_tab:
        left_column, right_column = st.columns([1.7, 1])

        with left_column:
            st.subheader("Market table")

            market_table = prepare_market_table(
                markets,
                currency_symbol,
            )

            st.dataframe(
                market_table,
                hide_index=True,
                use_container_width=True,
                height=650,
            )

            st.download_button(
                "Download market CSV",
                data=market_table.to_csv(index=False).encode("utf-8"),
                file_name="crypto-market.csv",
                mime="text/csv",
                use_container_width=True,
            )

        with right_column:
            st.subheader("Top gainers")
            render_movers(
                markets,
                ascending=False,
                currency_symbol=currency_symbol,
            )

            st.subheader("Top losers")
            render_movers(
                markets,
                ascending=True,
                currency_symbol=currency_symbol,
            )

    with detail_tab:
        focus_rows = markets.loc[
            markets["id"].astype(str).eq(selected_coin)
        ]

        if focus_rows.empty:
            try:
                snapshot = fetch_snapshot(
                    selected_coin,
                    currency,
                    api_key,
                )
                focus = snapshot.iloc[0] if not snapshot.empty else None
            except CoinGeckoError:
                focus = None
        else:
            focus = focus_rows.iloc[0]

        if focus is None:
            focus_name = FEATURED_ASSETS.get(
                selected_coin,
                selected_coin,
            )
            current_price = (
                chart_data["price"].iloc[-1]
                if not chart_data.empty
                else None
            )
            current_change = None
            high_24h = None
            low_24h = None
            market_cap = None
        else:
            focus_name = str(
                focus.get(
                    "name",
                    FEATURED_ASSETS.get(selected_coin, selected_coin),
                )
            )
            current_price = focus.get("current_price")
            current_change = focus.get(
                "price_change_percentage_24h"
            )
            high_24h = focus.get("high_24h")
            low_24h = focus.get("low_24h")
            market_cap = focus.get("market_cap")

        st.subheader(f"{focus_name} detail")

        detail_metrics = st.columns(5)

        with detail_metrics[0]:
            st.metric(
                "Current price",
                format_price(current_price, currency_symbol),
            )

        with detail_metrics[1]:
            st.metric(
                "24h change",
                format_change(current_change),
            )

        with detail_metrics[2]:
            st.metric(
                "24h high",
                format_price(high_24h, currency_symbol),
            )

        with detail_metrics[3]:
            st.metric(
                "24h low",
                format_price(low_24h, currency_symbol),
            )

        with detail_metrics[4]:
            st.metric(
                "Market cap",
                format_compact(market_cap, currency_symbol),
            )

        if chart_data.empty:
            st.info("No historical data is available for this asset.")
        else:
            first_price = numeric(chart_data["price"].iloc[0])
            last_price = numeric(chart_data["price"].iloc[-1])

            is_positive = (
                first_price is not None
                and last_price is not None
                and last_price >= first_price
            )

            line_color = "#00a982" if is_positive else "#e05656"
            fill_color = (
                "rgba(0, 169, 130, 0.12)"
                if is_positive
                else "rgba(224, 86, 86, 0.12)"
            )

            chart = go.Figure()

            chart.add_trace(
                go.Scatter(
                    x=chart_data["time"],
                    y=chart_data["price"],
                    mode="lines",
                    line={
                        "color": line_color,
                        "width": 3,
                    },
                    fill="tozeroy",
                    fillcolor=fill_color,
                    hovertemplate=(
                        "%{x|%b %d %H:%M UTC}<br>"
                        f"{currency_symbol}%{{y:,.6f}}"
                        "<extra></extra>"
                    ),
                )
            )

            chart.update_layout(
                height=470,
                margin={
                    "l": 10,
                    "r": 10,
                    "t": 20,
                    "b": 10,
                },
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(255,255,255,0.65)",
                showlegend=False,
                font={
                    "family": "DM Sans",
                    "color": "#112522",
                },
            )

            chart.update_xaxes(
                showgrid=False,
                title=None,
            )

            chart.update_yaxes(
                showgrid=True,
                gridcolor="rgba(17, 37, 34, 0.08)",
                title=None,
                tickprefix=currency_symbol,
            )

            st.plotly_chart(
                chart,
                use_container_width=True,
                config={
                    "displayModeBar": False,
                },
            )

    st.caption(
        "Market data is for monitoring and educational purposes only. "
        "Cryptocurrency prices may be delayed and are not financial advice."
    )


render_dashboard()
