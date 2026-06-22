"""
Mean Reversion Strategy - Standalone runner
Extracted from: mean reversion strategy.ipynb
Fixes applied:
  - CSV paths -> local ./data/notebook_files/
  - pd.read_html wrapped with StringIO (FutureWarning fix)
  - Removed trailing `?` that triggered IPython help
  - Fixed chained assignment (iloc -> .loc with index label)
"""

import os, sys, warnings
warnings.filterwarnings("ignore", category=FutureWarning)

# Force UTF-8 output on Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import pandas as pd
import numpy as np
import yfinance as yf
import requests
from datetime import datetime, timedelta
from io import StringIO

# ── Ensure output directory exists ────────────────────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "notebook_files")
os.makedirs(DATA_DIR, exist_ok=True)

# ═══════════════════════════════════════════════════════════════════════════════
# CELL 1 — Fetch DJIA constituents + 10yr prices
# ═══════════════════════════════════════════════════════════════════════════════
wiki_url = "https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average"
headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}
response = requests.get(wiki_url, headers=headers, timeout=30)
response.raise_for_status()

# FIX: wrap response.text in StringIO to avoid FutureWarning
tables = pd.read_html(StringIO(response.text), attrs={"id": "constituents"})
constituents_df = tables[0]
print("Columns found:", constituents_df.columns.tolist())

# Normalise column names
constituents_df.columns = [c.strip() for c in constituents_df.columns]
symbol_col = [c for c in constituents_df.columns if "symbol" in c.lower() or "ticker" in c.lower()][0]
constituents_df = constituents_df.rename(columns={symbol_col: "Symbol"})

# Clean symbols
constituents_df["Symbol"] = (
    constituents_df["Symbol"]
    .str.strip()
    .str.replace(r"^.*:\s*", "", regex=True)
    .str.replace(r"\s+", "-", regex=True)
)

constituents_path = os.path.join(DATA_DIR, "djia_constituents.csv")
constituents_df.to_csv(constituents_path, index=False)
print(f"Constituents saved -> {constituents_path}")
print(constituents_df[["Symbol"]].head())

# ── Fetch 10 years of adjusted close prices via yfinance ──────────────────────
end_date   = datetime.today().strftime("%Y-%m-%d")
start_date = (datetime.today() - timedelta(days=365 * 10)).strftime("%Y-%m-%d")

symbols = constituents_df["Symbol"].tolist()
price_data = {}
failed_symbols = []

for symbol in symbols:
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(start=start_date, end=end_date, auto_adjust=True)
        if hist.empty:
            raise ValueError(f"No data returned for {symbol}")
        price_data[symbol] = hist["Close"]
        print(f"  [OK] {symbol:8s}  rows={len(hist)}")
    except Exception as e:
        failed_symbols.append(symbol)
        print(f"  [FAIL] ERROR fetching {symbol}: {e}")

if failed_symbols:
    print(f"\nFailed symbols: {failed_symbols}")

prices_df = pd.DataFrame(price_data)
prices_df.index.name = "Date"
prices_df.index = pd.to_datetime(prices_df.index).tz_localize(None)

prices_path = os.path.join(DATA_DIR, "djia_prices.csv")
prices_df.to_csv(prices_path)
print(f"\nPrice data saved -> {prices_path}  shape={prices_df.shape}")

# ── Reload & forward fill ────────────────────────────────────────────────────
constituents_loaded = pd.read_csv(constituents_path)
prices_loaded = pd.read_csv(prices_path, index_col="Date", parse_dates=True)
prices_filled = prices_loaded.ffill()

missing_before = prices_loaded.isna().sum().sum()
missing_after  = prices_filled.isna().sum().sum()

print("\n-- Reload Summary ----------------------------------------------")
print(f"Constituents DataFrame : {constituents_loaded.shape}")
print(f"Prices DataFrame       : {prices_filled.shape}")
print(f"Missing values before ffill : {missing_before}")
print(f"Missing values after  ffill : {missing_after}")
print("\nFirst 5 rows of prices (filled):")
print(prices_filled.head())

