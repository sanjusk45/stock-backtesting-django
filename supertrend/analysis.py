"""
Supertrend Strategy Backtester
Core analysis logic. Used by Django views.
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import io
import warnings
from datetime import datetime, timedelta

warnings.filterwarnings("ignore")

SYMBOLS = {
    "RELIANCE":  "RELIANCE.NS",
    "NIFTYBEES": "NIFTYBEES.NS",
    "ITC":       "ITC.NS",
    "TCS":       "TCS.NS",
    "HDFCBANK":  "HDFCBANK.NS",
    "INFY":      "INFY.NS",
}


# ─────────────────────────────────────────────────────────────────────────────
# DATA FETCH
# ─────────────────────────────────────────────────────────────────────────────
def fetch_data(ticker: str, start: str, end: str) -> pd.DataFrame:
    try:
        import yfinance as yf
        df = yf.download(ticker, start=start, end=end,
                         progress=False, auto_adjust=True)
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        df.dropna(inplace=True)
        df.index = pd.to_datetime(df.index)
        if len(df) < 20:
            raise ValueError("Too few rows")
        return df[["Open", "High", "Low", "Close"]]
    except Exception:
        return _synthetic(ticker)


def fetch_live_data(ticker: str) -> dict:
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        fi = t.fast_info

        live = {}
        live["last_price"] = round(float(fi.last_price), 2)
        live["prev_close"] = round(float(fi.previous_close), 2)
        live["day_high"]   = round(float(fi.day_high), 2)
        live["day_low"]    = round(float(fi.day_low), 2)
        live["volume"]     = int(fi.three_month_average_volume or 0)
        live["market_cap"] = fi.market_cap

        change     = live["last_price"] - live["prev_close"]
        change_pct = change / live["prev_close"] * 100
        live["change"]     = round(change, 2)
        live["change_pct"] = round(change_pct, 2)
        live["direction"]  = "▲ UP" if change >= 0 else "▼ DOWN"
        live["color"]      = "#2ecc71" if change >= 0 else "#e74c3c"

        try:
            intra = t.history(period="1d", interval="1m")
            if not intra.empty:
                live["last_price"]  = round(float(intra["Close"].iloc[-1]), 2)
                live["intra_open"]  = round(float(intra["Open"].iloc[0]), 2)
                live["intra_high"]  = round(float(intra["High"].max()), 2)
                live["intra_low"]   = round(float(intra["Low"].min()), 2)
                live["last_update"] = str(intra.index[-1])
            else:
                live["last_update"] = "End of day (market closed)"
        except Exception:
            live["last_update"] = "Live tick unavailable"

        live["status"] = "ok"
        return live

    except Exception as e:
        return {
            "status": "error", "msg": str(e),
            "last_price": 0.0, "prev_close": 0.0,
            "change": 0.0, "change_pct": 0.0,
            "direction": "N/A", "color": "#7eb8f7",
            "day_high": 0.0, "day_low": 0.0,
            "volume": 0, "last_update": "Unavailable"
        }


def _synthetic(ticker: str) -> pd.DataFrame:
    seeds = {"RELIANCE.NS": 42, "ITC.NS": 7, "NIFTYBEES.NS": 99, "TCS.NS": 13, "HDFCBANK.NS": 55, "INFY.NS": 27}
    bases = {"RELIANCE.NS": 2800.0, "ITC.NS": 430.0, "NIFTYBEES.NS": 240.0, "TCS.NS": 3900.0, "HDFCBANK.NS": 1600.0, "INFY.NS": 1700.0}
    np.random.seed(seeds.get(ticker, 1))
    dates = pd.bdate_range(end=datetime.today(), periods=252 * 5)
    n     = len(dates)
    base  = bases.get(ticker, 1000.0)
    ret   = np.random.normal(0.0003, 0.012, n)
    ret[60:120]  += 0.004
    ret[130:185] -= 0.005
    ret[200:]    += 0.003
    close = base * np.exp(np.cumsum(ret))
    high  = close * (1 + np.abs(np.random.normal(0, 0.007, n)))
    low   = close * (1 - np.abs(np.random.normal(0, 0.007, n)))
    opn   = np.concatenate([[close[0] * 0.999], close[:-1]])
    return pd.DataFrame(
        {"Open": np.round(opn, 2), "High": np.round(high, 2),
         "Low": np.round(low, 2), "Close": np.round(close, 2)},
        index=dates
    )


# ─────────────────────────────────────────────────────────────────────────────
# HEIKIN ASHI
# ─────────────────────────────────────────────────────────────────────────────
def heikin_ashi(df: pd.DataFrame) -> pd.DataFrame:
    ha = pd.DataFrame(index=df.index)
    ha["HA_Close"] = (df["Open"] + df["High"] + df["Low"] + df["Close"]) / 4
    ha_open    = np.zeros(len(df))
    ha_open[0] = (df["Open"].iloc[0] + df["Close"].iloc[0]) / 2
    hc         = ha["HA_Close"].values
    for i in range(1, len(df)):
        ha_open[i] = (ha_open[i - 1] + hc[i - 1]) / 2
    ha["HA_Open"] = ha_open
    ha["HA_High"] = pd.concat([df["High"], ha["HA_Open"], ha["HA_Close"]], axis=1).max(axis=1)
    ha["HA_Low"]  = pd.concat([df["Low"],  ha["HA_Open"], ha["HA_Close"]], axis=1).min(axis=1)
    return ha


# ─────────────────────────────────────────────────────────────────────────────
# SUPERTREND
# ─────────────────────────────────────────────────────────────────────────────
def supertrend(ha: pd.DataFrame, period: int = 7, mult: float = 3) -> pd.DataFrame:
    H = ha["HA_High"].values
    L = ha["HA_Low"].values
    C = ha["HA_Close"].values
    n = len(ha)

    tr    = np.zeros(n)
    tr[0] = H[0] - L[0]
    for i in range(1, n):
        tr[i] = max(H[i] - L[i], abs(H[i] - C[i - 1]), abs(L[i] - C[i - 1]))

    atr    = np.zeros(n)
    atr[0] = tr[0]
    alpha  = 1.0 / period
    for i in range(1, n):
        atr[i] = alpha * tr[i] + (1 - alpha) * atr[i - 1]

    hl2 = (H + L) / 2.0
    ub  = hl2 + mult * atr
    lb  = hl2 - mult * atr
    fub = ub.copy()
    flb = lb.copy()

    for i in range(1, n):
        fub[i] = ub[i] if (ub[i] < fub[i - 1] or C[i - 1] > fub[i - 1]) else fub[i - 1]
        flb[i] = lb[i] if (lb[i] > flb[i - 1] or C[i - 1] < flb[i - 1]) else flb[i - 1]

    st_vals    = np.zeros(n)
    direction  = np.ones(n, dtype=int)
    st_vals[0] = flb[0]
    direction[0] = 1

    for i in range(1, n):
        if st_vals[i - 1] == fub[i - 1]:
            direction[i] = -1 if C[i] <= fub[i] else 1
        else:
            direction[i] =  1 if C[i] >= flb[i] else -1
        st_vals[i] = flb[i] if direction[i] == 1 else fub[i]

    out = ha.copy()
    out["Supertrend"] = st_vals
    out["Direction"]  = direction
    out["Final_UB"]   = fub
    out["Final_LB"]   = flb
    return out


# ─────────────────────────────────────────────────────────────────────────────
# SIGNALS
# ─────────────────────────────────────────────────────────────────────────────
def generate_signals(st_df: pd.DataFrame) -> pd.DataFrame:
    st_df = st_df.copy()
    prev = st_df["Direction"].shift(1).fillna(st_df["Direction"].iloc[0]).astype(int)
    st_df["Prev_Dir"]    = prev
    st_df["Long_Entry"]  = (st_df["Direction"] ==  1) & (prev == -1)
    st_df["Short_Entry"] = (st_df["Direction"] == -1) & (prev ==  1)
    return st_df


# ─────────────────────────────────────────────────────────────────────────────
# BACKTEST
# ─────────────────────────────────────────────────────────────────────────────
def backtest(ohlc: pd.DataFrame, sig: pd.DataFrame):
    long_trades  = []
    short_trades = []
    in_long = in_short = False
    le_d = le_p = se_d = se_p = None

    def _rec(ed, ep, xd, xp, pnl):
        return {
            "entry_date":  ed.strftime("%Y-%m-%d"),
            "entry_price": round(float(ep), 2),
            "exit_date":   xd.strftime("%Y-%m-%d"),
            "exit_price":  round(float(xp), 2),
            "pnl":         round(float(pnl), 2)
        }

    for date, row in sig.iterrows():
        px = float(ohlc.loc[date, "Close"])

        if row["Long_Entry"]:
            if in_short:
                short_trades.append(_rec(se_d, se_p, date, px, se_p - px))
                in_short = False
            if not in_long:
                le_d, le_p, in_long = date, px, True

        if row["Short_Entry"]:
            if in_long:
                long_trades.append(_rec(le_d, le_p, date, px, px - le_p))
                in_long = False
            if not in_short:
                se_d, se_p, in_short = date, px, True

    ld, lp = sig.index[-1], float(ohlc.iloc[-1]["Close"])
    if in_long:
        long_trades.append(_rec(le_d, le_p, ld, lp, lp - le_p))
    if in_short:
        short_trades.append(_rec(se_d, se_p, ld, lp, se_p - lp))

    return pd.DataFrame(long_trades), pd.DataFrame(short_trades)


# ─────────────────────────────────────────────────────────────────────────────
# METRICS
# ─────────────────────────────────────────────────────────────────────────────
def calc_metrics(df: pd.DataFrame, label: str) -> dict:
    if df.empty:
        return {"label": label, "total": 0, "pnl": 0.0,
                "win_rate": "0%", "max_dd": 0.0, "avg_pnl": 0.0,
                "wins": 0, "losses": 0}
    pnl  = df["pnl"].values
    cum  = np.cumsum(pnl)
    mdd  = round(float((np.maximum.accumulate(cum) - cum).max()), 2)
    wins = int((pnl > 0).sum())
    return {
        "label":    label,
        "total":    len(df),
        "pnl":      round(float(pnl.sum()), 2),
        "win_rate": f"{round(wins / len(pnl) * 100, 1)}%",
        "max_dd":   mdd,
        "avg_pnl":  round(float(pnl.mean()), 2),
        "wins":     wins,
        "losses":   len(pnl) - wins,
    }


# ─────────────────────────────────────────────────────────────────────────────
# DRAW CANDLES HELPER
# ─────────────────────────────────────────────────────────────────────────────
def _draw_ha_candles(ax, ha: pd.DataFrame, dir_arr, width_frac=0.6):
    import matplotlib.dates as mdates

    dates     = ha.index
    o         = ha["HA_Open"].values
    h         = ha["HA_High"].values
    l         = ha["HA_Low"].values
    c         = ha["HA_Close"].values
    date_nums = mdates.date2num(dates.to_pydatetime())
    width     = (date_nums[1] - date_nums[0]) * width_frac if len(date_nums) > 1 else 0.4

    for i in range(len(dates)):
        bull   = dir_arr[i] == 1
        body_c = "#26a65b" if bull else "#e74c3c"
        wick_c = "#1a8a45" if bull else "#c0392b"
        border = "#1a7a40" if bull else "#a93226"
        top    = max(o[i], c[i])
        bot    = min(o[i], c[i])
        body_h = max(top - bot, width * 0.05)
        rect   = mpatches.FancyBboxPatch(
            (date_nums[i] - width / 2, bot), width, body_h,
            boxstyle="square,pad=0",
            facecolor=body_c, edgecolor=border, linewidth=0.4, zorder=3
        )
        ax.add_patch(rect)
        if h[i] > top:
            ax.plot([date_nums[i], date_nums[i]], [top, h[i]], color=wick_c, lw=0.9, zorder=2)
        if l[i] < bot:
            ax.plot([date_nums[i], date_nums[i]], [l[i], bot], color=wick_c, lw=0.9, zorder=2)
    ax.xaxis_date()


# ─────────────────────────────────────────────────────────────────────────────
# MAIN CHART
# ─────────────────────────────────────────────────────────────────────────────
def build_chart(ohlc, sig, long_df, short_df, name) -> io.BytesIO:
    import matplotlib.dates as mdates

    BG, PAN = "#131722", "#1e222d"
    GRID    = "#2a2e39"
    GREEN   = "#26a65b"
    RED     = "#e74c3c"

    ha       = sig[["HA_Open", "HA_High", "HA_Low", "HA_Close"]].copy()
    dir_arr  = sig["Direction"].values
    st_arr   = sig["Supertrend"].values
    dates    = ohlc.index
    date_nums = mdates.date2num(dates.to_pydatetime())

    fig = plt.figure(figsize=(22, 13), facecolor=BG)
    gs  = fig.add_gridspec(3, 1, height_ratios=[4, 0.9, 1.4], hspace=0.04)
    ax1 = fig.add_subplot(gs[0])
    ax2 = fig.add_subplot(gs[1], sharex=ax1)
    ax3 = fig.add_subplot(gs[2], sharex=ax1)

    for ax in (ax1, ax2, ax3):
        ax.set_facecolor(PAN)
        ax.tick_params(colors="#787b86", labelsize=8.5)
        ax.yaxis.label.set_color("#787b86")
        ax.xaxis.label.set_color("#787b86")
        for sp in ax.spines.values():
            sp.set_edgecolor(GRID)
        ax.grid(color=GRID, linewidth=0.5, alpha=0.8)

    _draw_ha_candles(ax1, ha, dir_arr, width_frac=0.55)

    ha_close = ha["HA_Close"].values
    for i in range(1, len(sig)):
        c = GREEN if dir_arr[i] == 1 else RED
        ax1.plot([date_nums[i - 1], date_nums[i]], [st_arr[i - 1], st_arr[i]],
                 color=c, lw=1.8, zorder=4, solid_capstyle="round")

    bull_mask = dir_arr == 1
    bear_mask = ~bull_mask
    ax1.fill_between(date_nums, ha_close, st_arr, where=bull_mask,
                     color=GREEN, alpha=0.12, zorder=1, interpolate=True)
    ax1.fill_between(date_nums, ha_close, st_arr, where=bear_mask,
                     color=RED, alpha=0.12, zorder=1, interpolate=True)

    if not long_df.empty:
        entry_dn = mdates.date2num(pd.to_datetime(long_df["entry_date"]).dt.to_pydatetime())
        exit_dn  = mdates.date2num(pd.to_datetime(long_df["exit_date"]).dt.to_pydatetime())
        ax1.scatter(entry_dn, long_df["entry_price"].astype(float).values * 0.998,
                    marker="^", color=GREEN, s=220, zorder=8, edgecolors="white",
                    linewidths=0.7, label="Long Entry ▲  (OHLC price)")
        ax1.scatter(exit_dn, long_df["exit_price"].astype(float).values * 1.002,
                    marker="v", color="#f39c12", s=220, zorder=8, edgecolors="white",
                    linewidths=0.7, label="Long Exit ▼  (OHLC price)")

    if not short_df.empty:
        entry_dn = mdates.date2num(pd.to_datetime(short_df["entry_date"]).dt.to_pydatetime())
        exit_dn  = mdates.date2num(pd.to_datetime(short_df["exit_date"]).dt.to_pydatetime())
        ax1.scatter(entry_dn, short_df["entry_price"].astype(float).values * 1.002,
                    marker="v", color=RED, s=220, zorder=8, edgecolors="white",
                    linewidths=0.7, label="Short Entry ▼  (OHLC price)")
        ax1.scatter(exit_dn, short_df["exit_price"].astype(float).values * 0.998,
                    marker="^", color="#9b59b6", s=220, zorder=8, edgecolors="white",
                    linewidths=0.7, label="Short Exit ▲  (OHLC price)")

    ax1.set_title(
        f"{name}  ·  Heikin Ashi Candles  +  Supertrend (ATR=7, Mult=3)\n"
        f"⚠  Signal: Heikin Ashi direction change  |  Entry/Exit Price: Original OHLC Close",
        color="#d1d4dc", fontsize=11, fontweight="bold", pad=10, loc="left"
    )
    ax1.set_ylabel("Price (₹)", fontsize=10)
    ax1.legend(loc="upper left", fontsize=8.5, facecolor="#1e222d",
               edgecolor="#363a45", labelcolor="#c8cdd8", framealpha=0.95)
    plt.setp(ax1.get_xticklabels(), visible=False)

    if "Volume" in ohlc.columns:
        vol = ohlc["Volume"].values
    else:
        vol = ((ohlc["High"] - ohlc["Low"]) / ohlc["Close"] * 1e7).values

    vol_colors = [GREEN if dir_arr[i] == 1 else RED for i in range(len(dates))]
    ax2.bar(date_nums, vol, color=vol_colors, alpha=0.7, width=0.55)
    ax2.set_ylabel("Vol", fontsize=8)
    ax2.yaxis.set_major_formatter(
        plt.FuncFormatter(lambda x, _: f"{x / 1e6:.1f}M" if x >= 1e6 else f"{x / 1e3:.0f}K")
    )
    ax2.set_ylim(0, max(vol) * 1.2 if len(vol) > 0 else 1)
    plt.setp(ax2.get_xticklabels(), visible=False)

    all_t = []
    if not long_df.empty:
        all_t.append(long_df[["exit_date", "pnl"]].rename(columns={"exit_date": "Exit Date", "pnl": "PnL"}))
    if not short_df.empty:
        all_t.append(short_df[["exit_date", "pnl"]].rename(columns={"exit_date": "Exit Date", "pnl": "PnL"}))
    if all_t:
        comb = pd.concat(all_t).sort_values("Exit Date")
        comb["Exit Date"] = pd.to_datetime(comb["Exit Date"])
        comb["PnL"]       = comb["PnL"].astype(float)
        comb["Cum"]       = comb["PnL"].cumsum()
        exit_nums = mdates.date2num(comb["Exit Date"].dt.to_pydatetime())
        bc = [GREEN if p > 0 else RED for p in comb["PnL"]]
        ax3.bar(exit_nums, comb["PnL"].values, color=bc, alpha=0.75, width=2.0)
        ax3.plot(exit_nums, comb["Cum"].values, color="#f1c40f",
                 linewidth=2, label="Cumulative PnL", zorder=5)
        ax3.axhline(0, color="#555577", lw=0.8, ls="--")
        ax3.legend(loc="upper left", fontsize=8.5, facecolor="#1e222d",
                   edgecolor="#363a45", labelcolor="#c8cdd8")
        ax3.fill_between(exit_nums, 0, comb["Cum"].values,
                         where=(comb["Cum"].values >= 0),
                         color="#f1c40f", alpha=0.08, interpolate=True)
        ax3.fill_between(exit_nums, 0, comb["Cum"].values,
                         where=(comb["Cum"].values < 0),
                         color=RED, alpha=0.08, interpolate=True)

    ax3.set_ylabel("PnL (₹)", fontsize=9)
    ax3.set_xlabel("Date", fontsize=9)
    ax3.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
    ax3.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
    plt.setp(ax3.get_xticklabels(), rotation=0, ha="center")

    plt.tight_layout(rect=[0, 0, 1, 1])
    buf = io.BytesIO()
    plt.savefig(buf, dpi=160, bbox_inches="tight", facecolor=BG)
    plt.close()
    buf.seek(0)
    return buf


# ─────────────────────────────────────────────────────────────────────────────
# HA vs OHLC COMPARISON CHART
# ─────────────────────────────────────────────────────────────────────────────
def build_ha_comparison_chart(ohlc: pd.DataFrame, ha: pd.DataFrame,
                               sig: pd.DataFrame, name: str) -> io.BytesIO:
    import matplotlib.dates as mdates
    from matplotlib.lines import Line2D

    BG, PAN = "#131722", "#1e222d"

    fig, (ax_ohlc, ax_ha) = plt.subplots(
        2, 1, figsize=(22, 14), sharex=True,
        gridspec_kw={"height_ratios": [1, 1], "hspace": 0.06}
    )
    fig.patch.set_facecolor(BG)
    for ax in (ax_ohlc, ax_ha):
        ax.set_facecolor(PAN)
        ax.tick_params(colors="#787b86", labelsize=9)
        ax.yaxis.label.set_color("#787b86")
        ax.xaxis.label.set_color("#787b86")
        for sp in ax.spines.values():
            sp.set_edgecolor("#2a2e39")

    dir_arr   = sig["Direction"].values
    st_arr    = sig["Supertrend"].values
    dates     = ohlc.index
    dnums     = mdates.date2num(dates.to_pydatetime())
    w         = (dnums[1] - dnums[0]) * 0.55 if len(dnums) > 1 else 0.4

    def draw_candles(ax, O, H, L, C, bull_cond, dn, width):
        for i in range(len(dn)):
            bull = bool(bull_cond[i])
            body_col = "#26a65b" if bull else "#e74c3c"
            wick_col = "#1e8449" if bull else "#c0392b"
            edge_col = "#1a7a40" if bull else "#a93226"
            top    = max(O[i], C[i])
            bot    = min(O[i], C[i])
            body_h = max(top - bot, (H[i] - L[i]) * 0.012 + 0.01)
            rect   = mpatches.FancyBboxPatch(
                (dn[i] - width / 2, bot), width, body_h,
                boxstyle="square,pad=0",
                facecolor=body_col, edgecolor=edge_col, linewidth=0.4, zorder=4
            )
            ax.add_patch(rect)
            if H[i] > top:
                ax.plot([dn[i], dn[i]], [top, H[i]], color=wick_col, lw=1.0, zorder=3)
            if L[i] < bot:
                ax.plot([dn[i], dn[i]], [L[i], bot], color=wick_col, lw=1.0, zorder=3)
        ax.xaxis_date()
        ax.set_xlim(dnums[0] - w, dnums[-1] + w)
        ax.set_ylim(min(L) * 0.995, max(H) * 1.005)

    O = ohlc["Open"].values
    H = ohlc["High"].values
    L = ohlc["Low"].values
    C = ohlc["Close"].values
    draw_candles(ax_ohlc, O, H, L, C, C >= O, dnums, w)

    st_series = sig["Supertrend"].values
    cl_series = ohlc["Close"].values
    for i in range(1, len(sig)):
        bull = dir_arr[i] == 1
        col  = "#26a65b" if bull else "#e74c3c"
        ax_ohlc.plot([dnums[i - 1], dnums[i]], [st_arr[i - 1], st_arr[i]], color=col, lw=1.8, zorder=5)
        fill = "#26a65b22" if bull else "#e74c3c22"
        ax_ohlc.fill_between([dnums[i - 1], dnums[i]],
                              [st_series[i - 1], st_series[i]],
                              [cl_series[i - 1], cl_series[i]],
                              color=fill, zorder=1)

    ax_ohlc.set_title(f"{name}  ·  ① ORIGINAL OHLC CANDLESTICKS  —  Actual Entry & Exit Price Source",
                      color="#d1d4dc", fontsize=12, fontweight="bold", pad=10)
    ax_ohlc.set_ylabel("Price (₹)", fontsize=10)
    ax_ohlc.grid(alpha=0.07, color="#363a45", linestyle="-")
    ohlc_legend = [
        mpatches.Patch(color="#26a65b", label="Bullish Candle (Close ≥ Open)"),
        mpatches.Patch(color="#e74c3c", label="Bearish Candle (Close < Open)"),
        Line2D([0], [0], color="#26a65b", lw=2, label="Supertrend Green"),
        Line2D([0], [0], color="#e74c3c", lw=2, label="Supertrend Red"),
    ]
    ax_ohlc.legend(handles=ohlc_legend, loc="upper left", fontsize=8.5,
                   facecolor="#1e222d", edgecolor="#363a45", labelcolor="#d1d4dc", framealpha=0.9)
    ax_ohlc.text(0.01, 0.04, "★  Entry & Exit prices taken from OHLC Close  (NOT from Heikin Ashi)",
                 transform=ax_ohlc.transAxes, fontsize=9, color="#f1c40f", style="italic",
                 bbox=dict(boxstyle="round,pad=0.35", facecolor="#14140a", edgecolor="#3a3a10", alpha=0.95))
    plt.setp(ax_ohlc.get_xticklabels(), visible=False)

    HO = ha["HA_Open"].values
    HH = ha["HA_High"].values
    HL = ha["HA_Low"].values
    HC = ha["HA_Close"].values
    draw_candles(ax_ha, HO, HH, HL, HC, dir_arr == 1, dnums, w)

    ha_close = ha["HA_Close"].values
    for i in range(1, len(sig)):
        bull = dir_arr[i] == 1
        col  = "#26a65b" if bull else "#e74c3c"
        ax_ha.plot([dnums[i - 1], dnums[i]], [st_arr[i - 1], st_arr[i]], color=col, lw=1.8, zorder=5)
        fill = "#26a65b22" if bull else "#e74c3c22"
        ax_ha.fill_between([dnums[i - 1], dnums[i]],
                            [st_series[i - 1], st_series[i]],
                            [ha_close[i - 1], ha_close[i]],
                            color=fill, zorder=1)

    lmask = sig["Long_Entry"].values
    smask = sig["Short_Entry"].values
    if lmask.any():
        ax_ha.scatter(dnums[lmask], HL[lmask] * 0.997, marker="^", color="#26a65b",
                      s=220, zorder=8, label="Long Entry ▲ (HA Signal)",
                      edgecolors="white", linewidths=0.8)
    if smask.any():
        ax_ha.scatter(dnums[smask], HH[smask] * 1.003, marker="v", color="#e74c3c",
                      s=220, zorder=8, label="Short Entry ▼ (HA Signal)",
                      edgecolors="white", linewidths=0.8)

    ax_ha.set_title(f"{name}  ·  ② HEIKIN ASHI CANDLESTICKS  —  Signal Generation Source",
                    color="#26a65b", fontsize=12, fontweight="bold", pad=10)
    ax_ha.set_ylabel("HA Price (₹)", fontsize=10)
    ax_ha.set_xlabel("Date", fontsize=10)
    ax_ha.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax_ha.grid(alpha=0.07, color="#363a45", linestyle="-")
    ha_legend = [
        mpatches.Patch(color="#26a65b", label="Bullish HA Candle (Supertrend Green)"),
        mpatches.Patch(color="#e74c3c", label="Bearish HA Candle (Supertrend Red)"),
        Line2D([0], [0], marker="^", color="w", markerfacecolor="#26a65b", markersize=10, label="Long Entry ▲"),
        Line2D([0], [0], marker="v", color="w", markerfacecolor="#e74c3c", markersize=10, label="Short Entry ▼"),
    ]
    ax_ha.legend(handles=ha_legend, loc="upper left", fontsize=8.5,
                 facecolor="#1e222d", edgecolor="#363a45", labelcolor="#d1d4dc", framealpha=0.9)
    ax_ha.text(0.01, 0.04,
               "▲▼  Buy/Sell signals from HA Supertrend  |  Red→Green = Long  ·  Green→Red = Short",
               transform=ax_ha.transAxes, fontsize=9, color="#26a65b", style="italic",
               bbox=dict(boxstyle="round,pad=0.35", facecolor="#081208", edgecolor="#1a4020", alpha=0.95))

    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, dpi=150, bbox_inches="tight", facecolor=BG)
    plt.close()
    buf.seek(0)
    return buf


# ─────────────────────────────────────────────────────────────────────────────
# RUN FULL BACKTEST PIPELINE
# ─────────────────────────────────────────────────────────────────────────────
def run_backtest(stock_name: str, years_back: int = 3):
    """Run the full pipeline and return all results as a dict."""
    ticker    = SYMBOLS[stock_name]
    end_date  = datetime.today()
    start_date = end_date - timedelta(days=years_back * 365 + 60)
    start_str = start_date.strftime("%Y-%m-%d")
    end_str   = end_date.strftime("%Y-%m-%d")

    ohlc     = fetch_data(ticker, start_str, end_str)
    ha       = heikin_ashi(ohlc)
    st_df    = supertrend(ha, period=7, mult=3)
    sig      = generate_signals(st_df)
    long_df, short_df = backtest(ohlc, sig)
    lm       = calc_metrics(long_df, "Long")
    sm       = calc_metrics(short_df, "Short")
    live     = fetch_live_data(ticker)

    # Build charts → base64
    import base64
    chart_buf    = build_chart(ohlc, sig, long_df, short_df, stock_name)
    ha_chart_buf = build_ha_comparison_chart(ohlc, ha, sig, stock_name)
    chart_b64    = base64.b64encode(chart_buf.read()).decode()
    ha_chart_b64 = base64.b64encode(ha_chart_buf.read()).decode()

    # HA data (last 20 bars)
    ha_table   = ha[["HA_Open", "HA_High", "HA_Low", "HA_Close"]].tail(20).copy()
    ha_table.index = ha_table.index.strftime("%Y-%m-%d")
    ha_table   = ha_table.round(2)

    ohlc_table = ohlc[["Open", "High", "Low", "Close"]].tail(20).copy()
    ohlc_table.index = ohlc_table.index.strftime("%Y-%m-%d")
    ohlc_table = ohlc_table.round(2)

    # Trade data
    long_trades  = long_df.to_dict("records") if not long_df.empty else []
    short_trades = short_df.to_dict("records") if not short_df.empty else []

    # CSV
    csv_long  = long_df[["entry_date", "entry_price", "exit_date", "exit_price"]].to_csv(index=False) if not long_df.empty else ""
    csv_short = short_df[["entry_date", "entry_price", "exit_date", "exit_price"]].to_csv(index=False) if not short_df.empty else ""

    # Live signal
    last_dir    = int(sig["Direction"].iloc[-1])
    live_signal = "BUY (Bullish)" if last_dir == 1 else "SELL (Bearish)"
    signal_color = "#2ecc71" if last_dir == 1 else "#e74c3c"

    # Summary table
    summary = [
        {"metric": "Total Trades",      "long": str(lm["total"]),             "short": str(sm["total"])},
        {"metric": "Total PnL (₹)",     "long": f"₹{lm['pnl']:,.2f}",         "short": f"₹{sm['pnl']:,.2f}"},
        {"metric": "Win Rate",           "long": lm["win_rate"],               "short": sm["win_rate"]},
        {"metric": "Max Drawdown (₹)",  "long": f"₹{lm['max_dd']:,.2f}",       "short": f"₹{sm['max_dd']:,.2f}"},
        {"metric": "Avg PnL/Trade (₹)", "long": f"₹{lm['avg_pnl']:,.2f}",      "short": f"₹{sm['avg_pnl']:,.2f}"},
    ]

    return {
        "stock":        stock_name,
        "ticker":       ticker,
        "start_str":    start_str,
        "end_str":      end_str,
        "total_days":   len(ohlc),
        "chart_b64":    chart_b64,
        "ha_chart_b64": ha_chart_b64,
        "lm":           lm,
        "sm":           sm,
        "long_trades":  long_trades,
        "short_trades": short_trades,
        "csv_long":     csv_long,
        "csv_short":    csv_short,
        "ha_table":     ha_table.reset_index().to_dict("records"),
        "ohlc_table":   ohlc_table.reset_index().to_dict("records"),
        "live":         live,
        "live_signal":  live_signal,
        "signal_color": signal_color,
        "summary":      summary,
    }
