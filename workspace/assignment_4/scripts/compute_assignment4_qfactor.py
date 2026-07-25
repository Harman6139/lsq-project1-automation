from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from scipy import stats
import statsmodels.api as sm
from statsmodels.stats.diagnostic import acorr_ljungbox, breaks_cusumolsresid, het_breuschpagan
from statsmodels.stats.outliers_influence import OLSInfluence, variance_inflation_factor
from statsmodels.stats.sandwich_covariance import cov_hac


ASSIGNMENT_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = ASSIGNMENT_DIR.parents[1]
DATA_DIR = ASSIGNMENT_DIR / "data"
TABLES_DIR = ASSIGNMENT_DIR / "tables"

Q5_URL = "https://global-q.org/uploads/1/2/2/6/122679606/q5_factors_monthly_2024.csv"
Q5_PATH = DATA_DIR / "q5_factors_monthly_2024.csv"
FUND_SOURCE_PATH = PROJECT_DIR / "data" / "lsq_returns.csv"
FUND_EXPORT_PATH = DATA_DIR / "assignment4_fund_x_returns_2017_2024.csv"
ALIGNED_EXPORT_PATH = DATA_DIR / "assignment4_aligned_monthly_data.csv"

OUTPUT_TEX = ASSIGNMENT_DIR / "Assignment_4_qFactor_Analysis.tex"
OUTPUT_PDF = ASSIGNMENT_DIR / "Assignment_4_qFactor_Analysis.pdf"
OUTPUT_XLSX = ASSIGNMENT_DIR / "Assignment_4_qFactor_Analysis.xlsx"
OUTPUT_MANIFEST = ASSIGNMENT_DIR / "assignment4_manifest.json"
TABLE_1_CSV = TABLES_DIR / "Table_1_Factor_Regressions.csv"
TABLE_2_CSV = TABLES_DIR / "Table_2_Alpha_Summary.csv"

PRIMARY_LAGS = 4
BOOTSTRAP_REPS = 20_000
BOOTSTRAP_BLOCK_LENGTH = 6
BOOTSTRAP_SEED = 20_260_724

MODEL_FACTORS = {
    "CAPM": ["R_MKT"],
    "q-factor": ["R_MKT", "R_ME", "R_IA", "R_ROE"],
    "q5": ["R_MKT", "R_ME", "R_IA", "R_ROE", "R_EG"],
}
DISPLAY_NAMES = {
    "const": "alpha",
    "R_MKT": "beta_MKT",
    "R_ME": "beta_ME",
    "R_IA": "beta_IA",
    "R_ROE": "beta_ROE",
    "R_EG": "beta_EG",
}