# ═══════════════════════════════════════════════════════════════════════════════
# CELL 2 — Daily returns
# ═══════════════════════════════════════════════════════════════════════════════
daily_returns = prices_filled.pct_change()
daily_returns = daily_returns.dropna(how="all")

print("-- Daily Returns Summary ----------------------------------------")
print(f"Shape                  : {daily_returns.shape}")
print(f"Date range             : {daily_returns.index[0].date()}  →  {daily_returns.index[-1].date()}")
print(f"Missing values         : {daily_returns.isna().sum().sum()}")

print("\nFirst 5 rows of daily returns:")
print(daily_returns.head())
print("\nDescriptive statistics (daily returns):")
print(daily_returns.describe().round(6))

returns_path = os.path.join(DATA_DIR, "djia_daily_returns.csv")
daily_returns.to_csv(returns_path)
print(f"\nDaily returns saved -> {returns_path}  shape={daily_returns.shape}")

# ═══════════════════════════════════════════════════════════════════════════════
# CELL 3 — Identify 10 stocks with lowest returns per day
# ═══════════════════════════════════════════════════════════════════════════════
daily_returns_trimmed = daily_returns.iloc[1:]
lowest_10_per_day = {}

for date, row in daily_returns_trimmed.iterrows():
    valid_row = row.dropna()
    bottom_10 = valid_row.nsmallest(10)
    lowest_10_per_day[date] = {
        f"Rank_{i+1}_Stock":  stock
        for i, stock in enumerate(bottom_10.index)
    } | {
        f"Rank_{i+1}_Return": ret
        for i, ret in enumerate(bottom_10.values)
    }

lowest_10_df = pd.DataFrame.from_dict(lowest_10_per_day, orient="index")
ordered_cols = [col for i in range(1, 11) for col in (f"Rank_{i}_Stock", f"Rank_{i}_Return")]
lowest_10_df = lowest_10_df[ordered_cols]
lowest_10_df.index.name = "Date"

print("-- 10 Lowest-Return Stocks per Trading Day ---------------------")
print(f"Shape : {lowest_10_df.shape}")
print(f"Date range : {lowest_10_df.index[0].date()}  →  {lowest_10_df.index[-1].date()}")
print("\nFirst 5 rows:")
print(lowest_10_df.head())

lowest_10_path = os.path.join(DATA_DIR, "djia_lowest_10_daily.csv")
lowest_10_df.to_csv(lowest_10_path)
print(f"\nLowest-10 data saved -> {lowest_10_path}  shape={lowest_10_df.shape}")

# ═══════════════════════════════════════════════════════════════════════════════
# CELL 4 — Trading simulation
# ═══════════════════════════════════════════════════════════════════════════════
lowest_10_df.index = pd.to_datetime(lowest_10_df.index)
prices_filled.index = pd.to_datetime(prices_filled.index)
all_trading_dates = prices_filled.index.sort_values()

INITIAL_CAPITAL   = 100_000.0
MIN_CAPITAL       = 1.0
capital           = INITIAL_CAPITAL
results           = []

stock_cols = [f"Rank_{i}_Stock" for i in range(1, 11)]

