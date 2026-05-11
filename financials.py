import os
import json
import time
from typing import Any, Dict, List, Optional, Tuple

import requests


SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"


# Preferred XBRL concepts by dashboard metric.
# Order matters: first concept with clean annual FY records wins.
FINANCIAL_CONCEPTS = {
    "Revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueNet",
        "Revenues",
    ],
    "Operating Income": [
        "OperatingIncomeLoss",
    ],
    "Net Income": [
        "NetIncomeLoss",
        "ProfitLoss",
    ],
    "Basic EPS": [
        "EarningsPerShareBasic",
    ],
    "Diluted EPS": [
        "EarningsPerShareDiluted",
    ],
    "Dividends Paid": [
        "PaymentsOfDividendsCommonStock",
        "PaymentsOfOrdinaryDividends",
        "PaymentsOfDividends",
    ],
    "Operating Cash Flow": [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ],
    "Capital Expenditure": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
    ],
    "Total Assets": [
        "Assets",
    ],
    "Total Liabilities": [
        "Liabilities",
    ],
    "Shareholders Equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
}


BALANCE_SHEET_METRICS = {
    "Total Assets",
    "Total Liabilities",
    "Shareholders Equity",
}

EPS_METRICS = {
    "Basic EPS",
    "Diluted EPS",
}

CORE_DASHBOARD_METRICS = [
    "Revenue",
    "Operating Income",
    "Net Income",
]


def sec_headers() -> Dict[str, str]:
    return {
        "User-Agent": os.getenv(
            "SEC_USER_AGENT",
            "Academic SEC MCP Demo your.email@example.com",
        ),
        "Accept-Encoding": "gzip, deflate",
        "Accept": "application/json",
    }


def safe_get_json(url: str) -> Dict[str, Any]:
    # SEC fair access: be polite and avoid burst requests.
    time.sleep(0.15)

    response = requests.get(url, headers=sec_headers(), timeout=30)

    if response.status_code != 200:
        raise RuntimeError(
            f"SEC request failed. Status={response.status_code}. "
            f"Preview={response.text[:300]}"
        )

    try:
        return response.json()
    except Exception:
        raise RuntimeError(
            f"SEC response was not JSON. Preview={response.text[:300]}"
        )


def get_cik(ticker: str) -> str:
    ticker = ticker.upper().strip()
    data = safe_get_json(SEC_TICKERS_URL)

    for company in data.values():
        if company.get("ticker", "").upper() == ticker:
            return str(company["cik_str"]).zfill(10)

    raise ValueError(f"Ticker not found: {ticker}")


def get_company_facts(ticker: str) -> Dict[str, Any]:
    cik = get_cik(ticker)
    url = SEC_COMPANY_FACTS_URL.format(cik=cik)
    return safe_get_json(url)


def get_us_gaap_facts(company_facts: Dict[str, Any]) -> Dict[str, Any]:
    return company_facts.get("facts", {}).get("us-gaap", {})


def preferred_units(metric_name: str) -> List[str]:
    if metric_name in EPS_METRICS:
        return ["USD/shares"]
    return ["USD"]


def normalize_value(value: Optional[float], unit: Optional[str]) -> Dict[str, Any]:
    if value is None:
        return {
            "raw_value": None,
            "display_value": None,
            "display": "N/A",
            "scale": "not_available",
        }

    if unit == "USD/shares":
        return {
            "raw_value": value,
            "display_value": round(value, 2),
            "display": f"${value:,.2f}",
            "scale": "per share",
        }

    abs_value = abs(value)

    if abs_value >= 1_000_000_000:
        return {
            "raw_value": value,
            "display_value": round(value / 1_000_000_000, 2),
            "display": f"${value / 1_000_000_000:,.2f}B",
            "scale": "billions",
        }

    if abs_value >= 1_000_000:
        return {
            "raw_value": value,
            "display_value": round(value / 1_000_000, 2),
            "display": f"${value / 1_000_000:,.2f}M",
            "scale": "millions",
        }

    return {
        "raw_value": value,
        "display_value": value,
        "display": f"${value:,.0f}",
        "scale": "raw",
    }


def format_percent(value: Optional[float]) -> str:
    if value is None:
        return "N/A"

    sign = "+" if value > 0 else ""
    return f"{sign}{value:.2f}%"


def calculate_yoy(current: Optional[float], prior: Optional[float]) -> Optional[float]:
    if current is None or prior is None or prior == 0:
        return None

    return round(((current - prior) / prior) * 100, 2)


