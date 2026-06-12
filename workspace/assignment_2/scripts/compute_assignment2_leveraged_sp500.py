from __future__ import annotations

import json
import math
import shutil
import subprocess
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "assignment2_deliverables"
DATA_DIR = OUT_DIR / "data"

TEX_PATH = OUT_DIR / "Assignment_2_Leveraged_SP500.tex"
PDF_PATH = OUT_DIR / "Assignment_2_Leveraged_SP500.pdf"
CSV_PATH = DATA_DIR / "sp500tr_monthly_returns_2017_01_to_2026_05.csv"

SYMBOL = "^SP500TR"
SAMPLE_START = pd.Timestamp("2017-01-01")
SAMPLE_END = pd.Timestamp("2026-05-01")
LAMBDAS = [0.5, 1, 2, 3, 4, 5, 6]
RF_RATES = [0.00, 0.25, 0.50]


def yahoo_chart_monthly(symbol: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Fetch monthly adjusted close levels from the Yahoo Finance chart API."""
    period1 = int(datetime(start.year, start.month, start.day, tzinfo=timezone.utc).timestamp())
    end_exclusive = end + pd.offsets.MonthBegin(1) + pd.Timedelta(days=2)
    period2 = int(
        datetime(end_exclusive.year, end_exclusive.month, end_exclusive.day, tzinfo=timezone.utc).timestamp()
    )
    encoded_symbol = urllib.parse.quote(symbol, safe="")
    url = (
        f"https://query2.finance.yahoo.com/v8/finance/chart/{encoded_symbol}"
        f"?period1={period1}&period2={period2}&interval=1mo&events=history&includeAdjustedClose=true"
    )
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            )
        },
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        payload = json.load(response)

    error = payload.get("chart", {}).get("error")
    if error:
        raise RuntimeError(f"Yahoo chart API returned an error: {error}")
    result = payload["chart"]["result"][0]
    frame = pd.DataFrame(
        {
            "timestamp": result["timestamp"],
            "level": result["indicators"]["adjclose"][0]["adjclose"],
        }
    )
    frame["date"] = (
        pd.to_datetime(frame["timestamp"], unit="s", utc=True)
        .dt.tz_convert("America/New_York")
        .dt.tz_localize(None)
        .dt.to_period("M")
        .dt.to_timestamp()
    )
    frame = frame.dropna(subset=["level"]).sort_values("date").reset_index(drop=True)
    frame["sp500tr_return_percent"] = frame["level"].pct_change() * 100.0
    return frame


def load_sp500_total_return_series() -> pd.DataFrame:
    raw = yahoo_chart_monthly(SYMBOL, pd.Timestamp("2016-12-01"), SAMPLE_END)
    out = raw[(raw["date"] >= SAMPLE_START) & (raw["date"] <= SAMPLE_END)].copy().reset_index(drop=True)
    expected_dates = pd.date_range(SAMPLE_START, SAMPLE_END, freq="MS")
    if len(out) != 113:
        raise AssertionError(f"Expected 113 observations, found {len(out)}.")
    if not out["date"].equals(pd.Series(expected_dates, name="date")):
        raise AssertionError("Monthly dates are not contiguous from Jan 2017 to May 2026.")
    if out["sp500tr_return_percent"].isna().any():
        raise AssertionError("Return series contains missing values.")
    out["source"] = "Yahoo Finance chart API, symbol ^SP500TR"
    return out[["date", "level", "sp500tr_return_percent", "source"]]


def compute_stats(port_returns: np.ndarray) -> tuple[float, float, float, float, float]:
    """Return mean, sample standard deviation, Sharpe, Sortino, and Omega."""
    mu = float(np.mean(port_returns))
    sigma = float(np.std(port_returns, ddof=1))
    downside = np.minimum(port_returns, 0.0)
    downside_deviation = float(np.sqrt(np.mean(downside**2)))
    gains = float(port_returns[port_returns > 0].sum())
    losses = float(abs(port_returns[port_returns < 0].sum()))
    sharpe = math.inf if sigma == 0 else mu / sigma
    sortino = math.inf if downside_deviation == 0 else mu / downside_deviation
    omega = math.inf if losses == 0 else gains / losses
    return mu, sigma, sharpe, sortino, omega


def compute_all_results(r: np.ndarray) -> dict[float, pd.DataFrame]:
    results: dict[float, pd.DataFrame] = {}
    for rf in RF_RATES:
        rows = []
        for lam in LAMBDAS:
            port = lam * r - (lam - 1.0) * rf
            mu, sigma, sharpe, sortino, omega = compute_stats(port)
            rows.append(
                {
                    "lambda_value": lam,
                    "mean": mu,
                    "std": sigma,
                    "sharpe": sharpe,
                    "sortino": sortino,
                    "omega": omega,
                }
            )
        results[rf] = pd.DataFrame(rows)
    return results


def fmt4(value: float) -> str:
    return f"{value:.4f}"


def lambda_label(value: float) -> str:
    return "0.5" if value == 0.5 else str(int(value))


def table_latex(rf: float, frame: pd.DataFrame, table_no: int) -> str:
    lines = [
        r"\begin{table}[H]",
        r"\centering",
        rf"\caption{{Leveraged S\&P 500 monthly statistics for $r_f={rf:.2f}\%$.}}",
        rf"\label{{tab:rf-{int(rf * 100):02d}}}",
        r"\begin{tabular}{lrrrrr}",
        r"\toprule",
        r"$\lambda$ & $\bar{R}$ (\%) & $\sigma$ (\%) & Sharpe & Sortino & Omega \\",
        r"\midrule",
    ]
    for row in frame.itertuples(index=False):
        lines.append(
            " & ".join(
                [
                    lambda_label(row.lambda_value),
                    fmt4(row.mean),
                    fmt4(row.std),
                    fmt4(row.sharpe),
                    fmt4(row.sortino),
                    fmt4(row.omega),
                ]
            )
            + r" \\"
        )
    lines.extend([r"\bottomrule", r"\end{tabular}", r"\end{table}"])
    return "\n".join(lines)


def write_tex(results: dict[float, pd.DataFrame], n: int) -> None:
    tables = "\n\n".join(table_latex(rf, results[rf], i + 1) for i, rf in enumerate(RF_RATES))
    tex = rf"""\documentclass[11pt]{{article}}
\usepackage[margin=0.85in]{{geometry}}
\usepackage{{amsmath}}
\usepackage{{booktabs}}
\usepackage{{array}}
\usepackage{{float}}

\title{{Leveraged S\&P 500 Performance Analysis}}
\author{{Prepared by Harman Singh for Professor Phelim Boyle}}
\date{{June 2026}}

\begin{{document}}
\maketitle

\section*{{Data and Sample}}
The analysis uses monthly S\&P 500 total return data from January 2017 to May 2026, for a total of {n} monthly observations.
The data source is the Yahoo Finance S\&P 500 Total Return Index series, \texttt{{\string^SP500TR}}, which includes dividends and is therefore consistent with the paper's dividend-reinvestment convention.
All statistics are reported monthly and are not annualised.

\section*{{Methodology}}
Let $r_t$ denote the S\&P 500 total return in month $t$, in percent, and let $r_f$ denote the constant monthly risk-free rate, also in percent.
For each leverage level $\lambda$, the portfolio return is
\[
R_t(\lambda)=\lambda r_t-(\lambda-1)r_f=\lambda(r_t-r_f)+r_f.
\]
The analysis uses $\lambda \in \{{0.5,1,2,3,4,5,6\}}$ and $r_f \in \{{0.00\%,0.25\%,0.50\%\}}$.

For each portfolio return series, the mean is
\[
\bar{{R}}=\frac{{1}}{{n}}\sum_{{t=1}}^n R_t,
\]
and the sample standard deviation is
\[
\sigma=\sqrt{{\frac{{1}}{{n-1}}\sum_{{t=1}}^n (R_t-\bar{{R}})^2}}.
\]
The Sharpe ratio is $\bar{{R}}/\sigma$.
The Sortino ratio uses the zero-return threshold:
\[
\sigma_d=\sqrt{{\frac{{1}}{{n}}\sum_{{t=1}}^n \min(R_t,0)^2}},
\qquad
\mathrm{{Sortino}}=\frac{{\bar{{R}}}}{{\sigma_d}}.
\]
The Omega ratio is
\[
\Omega=\frac{{\sum_{{t:R_t>0}} R_t}}{{\sum_{{t:R_t<0}} |R_t|}}.
\]

\section*{{Results}}
{tables}

\section*{{Brief Discussion}}
When $r_f=0.00\%$, leverage scales both average return and volatility almost proportionally.
Sharpe, Sortino, and Omega are unchanged across leverage levels because every portfolio return is a constant multiple of the same underlying S\&P 500 total return series.

When $r_f=0.25\%$, borrowing costs reduce the return earned at higher leverage levels.
The mean return still rises with $\lambda$, but Sharpe, Sortino, and Omega decline as leverage increases because the cost of financing lowers returns without reducing downside exposure.

When $r_f=0.50\%$, the effect of borrowing costs is stronger.
The higher-leverage portfolios still have larger mean returns, but the risk-adjusted ratios fall more sharply, showing that leverage is less attractive when the monthly financing cost is higher.

\end{{document}}
"""
    TEX_PATH.write_text(tex, encoding="utf-8")


def compile_pdf() -> str:
    pdflatex = shutil.which("pdflatex")
    if not pdflatex:
        tinytex = Path.home() / "AppData" / "Roaming" / "TinyTeX" / "bin" / "windows" / "pdflatex.exe"
        if tinytex.exists():
            pdflatex = str(tinytex)
    if not pdflatex:
        return "pdflatex not found, PDF not compiled."
    for _ in range(2):
        result = subprocess.run(
            [pdflatex, "-interaction=nonstopmode", TEX_PATH.name],
            cwd=OUT_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            (OUT_DIR / "Assignment_2_Leveraged_SP500_latex_error.log").write_text(
                result.stdout + "\n" + result.stderr,
                encoding="utf-8",
            )
            return "LaTeX compilation failed, see Assignment_2_Leveraged_SP500_latex_error.log."
    for suffix in [".aux", ".log", ".out"]:
        aux = TEX_PATH.with_suffix(suffix)
        if aux.exists():
            aux.unlink()
    return "Compiled PDF with pdflatex."


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    data = load_sp500_total_return_series()
    data.to_csv(CSV_PATH, index=False)
    returns = data["sp500tr_return_percent"].to_numpy(float)
    results = compute_all_results(returns)
    write_tex(results, len(returns))
    compile_status = compile_pdf()

    sanity = {
        "n": int(len(returns)),
        "lambda_1_rf_0": results[0.00].loc[results[0.00]["lambda_value"] == 1].iloc[0].to_dict(),
        "lambda_2_rf_025": results[0.25].loc[results[0.25]["lambda_value"] == 2].iloc[0].to_dict(),
        "compile_status": compile_status,
    }
    (OUT_DIR / "assignment2_manifest.json").write_text(json.dumps(sanity, indent=2), encoding="utf-8")
    print(json.dumps(sanity, indent=2))


if __name__ == "__main__":
    main()