for current_date in all_trading_dates:
    loc = all_trading_dates.get_loc(current_date)
    if loc >= len(all_trading_dates) - 1:
        results.append({"Date": current_date, "Capital": round(capital, 4)})
        break

    next_date = all_trading_dates[loc + 1]

    if capital < MIN_CAPITAL:
        print(f"  [WARN] Capital too low ({capital:.2f}) on {current_date.date()} -- stopping.")
        results.append({"Date": current_date, "Capital": round(capital, 4)})
        break

    if current_date not in lowest_10_df.index:
        results.append({"Date": current_date, "Capital": round(capital, 4)})
        continue

    selected_stocks = lowest_10_df.loc[current_date, stock_cols].dropna().tolist()
    if len(selected_stocks) == 0:
        results.append({"Date": current_date, "Capital": round(capital, 4)})
        continue

    buy_prices  = {}
    sell_prices = {}

    for stock in selected_stocks:
        if stock not in prices_filled.columns:
            continue
        buy_price  = prices_filled.loc[current_date, stock]
        sell_price = prices_filled.loc[next_date,    stock]
        if pd.isna(buy_price) or pd.isna(sell_price):
            continue
        if buy_price <= 0 or sell_price <= 0:
            continue
        buy_prices[stock]  = buy_price
        sell_prices[stock] = sell_price

    tradeable = list(buy_prices.keys())
    n_stocks  = len(tradeable)

    if n_stocks == 0:
        results.append({"Date": current_date, "Capital": round(capital, 4)})
        continue

    alloc_per_stock = capital / n_stocks
    new_capital = 0.0
    for stock in tradeable:
        shares   = alloc_per_stock / buy_prices[stock]
        proceeds = shares * sell_prices[stock]
        new_capital += proceeds

    daily_return_pct = (new_capital - capital) / capital * 100
    if abs(daily_return_pct) > 50:
        print(f"  [WARN] Implausible daily return ({daily_return_pct:.1f}%) on "
              f"{current_date.date()} -- skipping trade, carrying capital forward.")
        results.append({"Date": current_date, "Capital": round(capital, 4)})
        continue

    capital = new_capital
    results.append({"Date": current_date, "Capital": round(capital, 4)})

simulation_df = pd.DataFrame(results, columns=["Date", "Capital"])
simulation_df["Date"] = pd.to_datetime(simulation_df["Date"])
simulation_df = simulation_df.set_index("Date").sort_index()