def is_valid_annual_record(record: Dict[str, Any], metric_name: str) -> bool:
    if record.get("form") != "10-K":
        return False

    if record.get("fp") != "FY":
        return False

    if record.get("fy") is None:
        return False

    if record.get("val") is None:
        return False

    # Income statement, EPS, cash flow, capex, and dividends are duration concepts.
    # Balance sheet concepts are instant concepts and may not have start date.
    if metric_name not in BALANCE_SHEET_METRICS:
        if not record.get("start") or not record.get("end"):
            return False

    return True


def get_records_for_concept(
    company_facts: Dict[str, Any],
    concept: str,
    metric_name: str,
) -> List[Dict[str, Any]]:
    us_gaap = get_us_gaap_facts(company_facts)

    if concept not in us_gaap:
        return []

    units = us_gaap[concept].get("units", {})
    selected_unit = None

    for unit in preferred_units(metric_name):
        if unit in units:
            selected_unit = unit
            break

    if selected_unit is None:
        return []

    records = []

    for record in units[selected_unit]:
        if not is_valid_annual_record(record, metric_name):
            continue

        records.append(
            {
                "concept": concept,
                "unit": selected_unit,
                "fy": int(record.get("end", "")[:4]),
                "reported_fy": int(record.get("fy")) if record.get("fy") is not None else None,
                "fp": record.get("fp"),
                "form": record.get("form"),
                "filed": record.get("filed"),
                "start": record.get("start"),
                "end": record.get("end"),
                "accn": record.get("accn"),
                "value": record.get("val"),
            }
        )

    return records