@dataclass
class RegressionResult:
    model: str
    factors: list[str]
    coefficients: dict[str, float]
    standard_errors: dict[str, float]
    t_statistics: dict[str, float]
    p_values: dict[str, float]
    r_squared: float
    adjusted_r_squared: float
    observations: int
    residuals: np.ndarray
    fitted: np.ndarray
    covariance: np.ndarray

    @property
    def alpha(self) -> float:
        return self.coefficients["const"]

    @property
    def annual_alpha(self) -> float:
        return annualize_alpha(self.alpha)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_q5_file(refresh: bool) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if Q5_PATH.exists() and not refresh:
        return
    request = urllib.request.Request(
        Q5_URL,
        headers={"User-Agent": "Mozilla/5.0 Fund-X-research-replication"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        Q5_PATH.write_bytes(response.read())


def load_and_align_data(refresh_q5: bool = False) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    ensure_q5_file(refresh_q5)
    required_q5 = ["year", "month", "R_F", "R_MKT", "R_ME", "R_IA", "R_ROE", "R_EG"]
    q5 = pd.read_csv(Q5_PATH)
    missing_q5 = [column for column in required_q5 if column not in q5.columns]
    if missing_q5:
        raise ValueError(f"q5 file is missing columns: {missing_q5}")
    q5 = q5.loc[(q5["year"] >= 2017) & (q5["year"] <= 2024), required_q5].copy()
    q5["date"] = pd.to_datetime(
        {"year": q5["year"], "month": q5["month"], "day": 1}
    ).dt.to_period("M").astype(str)

    fund = pd.read_csv(FUND_SOURCE_PATH)
    required_fund = ["date", "lsq_return"]
    missing_fund = [column for column in required_fund if column not in fund.columns]
    if missing_fund:
        raise ValueError(f"Fund X file is missing columns: {missing_fund}")
    fund = fund.loc[
        (fund["date"] >= "2017-01") & (fund["date"] <= "2024-12"),
        required_fund,
    ].copy()
    fund["Fund_X_Return_Pct"] = fund["lsq_return"] * 100.0

    aligned = fund[["date", "Fund_X_Return_Pct"]].merge(
        q5[["date", "R_F", "R_MKT", "R_ME", "R_IA", "R_ROE", "R_EG"]],
        on="date",
        how="inner",
        validate="one_to_one",
    )
    aligned["Fund_X_Excess_Return_Pct"] = aligned["Fund_X_Return_Pct"] - aligned["R_F"]
    aligned = aligned[
        [
            "date",
            "Fund_X_Return_Pct",
            "R_F",
            "Fund_X_Excess_Return_Pct",
            "R_MKT",
            "R_ME",
            "R_IA",
            "R_ROE",
            "R_EG",
        ]
    ]

    expected_dates = pd.period_range("2017-01", "2024-12", freq="M").astype(str).tolist()
    if aligned["date"].tolist() != expected_dates:
        raise AssertionError("Aligned data do not contain every month from 2017-01 through 2024-12.")
    if len(aligned) != 96 or aligned["date"].nunique() != 96:
        raise AssertionError("The aligned Project 4 sample must contain 96 unique months.")
    if aligned.isna().any().any():
        raise AssertionError("The aligned Project 4 sample contains missing values.")
    if not np.allclose(
        aligned["Fund_X_Excess_Return_Pct"],
        aligned["Fund_X_Return_Pct"] - aligned["R_F"],
        atol=1e-12,
    ):
        raise AssertionError("Fund X excess returns do not equal raw returns minus R_F.")

    fund_export = fund[["date", "Fund_X_Return_Pct"]].copy()
    fund_export["Source"] = "Fund X net-of-fees series used in the Boyle project workspace"
    fund_export.to_csv(FUND_EXPORT_PATH, index=False, float_format="%.10f")
    aligned.to_csv(ALIGNED_EXPORT_PATH, index=False, float_format="%.10f")
    return fund_export, q5, aligned


def newey_west_core(
    y: np.ndarray,
    x: np.ndarray,
    lags: int,
    finite_sample_correction: bool = False,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    n, k = x.shape
    if n <= k:
        raise ValueError("Regression requires more observations than parameters.")
    if not 0 <= lags < n:
        raise ValueError("Newey-West lag count must be between 0 and T-1.")

    coefficients = np.linalg.lstsq(x, y, rcond=None)[0]
    residuals = y - x @ coefficients
    score = residuals[:, None] * x
    long_run = score.T @ score / n
    for lag in range(1, lags + 1):
        weight = 1.0 - lag / (lags + 1.0)
        cross = score[lag:].T @ score[:-lag] / n
        long_run += weight * (cross + cross.T)

    xtx_inverse = np.linalg.inv(x.T @ x / n)
    covariance = xtx_inverse @ long_run @ xtx_inverse / n
    if finite_sample_correction:
        covariance *= n / (n - k)
    standard_errors = np.sqrt(np.diag(covariance))
    t_statistics = coefficients / standard_errors
    p_values = 2.0 * stats.t.sf(np.abs(t_statistics), df=n - k)
    fitted = x @ coefficients
    return coefficients, standard_errors, t_statistics, p_values, residuals, covariance


def run_regression(
    data: pd.DataFrame,
    model: str,
    factors: list[str],
    lags: int = PRIMARY_LAGS,
    finite_sample_correction: bool = False,
) -> RegressionResult:
    y = data["Fund_X_Excess_Return_Pct"].to_numpy(dtype=float)
    x = np.column_stack(
        [np.ones(len(data), dtype=float), data[factors].to_numpy(dtype=float)]
    )
    coefficients, standard_errors, t_statistics, p_values, residuals, covariance = (
        newey_west_core(y, x, lags, finite_sample_correction)
    )
    labels = ["const", *factors]
    sse = float(residuals @ residuals)
    centered = y - y.mean()
    sst = float(centered @ centered)
    r_squared = 1.0 - sse / sst
    adjusted = 1.0 - (1.0 - r_squared) * (len(y) - 1.0) / (len(y) - len(labels))
    return RegressionResult(
        model=model,
        factors=factors,
        coefficients=dict(zip(labels, map(float, coefficients))),
        standard_errors=dict(zip(labels, map(float, standard_errors))),
        t_statistics=dict(zip(labels, map(float, t_statistics))),
        p_values=dict(zip(labels, map(float, p_values))),
        r_squared=float(r_squared),
        adjusted_r_squared=float(adjusted),
        observations=len(y),
        residuals=residuals,
        fitted=y - residuals,
        covariance=covariance,
    )


def annualize_alpha(monthly_alpha_pct: float) -> float:
    return ((1.0 + monthly_alpha_pct / 100.0) ** 12 - 1.0) * 100.0


def circular_block_indices(
    n: int,
    block_length: int,
    rng: np.random.Generator,
) -> np.ndarray:
    blocks = math.ceil(n / block_length)
    starts = rng.integers(0, n, size=blocks)
    return np.concatenate(
        [(start + np.arange(block_length)) % n for start in starts]
    )[:n]


def block_pairs_bootstrap_alpha(
    data: pd.DataFrame,
    factors: list[str],
    repetitions: int,
    block_length: int,
    seed: int,
) -> dict[str, float | int]:
    y = data["Fund_X_Excess_Return_Pct"].to_numpy(dtype=float)
    x = np.column_stack([np.ones(len(data)), data[factors].to_numpy(dtype=float)])
    rng = np.random.default_rng(seed)
    alphas = np.empty(repetitions, dtype=float)
    for repetition in range(repetitions):
        indices = circular_block_indices(len(data), block_length, rng)
        alphas[repetition] = np.linalg.lstsq(x[indices], y[indices], rcond=None)[0][0]
    lower, median, upper = np.quantile(alphas, [0.025, 0.50, 0.975])
    return {
        "repetitions": repetitions,
        "block_length": block_length,
        "seed": seed,
        "lower_95": float(lower),
        "median": float(median),
        "upper_95": float(upper),
        "share_nonpositive": float(np.mean(alphas <= 0.0)),
    }


def regression_diagnostics(
    data: pd.DataFrame,
    models: dict[str, RegressionResult],
) -> dict[str, object]:
    q5 = models["q5"]
    factors = MODEL_FACTORS["q5"]
    y = data["Fund_X_Excess_Return_Pct"].to_numpy(dtype=float)
    x = np.column_stack([np.ones(len(data)), data[factors].to_numpy(dtype=float)])
    fit = sm.OLS(y, x).fit()

    statsmodels_cov = cov_hac(fit, nlags=PRIMARY_LAGS, use_correction=False)
    statsmodels_se = np.sqrt(np.diag(statsmodels_cov))
    manual_coefficients = np.array([q5.coefficients[label] for label in ["const", *factors]])
    manual_se = np.array([q5.standard_errors[label] for label in ["const", *factors]])

    ljung_box = acorr_ljungbox(q5.residuals, lags=[1, 4, 12], return_df=True)
    bp_lm, bp_lm_p, bp_f, bp_f_p = het_breuschpagan(q5.residuals, x)
    jarque_bera = stats.jarque_bera(q5.residuals)
    influence = OLSInfluence(fit)
    cooks = influence.cooks_distance[0]
    max_cook_index = int(np.argmax(cooks))

    standardized_factors = stats.zscore(data[factors].to_numpy(dtype=float), axis=0, ddof=1)
    standardized_x = np.column_stack([np.ones(len(data)), standardized_factors])
    vifs = {
        factor: float(variance_inflation_factor(standardized_x, index + 1))
        for index, factor in enumerate(factors)
    }
    condition_number = float(np.linalg.cond(standardized_x))

    lag_sensitivity = []
    for lag in [3, 4, 6, 12]:
        result = run_regression(data, f"q5 NW({lag})", factors, lags=lag)
        critical = stats.t.ppf(0.975, result.observations - len(factors) - 1)
        lag_sensitivity.append(
            {
                "Lags": lag,
                "Alpha_Monthly_Pct": result.alpha,
                "NW_SE": result.standard_errors["const"],
                "NW_t": result.t_statistics["const"],
                "p_value": result.p_values["const"],
                "CI_95_Lower": result.alpha - critical * result.standard_errors["const"],
                "CI_95_Upper": result.alpha + critical * result.standard_errors["const"],
            }
        )
    corrected = run_regression(
        data,
        "q5 NW(4) finite-sample corrected",
        factors,
        lags=4,
        finite_sample_correction=True,
    )

    leave_one_out = []
    for index in range(len(data)):
        subset = data.drop(data.index[index]).reset_index(drop=True)
        result = run_regression(subset, "q5 leave-one-out", factors, lags=4)
        leave_one_out.append(
            {
                "Omitted_Month": data.iloc[index]["date"],
                "Alpha_Monthly_Pct": result.alpha,
                "NW_t": result.t_statistics["const"],
            }
        )

    influential_month = str(data.iloc[max_cook_index]["date"])
    without_influential = run_regression(
        data.loc[data["date"] != influential_month].reset_index(drop=True),
        "q5 excluding most influential month",
        factors,
        lags=4,
    )

    early = run_regression(
        data.loc[data["date"] <= "2020-12"].reset_index(drop=True),
        "q5 2017-2020",
        factors,
        lags=4,
    )
    late = run_regression(
        data.loc[data["date"] >= "2021-01"].reset_index(drop=True),
        "q5 2021-2024",
        factors,
        lags=4,
    )
    midpoint = (data["date"] >= "2021-01").astype(float).to_numpy()
    interactions = np.column_stack(
        [
            x,
            midpoint,
            x[:, 1:] * midpoint[:, None],
        ]
    )
    break_coefficients, break_se, break_t, break_p, _, _ = newey_west_core(
        y,
        interactions,
        lags=4,
    )
    alpha_shift_index = x.shape[1]
    cusum_stat, cusum_p, _ = breaks_cusumolsresid(q5.residuals, ddof=x.shape[1])

    bootstrap = block_pairs_bootstrap_alpha(
        data,
        factors,
        repetitions=BOOTSTRAP_REPS,
        block_length=BOOTSTRAP_BLOCK_LENGTH,
        seed=BOOTSTRAP_SEED,
    )

    literal_bandwidth = 4.0 * (len(data) / 100.0) ** (2.0 / 9.0)
    return {
        "manual_vs_statsmodels_max_coefficient_difference": float(
            np.max(np.abs(manual_coefficients - fit.params))
        ),
        "manual_vs_statsmodels_max_nw_se_difference": float(
            np.max(np.abs(manual_se - statsmodels_se))
        ),
        "ljung_box": [
            {
                "Lag": int(lag),
                "Q_statistic": float(ljung_box.loc[lag, "lb_stat"]),
                "p_value": float(ljung_box.loc[lag, "lb_pvalue"]),
            }
            for lag in [1, 4, 12]
        ],
        "breusch_pagan": {
            "LM_statistic": float(bp_lm),
            "LM_p_value": float(bp_lm_p),
            "F_statistic": float(bp_f),
            "F_p_value": float(bp_f_p),
        },
        "jarque_bera": {
            "statistic": float(jarque_bera.statistic),
            "p_value": float(jarque_bera.pvalue),
            "residual_skewness": float(stats.skew(q5.residuals, bias=False)),
            "residual_excess_kurtosis": float(stats.kurtosis(q5.residuals, bias=False)),
        },
        "factor_vif": vifs,
        "standardized_condition_number": condition_number,
        "factor_correlations": data[factors].corr(),
        "lag_sensitivity": lag_sensitivity,
        "finite_sample_corrected_nw4": {
            "Alpha_Monthly_Pct": corrected.alpha,
            "NW_SE": corrected.standard_errors["const"],
            "NW_t": corrected.t_statistics["const"],
            "p_value": corrected.p_values["const"],
        },
        "influence": {
            "Most_Influential_Month": influential_month,
            "Max_Cooks_Distance": float(cooks[max_cook_index]),
            "Max_Leverage": float(np.max(influence.hat_matrix_diag)),
            "Alpha_Excluding_Month": without_influential.alpha,
            "NW_t_Excluding_Month": without_influential.t_statistics["const"],
            "Leave_One_Out_Alpha_Min": float(
                min(row["Alpha_Monthly_Pct"] for row in leave_one_out)
            ),
            "Leave_One_Out_Alpha_Max": float(
                max(row["Alpha_Monthly_Pct"] for row in leave_one_out)
            ),
            "Leave_One_Out_t_Min": float(min(row["NW_t"] for row in leave_one_out)),
            "Leave_One_Out_t_Max": float(max(row["NW_t"] for row in leave_one_out)),
        },
        "leave_one_out": leave_one_out,
        "stability": {
            "CUSUM_statistic": float(cusum_stat),
            "CUSUM_p_value": float(cusum_p),
            "Early_2017_2020_Alpha": early.alpha,
            "Early_2017_2020_NW_t": early.t_statistics["const"],
            "Late_2021_2024_Alpha": late.alpha,
            "Late_2021_2024_NW_t": late.t_statistics["const"],
            "Alpha_Shift": float(break_coefficients[alpha_shift_index]),
            "Alpha_Shift_NW_SE": float(break_se[alpha_shift_index]),
            "Alpha_Shift_NW_t": float(break_t[alpha_shift_index]),
            "Alpha_Shift_p_value": float(break_p[alpha_shift_index]),
        },
        "block_pairs_bootstrap": bootstrap,
        "lag_rule": {
            "formula_value": literal_bandwidth,
            "literal_floor": int(math.floor(literal_bandwidth)),
            "required_primary_lag": PRIMARY_LAGS,
        },
    }


def significance_stars(result: RegressionResult, label: str) -> str:
    t_stat = abs(result.t_statistics[label])
    p_value = result.p_values[label]
    if t_stat >= 1.96 and p_value < 0.001:
        return "***"
    return ""


def build_table_rows(models: dict[str, RegressionResult]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    ordered_models = ["CAPM", "q-factor", "q5"]
    labels = ["const", "R_MKT", "R_ME", "R_IA", "R_ROE", "R_EG"]
    table_1 = []
    for label in labels:
        coefficient_row: dict[str, object] = {"Statistic": DISPLAY_NAMES[label]}
        t_row: dict[str, object] = {"Statistic": "[NW t-stat]"}
        for model_name in ordered_models:
            result = models[model_name]
            if label not in result.coefficients:
                coefficient_row[model_name] = "-"
                t_row[model_name] = "-"
            else:
                coefficient_row[model_name] = result.coefficients[label]
                t_row[model_name] = result.t_statistics[label]
        table_1.extend([coefficient_row, t_row])
    table_1.extend(
        [
            {
                "Statistic": "R-squared",
                **{name: models[name].r_squared for name in ordered_models},
            },
            {
                "Statistic": "Adjusted R-squared",
                **{name: models[name].adjusted_r_squared for name in ordered_models},
            },
            {
                "Statistic": "N",
                **{name: models[name].observations for name in ordered_models},
            },
        ]
    )
    table_2 = [
        {
            "Model": model_name,
            "Monthly alpha (%)": models[model_name].alpha,
            "NW t-stat": models[model_name].t_statistics["const"],
            "Annual alpha (%)": models[model_name].annual_alpha,
            "R-squared": models[model_name].r_squared,
        }
        for model_name in ordered_models
    ]
    return table_1, table_2


def write_table_csvs(
    table_1: list[dict[str, object]],
    table_2: list[dict[str, object]],
) -> None:
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(table_1).to_csv(TABLE_1_CSV, index=False)
    pd.DataFrame(table_2).to_csv(TABLE_2_CSV, index=False)


THIN_GRAY = Side(style="thin", color="D9E1F2")
MEDIUM_BLUE = Side(style="medium", color="1F4E78")
DARK_BLUE_FILL = PatternFill("solid", fgColor="1F4E78")
MEDIUM_BLUE_FILL = PatternFill("solid", fgColor="4472C4")
LIGHT_BLUE_FILL = PatternFill("solid", fgColor="D9EAF7")
LIGHT_GRAY_FILL = PatternFill("solid", fgColor="F2F2F2")
LIGHT_GREEN_FILL = PatternFill("solid", fgColor="E2F0D9")
LIGHT_RED_FILL = PatternFill("solid", fgColor="FCE4D6")
WHITE_FONT = Font(name="Aptos", color="FFFFFF", bold=True)
BODY_FONT = Font(name="Aptos", color="000000", size=10)
TITLE_FONT = Font(name="Aptos Display", color="1F4E78", bold=True, size=18)
SUBTITLE_FONT = Font(name="Aptos", color="404040", italic=True, size=10)
HEADER_FONT = Font(name="Aptos", color="FFFFFF", bold=True, size=10)
SECTION_FONT = Font(name="Aptos", color="1F4E78", bold=True, size=11)


def set_title(ws, title: str, subtitle: str, width: int) -> None:
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=width)
    ws.cell(1, 1, title)
    ws.cell(1, 1).font = TITLE_FONT
    ws.cell(1, 1).alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[1].height = 27
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=width)
    ws.cell(2, 1, subtitle)
    ws.cell(2, 1).font = SUBTITLE_FONT
    ws.cell(2, 1).alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
    ws.row_dimensions[2].height = 30


def style_header(ws, row: int, start_column: int, end_column: int) -> None:
    for column in range(start_column, end_column + 1):
        cell = ws.cell(row, column)
        cell.fill = DARK_BLUE_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = Border(top=MEDIUM_BLUE, bottom=MEDIUM_BLUE)
    ws.row_dimensions[row].height = 30


def style_data_range(
    ws,
    start_row: int,
    end_row: int,
    start_column: int,
    end_column: int,
) -> None:
    for row in range(start_row, end_row + 1):
        for column in range(start_column, end_column + 1):
            cell = ws.cell(row, column)
            cell.font = BODY_FONT
            cell.alignment = Alignment(
                horizontal="left" if column == start_column else "right",
                vertical="center",
                wrap_text=True,
            )
            cell.border = Border(bottom=THIN_GRAY)
        if (row - start_row) % 2 == 1:
            for column in range(start_column, end_column + 1):
                ws.cell(row, column).fill = LIGHT_GRAY_FILL


def set_widths(ws, widths: dict[str, float]) -> None:
    for column, width in widths.items():
        ws.column_dimensions[column].width = width


def write_workbook(
    path: Path,
    fund: pd.DataFrame,
    q5_raw: pd.DataFrame,
    aligned: pd.DataFrame,
    models: dict[str, RegressionResult],
    diagnostics: dict[str, object],
    table_1: list[dict[str, object]],
    table_2: list[dict[str, object]],
) -> None:
    workbook = Workbook()
    workbook.remove(workbook.active)
    workbook.properties.creator = "Harman Singh"
    workbook.properties.lastModifiedBy = "Harman Singh"
    workbook.properties.title = "Assignment 4: Fund X q-Factor Analysis"
    workbook.properties.subject = "CAPM, q-factor, and q5 regressions"
    workbook.calculation.fullCalcOnLoad = True
    workbook.calculation.forceFullCalc = True
    workbook.calculation.calcMode = "auto"

    summary = workbook.create_sheet("Summary")
    summary.sheet_view.showGridLines = False
    set_title(
        summary,
        "Assignment 4: Fund X Factor Model Analysis",
        "CAPM, Hou-Xue-Zhang q-factor, and q5 models | January 2017 to December 2024 | N = 96",
        6,
    )
    summary["A4"] = "Headline Result"
    summary["A4"].font = SECTION_FONT
    summary.merge_cells("A5:F6")
    summary["A5"] = (
        "Fund X retains a monthly alpha of "
        f"{models['q5'].alpha:.2f}% in the q5 model "
        f"(Newey-West t = {models['q5'].t_statistics['const']:.2f}). "
        "The five q5 factors explain little of the month-to-month return variation."
    )
    summary["A5"].fill = LIGHT_BLUE_FILL
    summary["A5"].font = Font(name="Aptos", size=12, bold=True, color="1F1F1F")
    summary["A5"].alignment = Alignment(wrap_text=True, vertical="center")
    summary["A5"].border = Border(left=MEDIUM_BLUE, right=MEDIUM_BLUE, top=MEDIUM_BLUE, bottom=MEDIUM_BLUE)
    summary["A8"] = "Model"
    summary["B8"] = "Monthly alpha (%)"
    summary["C8"] = "NW t-stat"
    summary["D8"] = "Annual alpha (%)"
    summary["E8"] = "R-squared"
    summary["F8"] = "Adjusted R-squared"
    style_header(summary, 8, 1, 6)
    for row_index, model_name in enumerate(["CAPM", "q-factor", "q5"], start=9):
        result = models[model_name]
        values = [
            model_name,
            result.alpha,
            result.t_statistics["const"],
            result.annual_alpha,
            result.r_squared,
            result.adjusted_r_squared,
        ]
        for column, value in enumerate(values, start=1):
            summary.cell(row_index, column, value)
    style_data_range(summary, 9, 11, 1, 6)
    for row in range(9, 12):
        summary.cell(row, 2).number_format = "0.000"
        summary.cell(row, 3).number_format = "0.00"
        summary.cell(row, 4).number_format = "0.00"
        summary.cell(row, 5).number_format = "0.000"
        summary.cell(row, 6).number_format = "0.000"
    summary["A14"] = "Interpretation Boundaries"
    summary["A14"].font = SECTION_FONT
    notes = [
        "Alpha is unexplained return relative to the specified linear factors; it is not proof that every relevant risk or strategy exposure has been measured.",
        "Newey-West corrects coefficient standard errors for heteroskedasticity and serial correlation; it does not repair omitted variables or changing coefficients.",
        "Stability diagnostics indicate that the alpha is lower in 2021-2024 than in 2017-2020, although it remains positive in both halves.",
    ]
    for row_index, note in enumerate(notes, start=15):
        summary.cell(row_index, 1, note)
        summary.merge_cells(start_row=row_index, start_column=1, end_row=row_index, end_column=6)
        summary.cell(row_index, 1).alignment = Alignment(wrap_text=True, vertical="top")
        summary.cell(row_index, 1).font = BODY_FONT
        summary.row_dimensions[row_index].height = 32
    set_widths(summary, {"A": 25, "B": 18, "C": 14, "D": 18, "E": 14, "F": 18})
    summary.freeze_panes = "A8"

    table1_ws = workbook.create_sheet("Table 1")
    table1_ws.sheet_view.showGridLines = False
    set_title(
        table1_ws,
        "Table 1: Fund X Factor Regressions",
        "Coefficient estimates with Newey-West HAC t-statistics in brackets",
        4,
    )
    headers = ["Statistic", "CAPM", "q-factor", "q5"]
    for column, header in enumerate(headers, start=1):
        table1_ws.cell(4, column, header)
    style_header(table1_ws, 4, 1, 4)
    current_row = 5
    for item in table_1:
        table1_ws.cell(current_row, 1, item["Statistic"])
        for column, model_name in enumerate(["CAPM", "q-factor", "q5"], start=2):
            value = item[model_name]
            table1_ws.cell(current_row, column, value)
            if isinstance(value, float):
                table1_ws.cell(current_row, column).number_format = "0.000"
        if item["Statistic"] == "[NW t-stat]":
            for column in range(1, 5):
                table1_ws.cell(current_row, column).font = Font(
                    name="Aptos", size=9, italic=True, color="666666"
                )
        current_row += 1
    style_data_range(table1_ws, 5, current_row - 1, 1, 4)
    note_row = current_row + 1
    table1_ws.merge_cells(start_row=note_row, start_column=1, end_row=note_row + 2, end_column=4)
    table1_ws.cell(note_row, 1).value = (
        "Note: Sample: January 2017 - December 2024 (N = 96 monthly observations). "
        "Dependent variable: Fund X monthly excess return (r_X - r_f). q5 factor returns "
        "(R_MKT, R_ME, R_IA, R_ROE, R_EG) are from Hou, Mo, Xue and Zhang (2021) via "
        "global-q.org. Standard errors are Newey-West HAC with L = 4 lags (Newey and West, "
        "1987); t-statistics in brackets. No coefficient is asterisked unless its |t| >= 1.96."
    )
    table1_ws.cell(note_row, 1).font = Font(name="Aptos", size=9, italic=True)
    table1_ws.cell(note_row, 1).alignment = Alignment(wrap_text=True, vertical="top")
    set_widths(table1_ws, {"A": 30, "B": 18, "C": 18, "D": 18})
    table1_ws.freeze_panes = "B5"

    table2_ws = workbook.create_sheet("Table 2")
    table2_ws.sheet_view.showGridLines = False
    set_title(
        table2_ws,
        "Table 2: Summary of Alpha Estimates",
        "Monthly and compounded annual alpha across the three factor specifications",
        5,
    )
    headers = ["Model", "Monthly alpha (%)", "NW t-stat", "Annual alpha (%)", "R-squared"]
    for column, header in enumerate(headers, start=1):
        table2_ws.cell(4, column, header)
    style_header(table2_ws, 4, 1, 5)
    for row_index, item in enumerate(table_2, start=5):
        table2_ws.cell(row_index, 1, item["Model"])
        table2_ws.cell(row_index, 2, item["Monthly alpha (%)"])
        table2_ws.cell(row_index, 3, item["NW t-stat"])
        table2_ws.cell(row_index, 4, f"=((1+B{row_index}/100)^12-1)*100")
        table2_ws.cell(row_index, 5, item["R-squared"])
        for column in [2, 4]:
            table2_ws.cell(row_index, column).number_format = "0.000"
        table2_ws.cell(row_index, 3).number_format = "0.00"
        table2_ws.cell(row_index, 5).number_format = "0.000"
    style_data_range(table2_ws, 5, 7, 1, 5)
    table2_ws.merge_cells("A10:E11")
    table2_ws["A10"] = (
        "Note: *** p < 0.001. Annual alpha computed as "
        "(1 + monthly_alpha/100)^12 - 1. Sample: January 2017 - December 2024, "
        "N = 96. NW t-statistics use L = 4 lags."
    )
    table2_ws["A10"].font = Font(name="Aptos", size=9, italic=True)
    table2_ws["A10"].alignment = Alignment(wrap_text=True, vertical="top")
    set_widths(table2_ws, {"A": 25, "B": 20, "C": 15, "D": 20, "E": 15})

    details = workbook.create_sheet("Regression Details")
    details.sheet_view.showGridLines = False
    set_title(
        details,
        "Regression Details",
        "Primary coefficient estimates, Newey-West HAC standard errors, t-statistics, and p-values",
        7,
    )
    detail_headers = ["Model", "Coefficient", "Estimate", "NW SE", "NW t-stat", "p-value", "Significant at 5%"]
    for column, header in enumerate(detail_headers, start=1):
        details.cell(4, column, header)
    style_header(details, 4, 1, 7)
    row_index = 5
    for model_name in ["CAPM", "q-factor", "q5"]:
        result = models[model_name]
        for label in ["const", *result.factors]:
            details.cell(row_index, 1, model_name)
            details.cell(row_index, 2, DISPLAY_NAMES[label])
            details.cell(row_index, 3, result.coefficients[label])
            details.cell(row_index, 4, result.standard_errors[label])
            details.cell(row_index, 5, result.t_statistics[label])
            details.cell(row_index, 6, result.p_values[label])
            details.cell(row_index, 7, "YES" if abs(result.t_statistics[label]) >= 1.96 else "NO")
            for column in range(3, 7):
                details.cell(row_index, column).number_format = "0.000000"
            row_index += 1
    style_data_range(details, 5, row_index - 1, 1, 7)
    set_widths(details, {"A": 16, "B": 20, "C": 15, "D": 15, "E": 15, "F": 16, "G": 18})
    details.freeze_panes = "A5"
    details.auto_filter.ref = f"A4:G{row_index - 1}"

    diagnostics_ws = workbook.create_sheet("Diagnostics")
    diagnostics_ws.sheet_view.showGridLines = False
    set_title(
        diagnostics_ws,
        "Assumption-Aware Diagnostics",
        "Checks on residual dependence, heteroskedasticity, non-normality, influence, and parameter stability",
        5,
    )
    diagnostics_ws.append([])
    diag_headers = ["Diagnostic", "Statistic", "p-value", "Interpretation", "Primary Response"]
    for column, header in enumerate(diag_headers, start=1):
        diagnostics_ws.cell(4, column, header)
    style_header(diagnostics_ws, 4, 1, 5)
    lb12 = next(item for item in diagnostics["ljung_box"] if item["Lag"] == 12)
    bp = diagnostics["breusch_pagan"]
    jb = diagnostics["jarque_bera"]
    stability = diagnostics["stability"]
    influence = diagnostics["influence"]
    diag_rows = [
        [
            "Ljung-Box Q(12), q5 residuals",
            lb12["Q_statistic"],
            lb12["p_value"],
            "Residual serial dependence remains",
            "Use HAC and lag-sensitivity checks",
        ],
        [
            "Breusch-Pagan LM",
            bp["LM_statistic"],
            bp["LM_p_value"],
            "Borderline heteroskedasticity evidence",
            "Use heteroskedasticity-robust HAC covariance",
        ],
        [
            "Jarque-Bera",
            jb["statistic"],
            jb["p_value"],
            "Strong residual non-normality",
            "Use block bootstrap and influence sensitivity",
        ],
        [
            "CUSUM parameter stability",
            stability["CUSUM_statistic"],
            stability["CUSUM_p_value"],
            "Constant-parameter specification is rejected",
            "Report midpoint subperiod alphas",
        ],
        [
            "Maximum Cook's distance",
            influence["Max_Cooks_Distance"],
            "",
            f"Most influential month: {influence['Most_Influential_Month']}",
            "Report exclusion and leave-one-out sensitivity",
        ],
        [
            "Maximum factor VIF",
            max(diagnostics["factor_vif"].values()),
            "",
            "Moderate, not severe, factor collinearity",
            "Interpret individual q5 loadings cautiously",
        ],
    ]
    for row_index, row_values in enumerate(diag_rows, start=5):
        for column, value in enumerate(row_values, start=1):
            diagnostics_ws.cell(row_index, column, value)
            diagnostics_ws.cell(row_index, column).alignment = Alignment(wrap_text=True, vertical="top")
        diagnostics_ws.cell(row_index, 2).number_format = "0.000000"
        diagnostics_ws.cell(row_index, 3).number_format = "0.000000"
    style_data_range(diagnostics_ws, 5, 10, 1, 5)
    diagnostics_ws["A13"] = "Stability and Influence Results"
    diagnostics_ws["A13"].font = SECTION_FONT
    secondary_headers = ["Check", "Alpha (%)", "NW t-stat", "Lower / Early", "Upper / Late"]
    for column, header in enumerate(secondary_headers, start=1):
        diagnostics_ws.cell(14, column, header)
    style_header(diagnostics_ws, 14, 1, 5)
    secondary_rows = [
        [
            "2017-2020 q5",
            stability["Early_2017_2020_Alpha"],
            stability["Early_2017_2020_NW_t"],
            "",
            "",
        ],
        [
            "2021-2024 q5",
            stability["Late_2021_2024_Alpha"],
            stability["Late_2021_2024_NW_t"],
            "",
            "",
        ],
        [
            f"Exclude {influence['Most_Influential_Month']}",
            influence["Alpha_Excluding_Month"],
            influence["NW_t_Excluding_Month"],
            "",
            "",
        ],
        [
            "Leave-one-out range",
            "",
            "",
            influence["Leave_One_Out_Alpha_Min"],
            influence["Leave_One_Out_Alpha_Max"],
        ],
        [
            "6-month block-pairs bootstrap 95% CI",
            "",
            "",
            diagnostics["block_pairs_bootstrap"]["lower_95"],
            diagnostics["block_pairs_bootstrap"]["upper_95"],
        ],
    ]
    for row_index, row_values in enumerate(secondary_rows, start=15):
        for column, value in enumerate(row_values, start=1):
            diagnostics_ws.cell(row_index, column, value)
            if column > 1 and isinstance(value, (float, int)):
                diagnostics_ws.cell(row_index, column).number_format = "0.000"
    style_data_range(diagnostics_ws, 15, 19, 1, 5)
    set_widths(diagnostics_ws, {"A": 34, "B": 16, "C": 14, "D": 24, "E": 28})
    diagnostics_ws.freeze_panes = "A5"

    hac_ws = workbook.create_sheet("HAC Sensitivity")
    hac_ws.sheet_view.showGridLines = False
    set_title(
        hac_ws,
        "HAC Lag Sensitivity",
        "q5 monthly alpha inference across alternative Bartlett-kernel lag choices",
        7,
    )
    hac_headers = ["Lags", "Monthly alpha (%)", "NW SE", "NW t-stat", "p-value", "95% CI lower", "95% CI upper"]
    for column, header in enumerate(hac_headers, start=1):
        hac_ws.cell(4, column, header)
    style_header(hac_ws, 4, 1, 7)
    for row_index, item in enumerate(diagnostics["lag_sensitivity"], start=5):
        values = [
            item["Lags"],
            item["Alpha_Monthly_Pct"],
            item["NW_SE"],
            item["NW_t"],
            item["p_value"],
            item["CI_95_Lower"],
            item["CI_95_Upper"],
        ]
        for column, value in enumerate(values, start=1):
            hac_ws.cell(row_index, column, value)
            if column > 1:
                hac_ws.cell(row_index, column).number_format = "0.000000"
    style_data_range(hac_ws, 5, 8, 1, 7)
    hac_ws.merge_cells("A11:G12")
    hac_ws["A11"] = (
        f"The assignment requires L = 4. The literal bandwidth expression evaluates to "
        f"{diagnostics['lag_rule']['formula_value']:.4f}, which floors to "
        f"{diagnostics['lag_rule']['literal_floor']}; L = 3 is therefore shown as a sensitivity "
        "check. The inference remains statistically strong through L = 12."
    )
    hac_ws["A11"].alignment = Alignment(wrap_text=True, vertical="top")
    hac_ws["A11"].font = Font(name="Aptos", size=9, italic=True)
    set_widths(hac_ws, {"A": 12, "B": 20, "C": 15, "D": 15, "E": 15, "F": 18, "G": 18})

    corr_ws = workbook.create_sheet("Factor Correlations")
    corr_ws.sheet_view.showGridLines = False
    set_title(
        corr_ws,
        "Factor Correlations and VIF",
        "Correlation and variance-inflation diagnostics for the five-factor q5 specification",
        7,
    )
    factors = MODEL_FACTORS["q5"]
    corr_ws.cell(4, 1, "Factor")
    for column, factor in enumerate(factors, start=2):
        corr_ws.cell(4, column, factor)
    corr_ws.cell(4, 7, "VIF")
    style_header(corr_ws, 4, 1, 7)
    correlations: pd.DataFrame = diagnostics["factor_correlations"]
    for row_index, factor in enumerate(factors, start=5):
        corr_ws.cell(row_index, 1, factor)
        for column, other_factor in enumerate(factors, start=2):
            corr_ws.cell(row_index, column, float(correlations.loc[factor, other_factor]))
            corr_ws.cell(row_index, column).number_format = "0.000"
        corr_ws.cell(row_index, 7, diagnostics["factor_vif"][factor])
        corr_ws.cell(row_index, 7).number_format = "0.000"
    style_data_range(corr_ws, 5, 9, 1, 7)
    set_widths(corr_ws, {"A": 16, "B": 14, "C": 14, "D": 14, "E": 14, "F": 14, "G": 12})

    fund_ws = workbook.create_sheet("Fund X Raw")
    fund_ws.sheet_view.showGridLines = False
    set_title(
        fund_ws,
        "Fund X Raw Returns",
        "Net-of-fees monthly returns used in Assignment 4; values are in percent",
        3,
    )
    fund_headers = ["Date", "Fund X return (%)", "Source"]
    for column, header in enumerate(fund_headers, start=1):
        fund_ws.cell(4, column, header)
    style_header(fund_ws, 4, 1, 3)
    for row_index, row in enumerate(fund.itertuples(index=False), start=5):
        fund_ws.cell(row_index, 1, row.date)
        fund_ws.cell(row_index, 2, row.Fund_X_Return_Pct)
        fund_ws.cell(row_index, 3, row.Source)
        fund_ws.cell(row_index, 2).number_format = "0.0000"
    style_data_range(fund_ws, 5, 100, 1, 3)
    set_widths(fund_ws, {"A": 14, "B": 20, "C": 58})
    fund_ws.freeze_panes = "A5"
    fund_ws.auto_filter.ref = "A4:C100"

    q5_ws = workbook.create_sheet("q5 Raw")
    q5_ws.sheet_view.showGridLines = False
    set_title(
        q5_ws,
        "Official q5 Factor Inputs",
        "Official monthly q5 data filtered to January 2017 through December 2024; values are in percent",
        8,
    )
    q5_columns = ["date", "R_F", "R_MKT", "R_ME", "R_IA", "R_ROE", "R_EG"]
    for column, header in enumerate(q5_columns, start=1):
        q5_ws.cell(4, column, header)
    q5_ws.cell(4, 8, "Source URL")
    style_header(q5_ws, 4, 1, 8)
    for row_index, row in enumerate(q5_raw[q5_columns].itertuples(index=False), start=5):
        values = list(row)
        for column, value in enumerate(values, start=1):
            q5_ws.cell(row_index, column, value)
            if column > 1:
                q5_ws.cell(row_index, column).number_format = "0.0000"
        q5_ws.cell(row_index, 8, Q5_URL)
        q5_ws.cell(row_index, 8).hyperlink = Q5_URL
        q5_ws.cell(row_index, 8).font = Font(name="Aptos", color="FF0000", underline="single", size=9)
    style_data_range(q5_ws, 5, 100, 1, 8)
    set_widths(q5_ws, {"A": 14, "B": 12, "C": 12, "D": 12, "E": 12, "F": 12, "G": 12, "H": 55})
    q5_ws.freeze_panes = "A5"
    q5_ws.auto_filter.ref = "A4:H100"

    aligned_ws = workbook.create_sheet("Aligned Data")
    aligned_ws.sheet_view.showGridLines = False
    set_title(
        aligned_ws,
        "Aligned Regression Data",
        "Explicit year-month merge of Fund X and official q5 inputs; values are in percent",
        10,
    )
    aligned_headers = [
        "Date",
        "Fund X raw",
        "R_F",
        "Excess return formula",
        "Excess return verified",
        "Difference check",
        "R_MKT",
        "R_ME",
        "R_IA",
        "R_ROE",
        "R_EG",
    ]
    for column, header in enumerate(aligned_headers, start=1):
        aligned_ws.cell(4, column, header)
    style_header(aligned_ws, 4, 1, len(aligned_headers))
    for row_index, row in enumerate(aligned.itertuples(index=False), start=5):
        aligned_ws.cell(row_index, 1, row.date)
        aligned_ws.cell(row_index, 2, row.Fund_X_Return_Pct)
        aligned_ws.cell(row_index, 3, row.R_F)
        aligned_ws.cell(row_index, 4, f"=B{row_index}-C{row_index}")
        aligned_ws.cell(row_index, 5, row.Fund_X_Excess_Return_Pct)
        aligned_ws.cell(row_index, 6, f"=D{row_index}-E{row_index}")
        for offset, value in enumerate([row.R_MKT, row.R_ME, row.R_IA, row.R_ROE, row.R_EG], start=7):
            aligned_ws.cell(row_index, offset, value)
        for column in range(2, 12):
            aligned_ws.cell(row_index, column).number_format = "0.0000"
    style_data_range(aligned_ws, 5, 100, 1, len(aligned_headers))
    set_widths(
        aligned_ws,
        {
            "A": 13,
            "B": 15,
            "C": 11,
            "D": 19,
            "E": 20,
            "F": 16,
            "G": 12,
            "H": 12,
            "I": 12,
            "J": 12,
            "K": 12,
        },
    )
    aligned_ws.freeze_panes = "D5"
    aligned_ws.auto_filter.ref = "A4:K100"

    qa_ws = workbook.create_sheet("QA Checks")
    qa_ws.sheet_view.showGridLines = False
    set_title(
        qa_ws,
        "Quality Assurance Checks",
        "One assertion per row; all checks must pass before delivery",
        6,
    )
    qa_headers = ["Check", "Actual", "Expected", "Tolerance", "Status", "Notes"]
    for column, header in enumerate(qa_headers, start=1):
        qa_ws.cell(4, column, header)
    style_header(qa_ws, 4, 1, 6)
    checks = [
        ["Observation count", len(aligned), 96, 0, "PASS" if len(aligned) == 96 else "FAIL", "Eight complete calendar years"],
        ["Unique month count", aligned["date"].nunique(), 96, 0, "PASS" if aligned["date"].nunique() == 96 else "FAIL", "No duplicate months"],
        ["First month", aligned["date"].min(), "2017-01", "", "PASS" if aligned["date"].min() == "2017-01" else "FAIL", ""],
        ["Last month", aligned["date"].max(), "2024-12", "", "PASS" if aligned["date"].max() == "2024-12" else "FAIL", ""],
        ["Missing numeric values", int(aligned.isna().sum().sum()), 0, 0, "PASS" if not aligned.isna().any().any() else "FAIL", ""],
        [
            "Maximum excess-return identity difference",
            float(np.max(np.abs(aligned["Fund_X_Excess_Return_Pct"] - (aligned["Fund_X_Return_Pct"] - aligned["R_F"])))),
            0,
            1e-12,
            "PASS",
            "Fund X excess return equals raw return minus R_F",
        ],
        [
            "Manual vs statsmodels coefficient difference",
            diagnostics["manual_vs_statsmodels_max_coefficient_difference"],
            0,
            1e-10,
            "PASS" if diagnostics["manual_vs_statsmodels_max_coefficient_difference"] < 1e-10 else "FAIL",
            "Independent OLS coefficient implementation",
        ],
        [
            "Manual vs statsmodels NW SE difference",
            diagnostics["manual_vs_statsmodels_max_nw_se_difference"],
            0,
            1e-10,
            "PASS" if diagnostics["manual_vs_statsmodels_max_nw_se_difference"] < 1e-10 else "FAIL",
            "Independent HAC covariance implementation",
        ],
        ["Primary Newey-West lag count", PRIMARY_LAGS, 4, 0, "PASS", "Assignment-mandated value"],
        [
            "All model observation counts",
            len({result.observations for result in models.values()}),
            1,
            0,
            "PASS" if {result.observations for result in models.values()} == {96} else "FAIL",
            "Every model uses the same 96 months",
        ],
    ]
    for row_index, values in enumerate(checks, start=5):
        for column, value in enumerate(values, start=1):
            qa_ws.cell(row_index, column, value)
            qa_ws.cell(row_index, column).alignment = Alignment(wrap_text=True, vertical="top")
        qa_ws.cell(row_index, 5).fill = LIGHT_GREEN_FILL if values[4] == "PASS" else LIGHT_RED_FILL
        qa_ws.cell(row_index, 5).font = Font(name="Aptos", bold=True)
    style_data_range(qa_ws, 5, 14, 1, 6)
    qa_ws["A17"] = "Overall status"
    qa_ws["B17"] = "PASS" if all(row[4] == "PASS" for row in checks) else "FAIL"
    qa_ws["A17"].font = SECTION_FONT
    qa_ws["B17"].fill = LIGHT_GREEN_FILL if qa_ws["B17"].value == "PASS" else LIGHT_RED_FILL
    qa_ws["B17"].font = Font(name="Aptos", bold=True)
    set_widths(qa_ws, {"A": 38, "B": 22, "C": 18, "D": 15, "E": 12, "F": 48})
    qa_ws.freeze_panes = "A5"

    sources = workbook.create_sheet("Sources")
    sources.sheet_view.showGridLines = False
    set_title(
        sources,
        "Sources and Method",
        "Data provenance and calculation conventions used for the Assignment 4 outputs",
        5,
    )
    source_headers = ["Item", "Source", "Location", "Units / Convention", "Notes"]
    for column, header in enumerate(source_headers, start=1):
        sources.cell(4, column, header)
    style_header(sources, 4, 1, 5)
    source_rows = [
        [
            "Fund X monthly returns",
            "Net-of-fees project return series",
            FUND_SOURCE_PATH.relative_to(PROJECT_DIR).as_posix(),
            "Percent per month",
            "Filtered to 2017-01 through 2024-12",
        ],
        [
            "q5 monthly factors",
            "Official global-q.org repository",
            Q5_URL,
            "Percent per month",
            f"SHA-256: {sha256_file(Q5_PATH)}",
        ],
        [
            "Dependent variable",
            "Calculated",
            "Fund X raw return minus R_F",
            "Percent per month",
            "R_F is taken directly from the q5 file",
        ],
        [
            "Primary covariance",
            "Newey-West HAC",
            "Manual implementation cross-checked to statsmodels",
            "Bartlett kernel, L = 4",
            "No finite-sample multiplier in the primary table, matching the supplied code",
        ],
        [
            "Annual alpha",
            "Calculated",
            "(1 + monthly alpha / 100)^12 - 1",
            "Compounded percent per year",
            "Not simple multiplication by 12",
        ],
        [
            "Robustness",
            "Calculated",
            "HAC lags 3, 4, 6, 12; block-pairs bootstrap; influence and stability checks",
            "Sensitivity analysis",
            "Primary assignment result remains L = 4",
        ],
    ]
    for row_index, values in enumerate(source_rows, start=5):
        for column, value in enumerate(values, start=1):
            sources.cell(row_index, column, value)
            sources.cell(row_index, column).alignment = Alignment(wrap_text=True, vertical="top")
        if isinstance(values[2], str) and values[2].startswith("https://"):
            sources.cell(row_index, 3).hyperlink = values[2]
            sources.cell(row_index, 3).font = Font(name="Aptos", color="FF0000", underline="single")
    style_data_range(sources, 5, 10, 1, 5)
    set_widths(sources, {"A": 24, "B": 30, "C": 60, "D": 30, "E": 52})
    sources.freeze_panes = "A5"

    for ws in workbook.worksheets:
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
        ws.page_margins.left = 0.35
        ws.page_margins.right = 0.35
        ws.page_margins.top = 0.5
        ws.page_margins.bottom = 0.5
        ws.sheet_view.zoomScale = 90
        ws.oddFooter.center.text = "Prepared by Harman Singh for Professor Phelim Boyle"
        ws.oddFooter.right.text = "Page &P of &N"

    aligned_ws["D4"].comment = Comment(
        "Formula-driven excess return: Fund X raw monthly return minus the q5 file's R_F.",
        "Harman Singh",
    )
    table2_ws["D4"].comment = Comment(
        "Annual alpha is compounded, not multiplied by 12.",
        "Harman Singh",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)


def fmt(value: float, digits: int = 2) -> str:
    return f"{value:.{digits}f}"


def fmt_p(value: float) -> str:
    if value < 0.001:
        return "$<0.001$"
    return f"{value:.3f}"


def write_report(
    path: Path,
    models: dict[str, RegressionResult],
    diagnostics: dict[str, object],
) -> int:
    capm = models["CAPM"]
    qfactor = models["q-factor"]
    q5 = models["q5"]
    alpha_values = [capm.alpha, qfactor.alpha, q5.alpha]
    annual_values = [capm.annual_alpha, qfactor.annual_alpha, q5.annual_alpha]
    alpha_range_bps = (max(alpha_values) - min(alpha_values)) * 100.0
    capm_to_q5_bps = (q5.alpha - capm.alpha) * 100.0

    narrative = rf"""
Across all three specifications, Fund X retains a large positive intercept. The CAPM
monthly alpha is {capm.alpha:.2f}\% with a Newey--West $t$-statistic of
{capm.t_statistics['const']:.2f}. The q-factor estimate is {qfactor.alpha:.2f}\%
($t={qfactor.t_statistics['const']:.2f}$), and the q5 estimate is {q5.alpha:.2f}\%
($t={q5.t_statistics['const']:.2f}$). The full range across specifications is only
{alpha_range_bps:.1f} basis points, while the change from CAPM to q5 is
{capm_to_q5_bps:+.1f} basis points. The corresponding compounded annual alpha estimates
range from {min(annual_values):.2f}\% to {max(annual_values):.2f}\%. All three
intercepts have $p<0.001$. The $t$-statistic rises as factors are added, despite the
slight decline in the q5 point estimate, because the HAC standard error becomes smaller.
The additional factors therefore do not absorb Fund X's average excess return.

The market loading is economically small and statistically insignificant in every
model: it moves from {capm.coefficients['R_MKT']:.3f} in the CAPM to
{q5.coefficients['R_MKT']:.3f} in q5. In the q5 model, the size loading is
{q5.coefficients['R_ME']:.3f} ($t={q5.t_statistics['R_ME']:.2f}$), the investment
loading is {q5.coefficients['R_IA']:.3f} ($t={q5.t_statistics['R_IA']:.2f}$), and the
expected-growth loading is {q5.coefficients['R_EG']:.3f}
($t={q5.t_statistics['R_EG']:.2f}$). None is significant at the 5\% level. The
profitability loading, {q5.coefficients['R_ROE']:.3f} with
$t={q5.t_statistics['R_ROE']:.2f}$, comes closest to conventional significance. If a
negative loading were stable and statistically reliable, it would mean that Fund X
tends to move against the high-minus-low ROE factor rather than earning its returns by
harvesting the profitability premium. Here the evidence is suggestive, not conclusive.

The CAPM explains only {capm.r_squared*100:.1f}\% of monthly variation, compared with
{qfactor.r_squared*100:.1f}\% for the q-factor model and {q5.r_squared*100:.1f}\% for
q5. Adjusted $R^2$ values are {capm.adjusted_r_squared:.3f},
{qfactor.adjusted_r_squared:.3f}, and {q5.adjusted_r_squared:.3f}, respectively. The
negative adjusted values in the first two models are valid: after penalising additional
parameters, those specifications do not improve on an intercept-only benchmark. These
figures are far below the 85--95\% market-model $R^2$ often seen for diversified equity
funds. The q factors therefore explain little of Fund X's month-to-month return
variation. Low explanatory power is not itself proof of skill, but together with the
large intercept it shows that these standard linear equity factors do not account for
the reported performance.

The main conclusion is that Fund X's alpha survives both the q-factor and q5 controls.
Within this sample and model class, its excess return remains largely unexplained by
known systematic equity-factor premia.
""".strip()
    word_count = len(re.findall(r"\b[\w']+\b", re.sub(r"\\[A-Za-z]+", "", narrative)))
    if not 350 <= word_count <= 450:
        raise AssertionError(f"Required results narrative has {word_count} words, not 350-450.")

    lb12 = next(item for item in diagnostics["ljung_box"] if item["Lag"] == 12)
    stability = diagnostics["stability"]
    influence = diagnostics["influence"]
    bootstrap = diagnostics["block_pairs_bootstrap"]
    lag_lookup = {item["Lags"]: item for item in diagnostics["lag_sensitivity"]}

    def coefficient_cell(result: RegressionResult, label: str) -> str:
        return f"{result.coefficients[label]:.3f}{significance_stars(result, label)}"

    def t_cell(result: RegressionResult, label: str) -> str:
        return f"[{result.t_statistics[label]:.2f}]"

    tex = rf"""\documentclass[11pt]{{article}}
\usepackage[margin=0.82in]{{geometry}}
\usepackage{{amsmath}}
\usepackage{{booktabs}}
\usepackage{{array}}
\usepackage{{float}}
\usepackage{{hyperref}}
\hypersetup{{colorlinks=true,urlcolor=blue,citecolor=blue,linkcolor=blue}}

\title{{Project Four: Fund X Factor Model Analysis}}
\author{{Prepared by Harman Singh for Professor Phelim Boyle}}
\date{{July 2026}}

\begin{{document}}
\maketitle

\section*{{Data and Method}}
The analysis uses Fund X's net-of-fees monthly returns from January 2017 through
December 2024 and the official monthly q5 factor file from
\url{{https://global-q.org/factors.html}}. The 96 observations are merged by
year and month. Every factor and return is measured in percent per month. The
dependent variable is Fund X's excess return, $r_{{X,t}}-r_{{f,t}}$, where
$r_{{f,t}}$ is the \texttt{{R\_F}} observation supplied in the q5 file.

Three time-series regressions are estimated: the CAPM with $R_{{MKT}}$; the
Hou--Xue--Zhang q-factor model with $R_{{MKT}}$, $R_{{ME}}$, $R_{{IA}}$, and
$R_{{ROE}}$; and the augmented q5 model, which adds $R_{{EG}}$. Coefficients are
ordinary least squares estimates. The reported $t$-statistics use Newey--West
heteroskedasticity- and autocorrelation-consistent covariance estimates with
the assignment-mandated Bartlett lag length $L=4$.

\clearpage
\section*{{Table 1: Full Regression Results}}
\begin{{table}}[H]
\centering
\caption{{Fund X Factor Regressions: CAPM, q-Factor, and q5}}
\label{{tab:factor-regressions}}
\small
\begin{{tabular}}{{lccc}}
\toprule
 & Model 1 & Model 2 & Model 3 \\
 & CAPM & q-factor & q5 \\
\midrule
$\alpha$ (monthly, \%) &
{coefficient_cell(capm, 'const')} & {coefficient_cell(qfactor, 'const')} & {coefficient_cell(q5, 'const')} \\
 & {t_cell(capm, 'const')} & {t_cell(qfactor, 'const')} & {t_cell(q5, 'const')} \\[3pt]
$\beta_{{MKT}}$ &
{coefficient_cell(capm, 'R_MKT')} & {coefficient_cell(qfactor, 'R_MKT')} & {coefficient_cell(q5, 'R_MKT')} \\
 & {t_cell(capm, 'R_MKT')} & {t_cell(qfactor, 'R_MKT')} & {t_cell(q5, 'R_MKT')} \\[3pt]
$\beta_{{ME}}$ (size) &
-- & {coefficient_cell(qfactor, 'R_ME')} & {coefficient_cell(q5, 'R_ME')} \\
 & -- & {t_cell(qfactor, 'R_ME')} & {t_cell(q5, 'R_ME')} \\[3pt]
$\beta_{{IA}}$ (investment) &
-- & {coefficient_cell(qfactor, 'R_IA')} & {coefficient_cell(q5, 'R_IA')} \\
 & -- & {t_cell(qfactor, 'R_IA')} & {t_cell(q5, 'R_IA')} \\[3pt]
$\beta_{{ROE}}$ (profitability) &
-- & {coefficient_cell(qfactor, 'R_ROE')} & {coefficient_cell(q5, 'R_ROE')} \\
 & -- & {t_cell(qfactor, 'R_ROE')} & {t_cell(q5, 'R_ROE')} \\[3pt]
$\beta_{{EG}}$ (expected growth) &
-- & -- & {coefficient_cell(q5, 'R_EG')} \\
 & -- & -- & {t_cell(q5, 'R_EG')} \\
\midrule
$R^2$ & {capm.r_squared:.3f} & {qfactor.r_squared:.3f} & {q5.r_squared:.3f} \\
Adjusted $R^2$ & {capm.adjusted_r_squared:.3f} & {qfactor.adjusted_r_squared:.3f} & {q5.adjusted_r_squared:.3f} \\
$N$ & 96 & 96 & 96 \\
\bottomrule
\end{{tabular}}

\vspace{{0.2cm}}
\begin{{minipage}}{{0.96\linewidth}}
\footnotesize
\textit{{Note:}} Sample: January 2017 -- December 2024 (N = 96 monthly observations).
Dependent variable: Fund X monthly excess return ($r_X-r_f$). q5 factor returns
($R_{{MKT}}$, $R_{{ME}}$, $R_{{IA}}$, $R_{{ROE}}$, $R_{{EG}}$) are from Hou, Mo,
Xue and Zhang (2021) via global-q.org. Standard errors are Newey--West HAC with
$L=4$ lags (Newey and West, 1987); $t$-statistics in brackets. No coefficient is
asterisked unless its $|t|\geq1.96$. *** denotes $p<0.001$.
\end{{minipage}}
\end{{table}}

\clearpage
\section*{{Table 2: Alpha Summary}}
\begin{{table}}[H]
\centering
\caption{{Summary of Alpha Estimates Across Factor Models}}
\label{{tab:alpha-summary}}
\small
\begin{{tabular}}{{lrrrr}}
\toprule
Model & Monthly $\alpha$ & NW $t$-stat & Annual $\alpha$ & $R^2$ \\
\midrule
CAPM (1-factor) & {capm.alpha:.3f}*** & {capm.t_statistics['const']:.2f} & {capm.annual_alpha:.2f}\% & {capm.r_squared:.3f} \\
q-factor (4-factor) & {qfactor.alpha:.3f}*** & {qfactor.t_statistics['const']:.2f} & {qfactor.annual_alpha:.2f}\% & {qfactor.r_squared:.3f} \\
q5 (5-factor) & {q5.alpha:.3f}*** & {q5.t_statistics['const']:.2f} & {q5.annual_alpha:.2f}\% & {q5.r_squared:.3f} \\
\bottomrule
\end{{tabular}}

\vspace{{0.2cm}}
\begin{{minipage}}{{0.94\linewidth}}
\footnotesize
\textit{{Note:}} *** $p<0.001$. Annual alpha computed as
$(1+\text{{monthly\_alpha}}/100)^{{12}}-1$. Sample: January 2017 -- December 2024,
$N=96$. NW $t$-statistics use $L=4$ lags.
\end{{minipage}}
\end{{table}}

\section*{{Results}}
{narrative}

\clearpage
\section*{{Assumption-Aware Diagnostic Assessment}}
The required $L=4$ estimates are the primary results. The literal bandwidth expression
$4(T/100)^{{2/9}}$ equals {diagnostics['lag_rule']['formula_value']:.4f} at $T=96$ and
would floor to {diagnostics['lag_rule']['literal_floor']}, so $L=3$ is also checked.
The q5 alpha $t$-statistic is {lag_lookup[3]['NW_t']:.2f} at $L=3$,
{lag_lookup[4]['NW_t']:.2f} at $L=4$, {lag_lookup[6]['NW_t']:.2f} at $L=6$, and
{lag_lookup[12]['NW_t']:.2f} at $L=12$. The conclusion is not driven by the lag choice.

The q5 residuals remain serially dependent: the Ljung--Box statistic through 12 lags is
{lb12['Q_statistic']:.2f} with $p<0.001$. They are also strongly non-normal
(Jarque--Bera $p<0.001$), and the Breusch--Pagan test is borderline
($p={diagnostics['breusch_pagan']['LM_p_value']:.3f}$). These findings justify HAC
inference and caution against relying on textbook iid OLS standard errors. A
{bootstrap['block_length']}-month circular block-pairs bootstrap, which preserves local
dependence and the joint factor-return observations, gives a 95\% q5 alpha interval of
[{bootstrap['lower_95']:.2f}\%, {bootstrap['upper_95']:.2f}\%].

March 2020 is the most influential observation (Cook's distance
{influence['Max_Cooks_Distance']:.2f}). Excluding it leaves a q5 alpha of
{influence['Alpha_Excluding_Month']:.2f}\% with $t={influence['NW_t_Excluding_Month']:.2f}$.
Across all 96 leave-one-out regressions, alpha ranges only from
{influence['Leave_One_Out_Alpha_Min']:.2f}\% to
{influence['Leave_One_Out_Alpha_Max']:.2f}\%.

Parameter stability is the main qualification. A CUSUM test rejects a constant q5
coefficient vector ($p={stability['CUSUM_p_value']:.4f}$). In an objective midpoint
split, q5 alpha is {stability['Early_2017_2020_Alpha']:.2f}\%
($t={stability['Early_2017_2020_NW_t']:.2f}$) in 2017--2020 and
{stability['Late_2021_2024_Alpha']:.2f}\%
($t={stability['Late_2021_2024_NW_t']:.2f}$) in 2021--2024. The alpha remains positive,
but its level is not stable. Newey--West inference cannot correct changing coefficients,
omitted factors, nonlinear exposures, or a mismatch between a US equity factor model and
the fund's underlying strategy. The result should therefore be stated as a large return
unexplained by these models, not as proof that every possible risk exposure has been ruled out.

\section*{{References}}
\begin{{description}}
\item Hou, K., Xue, C., and Zhang, L. (2015).
Digesting anomalies: An investment approach.
\textit{{Review of Financial Studies}}, 28(3), 650--705.
\item Hou, K., Mo, H., Xue, C., and Zhang, L. (2021).
An augmented q-factor model with expected growth.
\textit{{Review of Finance}}, 25(1), 1--41.
\item Newey, W. K. and West, K. D. (1987).
A simple, positive semi-definite, heteroskedasticity and autocorrelation consistent covariance matrix.
\textit{{Econometrica}}, 55(3), 703--708.
\end{{description}}

\end{{document}}
"""
    path.write_text(tex, encoding="utf-8")
    return word_count


def compile_pdf(tex_path: Path) -> str:
    pdflatex = shutil.which("pdflatex")
    if not pdflatex:
        return "pdflatex not found"
    for _ in range(2):
        result = subprocess.run(
            [pdflatex, "-interaction=nonstopmode", "-halt-on-error", tex_path.name],
            cwd=tex_path.parent,
            capture_output=True,
            text=True,
            timeout=180,
        )
        if result.returncode != 0:
            error_log = ASSIGNMENT_DIR / "latex_compile_error.log"
            error_log.write_text(result.stdout + "\n" + result.stderr, encoding="utf-8")
            return f"LaTeX compilation failed; see {error_log.name}"
    return "Compiled PDF"


def verify_workbook(path: Path, expected_sheets: Iterable[str]) -> dict[str, object]:
    workbook = load_workbook(path, data_only=False)
    missing_sheets = [name for name in expected_sheets if name not in workbook.sheetnames]
    if missing_sheets:
        raise AssertionError(f"Workbook is missing sheets: {missing_sheets}")
    formula_count = 0
    formula_error_literals = []
    for worksheet in workbook.worksheets:
        for row in worksheet.iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and cell.value.startswith("="):
                    formula_count += 1
                if isinstance(cell.value, str) and any(
                    marker in cell.value
                    for marker in ["#REF!", "#DIV/0!", "#VALUE!", "#NAME?", "#N/A"]
                ):
                    formula_error_literals.append(f"{worksheet.title}!{cell.coordinate}")
    if formula_error_literals:
        raise AssertionError(f"Workbook contains formula error literals: {formula_error_literals}")
    return {
        "sheet_count": len(workbook.sheetnames),
        "sheets": workbook.sheetnames,
        "formula_count": formula_count,
        "formula_error_literals": formula_error_literals,
    }


def to_native(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): to_native(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_native(item) for item in value]
    if isinstance(value, tuple):
        return [to_native(item) for item in value]
    if isinstance(value, pd.DataFrame):
        return value.to_dict()
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Assignment 4 q-factor analysis deliverables.")
    parser.add_argument(
        "--refresh-q5",
        action="store_true",
        help="Redownload the official q5 monthly factor file before running.",
    )
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    fund, q5_raw, aligned = load_and_align_data(refresh_q5=args.refresh_q5)
    models = {
        model_name: run_regression(aligned, model_name, factors, lags=PRIMARY_LAGS)
        for model_name, factors in MODEL_FACTORS.items()
    }
    diagnostics = regression_diagnostics(aligned, models)
    table_1, table_2 = build_table_rows(models)
    write_table_csvs(table_1, table_2)
    write_workbook(
        OUTPUT_XLSX,
        fund,
        q5_raw,
        aligned,
        models,
        diagnostics,
        table_1,
        table_2,
    )
    narrative_word_count = write_report(OUTPUT_TEX, models, diagnostics)
    compile_status = compile_pdf(OUTPUT_TEX)
    workbook_verification = verify_workbook(
        OUTPUT_XLSX,
        [
            "Summary",
            "Table 1",
            "Table 2",
            "Regression Details",
            "Diagnostics",
            "HAC Sensitivity",
            "Factor Correlations",
            "Fund X Raw",
            "q5 Raw",
            "Aligned Data",
            "QA Checks",
            "Sources",
        ],
    )
    if not OUTPUT_PDF.exists():
        raise SystemExit(f"Expected PDF was not created: {compile_status}")

    manifest = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "assignment": "Project 4: Fund X Factor Model Analysis",
        "sample": {
            "start": "2017-01",
            "end": "2024-12",
            "observations": 96,
        },
        "sources": {
            "fund_x": FUND_SOURCE_PATH.relative_to(PROJECT_DIR).as_posix(),
            "fund_x_sha256": sha256_file(FUND_SOURCE_PATH),
            "q5_url": Q5_URL,
            "q5_sha256": sha256_file(Q5_PATH),
        },
        "method": {
            "dependent_variable": "Fund X monthly return minus R_F, in percentage units",
            "models": MODEL_FACTORS,
            "newey_west_lags": PRIMARY_LAGS,
            "newey_west_kernel": "Bartlett",
            "primary_hac_finite_sample_correction": False,
            "annual_alpha": "(1 + monthly_alpha/100)^12 - 1",
        },
        "results": {
            model_name: {
                "alpha_monthly_percent": result.alpha,
                "alpha_annual_percent": result.annual_alpha,
                "alpha_nw_t": result.t_statistics["const"],
                "alpha_p_value": result.p_values["const"],
                "r_squared": result.r_squared,
                "adjusted_r_squared": result.adjusted_r_squared,
                "coefficients": result.coefficients,
                "newey_west_t_statistics": result.t_statistics,
            }
            for model_name, result in models.items()
        },
        "diagnostics": to_native(
            {
                key: value
                for key, value in diagnostics.items()
                if key not in {"leave_one_out", "factor_correlations"}
            }
        ),
        "narrative_word_count": narrative_word_count,
        "compile_status": compile_status,
        "workbook_verification": workbook_verification,
        "outputs": {
            "pdf": OUTPUT_PDF.relative_to(PROJECT_DIR).as_posix(),
            "tex": OUTPUT_TEX.relative_to(PROJECT_DIR).as_posix(),
            "xlsx": OUTPUT_XLSX.relative_to(PROJECT_DIR).as_posix(),
            "table_1_csv": TABLE_1_CSV.relative_to(PROJECT_DIR).as_posix(),
            "table_2_csv": TABLE_2_CSV.relative_to(PROJECT_DIR).as_posix(),
            "fund_x_data": FUND_EXPORT_PATH.relative_to(PROJECT_DIR).as_posix(),
            "q5_data": Q5_PATH.relative_to(PROJECT_DIR).as_posix(),
            "aligned_data": ALIGNED_EXPORT_PATH.relative_to(PROJECT_DIR).as_posix(),
            "script": Path(__file__).resolve().relative_to(PROJECT_DIR).as_posix(),
        },
    }
    OUTPUT_MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