final_capital  = simulation_df["Capital"].iloc[-1]
total_return   = (final_capital - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100
n_trading_days = len(simulation_df)

print("-- Trading Simulation Results -----------------------------------")
print(f"Initial capital  : ${INITIAL_CAPITAL:>15,.2f}")
print(f"Final capital    : ${final_capital:>15,.2f}")
print(f"Total return     : {total_return:>+.2f}%")
print(f"Trading days     : {n_trading_days}")
print(f"\nFirst 5 rows of simulation results:")
print(simulation_df.head())
print(f"\nLast 5 rows of simulation results:")
print(simulation_df.tail())

sim_path = os.path.join(DATA_DIR, "djia_simulation_results.csv")
simulation_df.to_csv(sim_path)
print(f"\nSimulation results saved -> {sim_path}  shape={simulation_df.shape}")

# ═══════════════════════════════════════════════════════════════════════════════
# CELL 5 — Performance metrics
# ═══════════════════════════════════════════════════════════════════════════════
capital_series = simulation_df["Capital"]
daily_sim_returns = capital_series.pct_change().dropna()

n_days           = len(daily_sim_returns)
total_growth     = capital_series.iloc[-1] / capital_series.iloc[0]
annualized_return = total_growth ** (252 / n_days) - 1

annualized_volatility = daily_sim_returns.std() * np.sqrt(252)
sharpe_ratio = annualized_return / annualized_volatility

print("-- Performance Metrics -----------------------------------------")
print(f"Number of trading days used : {n_days}")
print(f"Annualized Return           : {annualized_return * 100:>+.4f}%")
print(f"Annualized Volatility       : {annualized_volatility * 100:>.4f}%")
print(f"Sharpe Ratio (Rf = 0)       : {sharpe_ratio:>.4f}")

# ═══════════════════════════════════════════════════════════════════════════════
# CELL 6 — Benchmark comparison (DIA ETF)
# ═══════════════════════════════════════════════════════════════════════════════
bench_start = prices_filled.index.min().strftime("%Y-%m-%d")
bench_end   = prices_filled.index.max().strftime("%Y-%m-%d")
print(f"\nBenchmark period : {bench_start}  ->  {bench_end}")

dia_ticker = yf.Ticker("DIA")
dia_hist   = dia_ticker.history(start=bench_start, end=bench_end, auto_adjust=True)

if dia_hist.empty:
    raise ValueError("No data returned for DIA — check the ticker or date range.")

dia_prices = dia_hist["Close"].copy()
dia_prices.index = pd.to_datetime(dia_prices.index).tz_localize(None)
dia_prices.name  = "DIA"

print(f"DIA price rows fetched : {len(dia_prices)}")
print(f"DIA date range         : {dia_prices.index[0].date()}  ->  {dia_prices.index[-1].date()}")

dia_daily_returns = dia_prices.pct_change().dropna()
print(f"\nDIA daily returns rows : {len(dia_daily_returns)}")
print("Sample DIA daily returns:")
print(dia_daily_returns.head())

n_dia_days = len(dia_daily_returns)
dia_total_growth      = dia_prices.iloc[-1] / dia_prices.iloc[0]
dia_annualized_return = dia_total_growth ** (252 / n_dia_days) - 1
dia_annualized_vol    = dia_daily_returns.std() * np.sqrt(252)
dia_sharpe_ratio      = dia_annualized_return / dia_annualized_vol

print("\n-- DIA ETF Performance Metrics ---------------------------------")
print(f"Number of trading days      : {n_dia_days}")
print(f"Annualized Return           : {dia_annualized_return * 100:>+.4f}%")
print(f"Annualized Volatility       : {dia_annualized_vol    * 100:>.4f}%")
print(f"Sharpe Ratio (Rf = 0)       : {dia_sharpe_ratio:>.4f}")

print("\n-- Sharpe Ratio Comparison --------------------------------------")
print(f"{'Metric':<30} {'Strategy':>12} {'DIA (Benchmark)':>16}")
print("-" * 60)
print(f"{'Annualized Return':<30} {annualized_return * 100:>+11.4f}% {dia_annualized_return * 100:>+15.4f}%")
print(f"{'Annualized Volatility':<30} {annualized_volatility * 100:>11.4f}% {dia_annualized_vol * 100:>15.4f}%")
print(f"{'Sharpe Ratio (Rf = 0)':<30} {sharpe_ratio:>12.4f} {dia_sharpe_ratio:>16.4f}")
print("-" * 60)

if sharpe_ratio > dia_sharpe_ratio:
    print(
        f"\n[WIN] Our mean-reversion strategy OUTPERFORMED the DIA benchmark "
        f"on a risk-adjusted basis.\n"
        f"   Strategy Sharpe ({sharpe_ratio:.4f}) > DIA Sharpe ({dia_sharpe_ratio:.4f})"
    )
else:
    print(
        f"\n[LOSS] Our mean-reversion strategy UNDERPERFORMED the DIA benchmark "
        f"on a risk-adjusted basis.\n"
        f"   Strategy Sharpe ({sharpe_ratio:.4f}) <= DIA Sharpe ({dia_sharpe_ratio:.4f})"
    )

# ═══════════════════════════════════════════════════════════════════════════════
# CELL 7 — Performance summary table
# ═══════════════════════════════════════════════════════════════════════════════
summary_data = {
    "Mean-Reversion Strategy": {
        "Annual Return (%)":       round(annualized_return    * 100, 4),
        "Annual Std Dev (%)":      round(annualized_volatility * 100, 4),
        "Sharpe Ratio (Rf = 0)":   round(sharpe_ratio,               4),
    },
    "DIA ETF (Benchmark)": {
        "Annual Return (%)":       round(dia_annualized_return * 100, 4),
        "Annual Std Dev (%)":      round(dia_annualized_vol    * 100, 4),
        "Sharpe Ratio (Rf = 0)":   round(dia_sharpe_ratio,           4),
    },
}

summary_df = pd.DataFrame(summary_data)

def winner(row):
    strat_val = row["Mean-Reversion Strategy"]
    dia_val   = row["DIA ETF (Benchmark)"]
    if row.name == "Annual Std Dev (%)":
        return "* Strategy" if strat_val < dia_val else "* DIA ETF"
    else:
        return "* Strategy" if strat_val > dia_val else "* DIA ETF"

summary_df["Winner"] = summary_df.apply(winner, axis=1)

divider = "-" * 72
print(divider)
print("  PERFORMANCE SUMMARY: Mean-Reversion Strategy vs DIA ETF")
print(divider)
print(summary_df.to_string())
print(divider)

print("\n  RISK-ADJUSTED VERDICT (Sharpe Ratio)")
print(divider)

if sharpe_ratio > dia_sharpe_ratio:
    winner_name  = "Mean-Reversion Strategy"
    winner_val   = sharpe_ratio
    loser_val    = dia_sharpe_ratio
    icon         = "[WIN]"
else:
    winner_name  = "DIA ETF (Benchmark)"
    winner_val   = dia_sharpe_ratio
    loser_val    = sharpe_ratio
    icon         = "[--]"

print(f"  {icon}  {winner_name} achieved HIGHER risk-adjusted returns.")
print(f"      Sharpe - Strategy : {sharpe_ratio:>8.4f}")
print(f"      Sharpe - DIA ETF  : {dia_sharpe_ratio:>8.4f}")
print(f"      Difference        : {abs(sharpe_ratio - dia_sharpe_ratio):>8.4f} "
      f"in favour of {winner_name}")
print(divider)

# ═══════════════════════════════════════════════════════════════════════════════
# CELL 8 — Plotly performance chart (saved as HTML)
# ═══════════════════════════════════════════════════════════════════════════════
try:
    import plotly.graph_objects as go

    strategy_data = simulation_df.copy()
    strategy_data['Daily Return'] = strategy_data['Capital'].pct_change()

    dia_data = pd.DataFrame({
        'DIA Price': dia_prices,
        'Daily Return': dia_daily_returns
    })

    # FIX: use .loc with index label instead of chained .iloc assignment
    strategy_data['Cumulative Return'] = (1 + strategy_data['Daily Return']).cumprod()
    strategy_data.loc[strategy_data.index[0], 'Cumulative Return'] = 1.0

    dia_data['Cumulative Return'] = (1 + dia_data['Daily Return']).cumprod()
    dia_data.loc[dia_data.index[0], 'Cumulative Return'] = 1.0

    INITIAL_CAPITAL = 100_000
    strategy_data['Portfolio Value'] = strategy_data['Cumulative Return'] * INITIAL_CAPITAL
    dia_data['Portfolio Value'] = dia_data['Cumulative Return'] * INITIAL_CAPITAL

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=strategy_data.index, y=strategy_data['Portfolio Value'],
        mode='lines', name='Mean Reversion Strategy',
        line=dict(color='#1f77b4', width=2)
    ))
    fig.add_trace(go.Scatter(
        x=dia_data.index, y=dia_data['Portfolio Value'],
        mode='lines', name='DIA ETF (Benchmark)',
        line=dict(color='#ff7f0e', width=2)
    ))
    fig.update_layout(
        title='Growth of $100,000 Portfolio Over Time: Mean Reversion vs DIA ETF',
        xaxis_title='Date', yaxis_title='Portfolio Value ($)',
        legend_title='Strategy', autosize=False,
        width=1200, height=600, hovermode='x unified',
        template='plotly_white'
    )
    fig.update_yaxes(tickformat='$,.0f')

    chart_path = os.path.join(DATA_DIR, "performance_chart.html")
    fig.write_html(chart_path)
    print(f"\n[OK] Performance chart saved -> {chart_path}")

    # Open chart in default browser
    import webbrowser
    webbrowser.open('file:///' + chart_path.replace('\\', '/'))
    print("[OK] Chart opened in browser.")
except ImportError:
    print("\n[WARN] plotly not installed -- skipping chart generation. Install with: pip install plotly")

print("\n=== All cells executed successfully. ===")