def dedupe_records_by_fiscal_year(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Keep exactly one record per fiscal year.
    If multiple 10-K FY facts exist, keep the latest filed record.
    """
    by_year: Dict[int, Dict[str, Any]] = {}

    for record in records:
        fy = record["fy"]

        if fy not in by_year:
            by_year[fy] = record
            continue

        existing = by_year[fy]
        if str(record.get("filed", "")) > str(existing.get("filed", "")):
            by_year[fy] = record

    return sorted(by_year.values(), key=lambda r: r["fy"], reverse=True)


def find_best_concept_records(
    company_facts: Dict[str, Any],
    metric_name: str,
    concepts: List[str],
) -> Dict[str, Any]:

    best_result = None
    best_latest_year = -1

    for concept in concepts:
        records = get_records_for_concept(
            company_facts,
            concept,
            metric_name
        )

        records = dedupe_records_by_fiscal_year(records)

        if not records:
            continue

        latest_year = max(r["fy"] for r in records)

        if latest_year > best_latest_year:
            best_latest_year = latest_year

            best_result = {
                "metric": metric_name,
                "concept_used": concept,
                "records": records,
                "status": "found",
            }

    if best_result:
        return best_result

    return {
        "metric": metric_name,
        "concept_used": None,
        "records": [],
        "status": "not_found",
    }


def determine_dashboard_year_pair(company_facts):
    revenue_data = find_best_concept_records(
        company_facts,
        "Revenue",
        FINANCIAL_CONCEPTS["Revenue"],
    )

    revenue_years = [record["fy"] for record in revenue_data.get("records", [])]

    if not revenue_years:
        return None, None

    current_fy = max(revenue_years)
    prior_fy = current_fy - 1

    return current_fy, prior_fy

"""

def determine_dashboard_year_pair(company_facts: Dict[str, Any]) -> Tuple[Optional[int], Optional[int]]:

    candidate_year_sets = []

    for metric_name in CORE_DASHBOARD_METRICS:
        concepts = FINANCIAL_CONCEPTS[metric_name]
        concept_data = find_best_concept_records(company_facts, metric_name, concepts)
        years = {record["fy"] for record in concept_data.get("records", [])}

        if years:
            candidate_year_sets.append(years)

    if not candidate_year_sets:
        return None, None

    common_years = set.intersection(*candidate_year_sets)

    if not common_years:
        revenue_data = find_best_concept_records(
            company_facts,
            "Revenue",
            FINANCIAL_CONCEPTS["Revenue"],
        )
        revenue_years = [r["fy"] for r in revenue_data.get("records", [])]
        if not revenue_years:
            return None, None

        current_fy = max(revenue_years)
        prior_fy = current_fy - 1
        return current_fy, prior_fy

    current_fy = max(common_years)
    prior_fy = current_fy - 1

    return current_fy, prior_fy

"""

def get_record_for_year(records: List[Dict[str, Any]], fy: Optional[int]) -> Optional[Dict[str, Any]]:
    if fy is None:
        return None

    return next((record for record in records if record.get("fy") == fy), None)


def format_metric_result(
    metric_name: str,
    concept_data: Dict[str, Any],
    dashboard_current_fy: Optional[int],
    dashboard_prior_fy: Optional[int],
) -> Dict[str, Any]:
    records = concept_data.get("records", [])

    current = get_record_for_year(records, dashboard_current_fy)
    prior = get_record_for_year(records, dashboard_prior_fy)

    if current is None:
        return {
            "metric": metric_name,
            "status": "not_available",
            "concept_used": concept_data.get("concept_used"),
            "unit": None,
            "dashboard_current_year": dashboard_current_fy,
            "dashboard_prior_year": dashboard_prior_fy,
            "current_year": dashboard_current_fy,
            "prior_year": dashboard_prior_fy,
            "current_period_end": None,
            "prior_period_end": None,
            "current_value": None,
            "prior_value": None,
            "current_display": "N/A",
            "prior_display": "N/A",
            "scale": "not_available",
            "yoy_change_percent": None,
            "yoy_display": "N/A",
            "warnings": [
                f"No clean annual 10-K FY record found for dashboard current year {dashboard_current_fy}."
            ],
            "quality_checks": {
                "uses_dashboard_year_pair": True,
                "same_current_year_as_dashboard": False,
                "same_prior_year_as_dashboard": False,
                "same_unit": False,
                "yoy_calculation_allowed": False,
            },
        }

    current_value = current.get("value")
    prior_value = prior.get("value") if prior else None

    current_fmt = normalize_value(current_value, current.get("unit"))
    prior_fmt = normalize_value(prior_value, prior.get("unit")) if prior else normalize_value(None, current.get("unit"))

    same_unit = prior is not None and current.get("unit") == prior.get("unit")
    prior_is_expected_year = prior is not None and prior.get("fy") == dashboard_prior_fy

    can_calculate_yoy = (
        dashboard_current_fy is not None
        and dashboard_prior_fy is not None
        and current.get("fy") == dashboard_current_fy
        and prior_is_expected_year
        and same_unit
        and prior_value is not None
        and prior_value != 0
    )

    yoy_value = calculate_yoy(current_value, prior_value) if can_calculate_yoy else None

    warnings = []

    if prior is None:
        warnings.append(
            f"No clean annual 10-K FY record found for dashboard prior year {dashboard_prior_fy}."
        )

    if prior is not None and not same_unit:
        warnings.append(
            f"YoY not calculated because units differ: current {current.get('unit')}, prior {prior.get('unit')}."
        )

    if prior_value == 0:
        warnings.append("YoY not calculated because prior-year value is zero.")

    return {
        "metric": metric_name,
        "status": "ok" if can_calculate_yoy else "partial",
        "concept_used": concept_data.get("concept_used"),
        "unit": current.get("unit"),
        "dashboard_current_year": dashboard_current_fy,
        "dashboard_prior_year": dashboard_prior_fy,
        "current_year": current.get("fy"),
        "prior_year": prior.get("fy") if prior else dashboard_prior_fy,
        "current_value": current_value,
        "prior_value": prior_value,
        "current_display": current_fmt["display"],
        "prior_display": prior_fmt["display"],
        "scale": current_fmt["scale"],
        "yoy_change_percent": yoy_value,
        "yoy_display": format_percent(yoy_value),
        "current_filed": current.get("filed"),
        "prior_filed": prior.get("filed") if prior else None,
        "current_period_end": current.get("end"),
        "prior_period_end": prior.get("end") if prior else None,
        "current_accession": current.get("accn"),
        "prior_accession": prior.get("accn") if prior else None,
        "warnings": warnings,
        "quality_checks": {
            "uses_dashboard_year_pair": True,
            "same_current_year_as_dashboard": current.get("fy") == dashboard_current_fy,
            "same_prior_year_as_dashboard": prior_is_expected_year,
            "same_unit": same_unit,
            "yoy_calculation_allowed": can_calculate_yoy,
        },
    }


def get_multi_year_series(
    company_facts: Dict[str, Any],
    concept: Optional[str],
    metric_name: str,
    max_years: int = 5,
) -> List[Dict[str, Any]]:
    if not concept:
        return []

    records = get_records_for_concept(company_facts, concept, metric_name)
    records = dedupe_records_by_fiscal_year(records)

    series = []

    for record in records[:max_years]:
        formatted = normalize_value(record.get("value"), record.get("unit"))
        series.append(
            {
                "year": record["fy"],
                "value": record["value"],
                "display": formatted["display"],
                "unit": record.get("unit"),
            }
        )

    return sorted(series, key=lambda x: x["year"])


def add_trend_data(
    company_facts: Dict[str, Any],
    metric_name: str,
    concept_data: Dict[str, Any],
    result: Dict[str, Any],
) -> Dict[str, Any]:
    concept = concept_data.get("concept_used")

    if not concept:
        result["trend"] = []
        return result

    result["trend"] = get_multi_year_series(
        company_facts=company_facts,
        concept=concept,
        metric_name=metric_name,
        max_years=5,
    )

    return result


def calculate_dividend_payout_ratio(
    analytics: Dict[str, Any],
    dashboard_current_fy: Optional[int],
) -> Dict[str, Any]:
    net_income = analytics.get("Net Income", {})
    dividends = analytics.get("Dividends Paid", {})

    net_income_value = net_income.get("current_value")
    dividends_value = dividends.get("current_value")

    same_current_year = (
        net_income.get("current_year") == dashboard_current_fy
        and dividends.get("current_year") == dashboard_current_fy
    )

    if (
        net_income_value is not None
        and dividends_value is not None
        and same_current_year
        and net_income_value != 0
    ):
        payout_ratio = round((abs(dividends_value) / net_income_value) * 100, 2)

        return {
            "metric": "Dividend Payout Ratio",
            "formula": "abs(Dividends Paid) / Net Income * 100",
            "dashboard_current_year": dashboard_current_fy,
            "current_year": dashboard_current_fy,
            "value_percent": payout_ratio,
            "value_display": f"{payout_ratio:.2f}%",
            "numerator": dividends.get("current_display"),
            "denominator": net_income.get("current_display"),
            "status": "ok",
            "warnings": [],
            "quality_checks": {
                "uses_dashboard_year_pair": True,
                "same_current_fiscal_year": same_current_year,
                "net_income_available": True,
                "dividends_available": True,
                "calculation_allowed": True,
            },
        }

    return {
        "metric": "Dividend Payout Ratio",
        "status": "not_available",
        "value_percent": None,
        "value_display": "N/A",
        "dashboard_current_year": dashboard_current_fy,
        "warning": (
            "Dividend payout ratio not calculated because Net Income and Dividends Paid "
            "are not available for the same dashboard fiscal year."
        ),
        "quality_checks": {
            "uses_dashboard_year_pair": True,
            "same_current_fiscal_year": same_current_year,
            "net_income_available": net_income_value is not None,
            "dividends_available": dividends_value is not None,
            "calculation_allowed": False,
        },
    }


def calculate_financial_analytics(ticker: str) -> Dict[str, Any]:
    company_facts = get_company_facts(ticker)

    dashboard_current_fy, dashboard_prior_fy = determine_dashboard_year_pair(company_facts)

    analytics: Dict[str, Any] = {}

    for metric_name, concepts in FINANCIAL_CONCEPTS.items():
        concept_data = find_best_concept_records(
            company_facts=company_facts,
            metric_name=metric_name,
            concepts=concepts,
        )

        result = format_metric_result(
            metric_name=metric_name,
            concept_data=concept_data,
            dashboard_current_fy=dashboard_current_fy,
            dashboard_prior_fy=dashboard_prior_fy,
        )

        result = add_trend_data(
            company_facts=company_facts,
            metric_name=metric_name,
            concept_data=concept_data,
            result=result,
        )

        analytics[metric_name] = result

    analytics["Dividend Payout Ratio"] = calculate_dividend_payout_ratio(
        analytics=analytics,
        dashboard_current_fy=dashboard_current_fy,
    )

    print("DEBUG DASHBOARD FY:", dashboard_current_fy, dashboard_prior_fy)
    print("DEBUG REVENUE YEARS:", [
        r["fy"] for r in find_best_concept_records(
            company_facts,
            "Revenue",
            FINANCIAL_CONCEPTS["Revenue"]
        ).get("records", [])
    ])

    return {
        "ticker": ticker.upper(),
        "source": "SEC Company Facts XBRL API",
        "basis": (
            "Dashboard uses one common annual 10-K fiscal-year pair across all KPIs. "
            "Metrics missing that exact year pair are shown as N/A instead of borrowing another year."
        ),
        "dashboard_current_fy": dashboard_current_fy,
        "dashboard_prior_fy": dashboard_prior_fy,
        "financial_analytics": analytics,
    }


if __name__ == "__main__":
    result = calculate_financial_analytics("WMT")
    print(json.dumps(result, indent=2))