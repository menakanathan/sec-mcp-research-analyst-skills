import os
import json
import time
import requests
from typing import Any, Dict, List, Optional


SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"


FINANCIAL_CONCEPTS = {
    "Revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueNet",
        "Revenues"
    ],
    "Operating Income": ["OperatingIncomeLoss"],
    "Net Income": ["NetIncomeLoss", "ProfitLoss"],
    "Basic EPS": ["EarningsPerShareBasic"],
    "Diluted EPS": ["EarningsPerShareDiluted"],
    "Dividends Paid": ["PaymentsOfDividends", "PaymentsOfDividendsCommonStock","PaymentsOfOrdinaryDividends"],
    "Operating Cash Flow": ["NetCashProvidedByUsedInOperatingActivities"],
    "Capital Expenditure": ["PaymentsToAcquirePropertyPlantAndEquipment"],
    "Total Assets": ["Assets"],
    "Total Liabilities": ["Liabilities"],
    "Shareholders Equity": ["StockholdersEquity"],
}


def sec_headers() -> Dict[str, str]:
    return {
        "User-Agent": os.getenv(
            "SEC_USER_AGENT",
            "Academic SEC MCP Demo your.email@example.com"
        ),
        "Accept-Encoding": "gzip, deflate",
        "Accept": "application/json",
    }


def safe_get_json(url: str) -> Dict[str, Any]:
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
        if company["ticker"].upper() == ticker:
            return str(company["cik_str"]).zfill(10)

    raise ValueError(f"Ticker not found: {ticker}")


def get_company_facts(ticker: str) -> Dict[str, Any]:
    cik = get_cik(ticker)
    url = SEC_COMPANY_FACTS_URL.format(cik=cik)
    return safe_get_json(url)


def preferred_unit_for_metric(metric_name: str) -> List[str]:
    if "EPS" in metric_name:
        return ["USD/shares"]
    if metric_name in ["Total Assets", "Total Liabilities", "Shareholders Equity"]:
        return ["USD"]
    return ["USD"]


def normalize_value(value: float, unit: str) -> Dict[str, Any]:
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


def get_us_gaap_facts(company_facts: Dict[str, Any]) -> Dict[str, Any]:
    return company_facts.get("facts", {}).get("us-gaap", {})


def get_records_for_concept(
    company_facts: Dict[str, Any],
    concept: str,
    metric_name: str
) -> List[Dict[str, Any]]:
    us_gaap = get_us_gaap_facts(company_facts)

    if concept not in us_gaap:
        return []

    units = us_gaap[concept].get("units", {})
    preferred_units = preferred_unit_for_metric(metric_name)

    selected_unit = None
    for unit in preferred_units:
        if unit in units:
            selected_unit = unit
            break

    if selected_unit is None:
        return []

    records = []

    for record in units[selected_unit]:
        if record.get("form") != "10-K":
            continue

        if record.get("fp") != "FY":
            continue

        if record.get("val") is None:
            continue

        if record.get("fy") is None:
            continue

        start = record.get("start")
        end = record.get("end")

        # For income statement and cash flow metrics, prefer duration facts with start and end.
        # For balance sheet metrics, instant facts may not have start.
        if metric_name not in ["Total Assets", "Total Liabilities", "Shareholders Equity"]:
            if not start or not end:
                continue

        records.append({
            "concept": concept,
            "unit": selected_unit,
            "fy": record.get("fy"),
            "fp": record.get("fp"),
            "form": record.get("form"),
            "filed": record.get("filed"),
            "start": start,
            "end": end,
            "accn": record.get("accn"),
            "value": record.get("val"),
        })

    return records


def dedupe_records_by_fiscal_year(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Keeps one clean record per fiscal year.
    If multiple records exist for the same FY, keep the latest filed record.
    """
    by_year = {}

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
    concepts: List[str]
) -> Dict[str, Any]:
    for concept in concepts:
        records = get_records_for_concept(company_facts, concept, metric_name)
        records = dedupe_records_by_fiscal_year(records)

        if records:
            return {
                "metric": metric_name,
                "concept_used": concept,
                "records": records,
                "status": "found",
            }

    return {
        "metric": metric_name,
        "concept_used": None,
        "records": [],
        "status": "not_found",
    }

def get_multi_year_series(company_facts, concept, metric_name, max_years=5):
    records = get_records_for_concept(company_facts, concept, metric_name)
    records = dedupe_records_by_fiscal_year(records)

    series = []

    for r in records[:max_years]:
        series.append({
            "year": r["fy"],
            "value": r["value"],
            "display": normalize_value(r["value"], r["unit"])["display"]
        })

    # sort ascending for chart
    series = sorted(series, key=lambda x: x["year"])

    return series


def calculate_yoy(current: Optional[float], prior: Optional[float]) -> Optional[float]:
    if current is None or prior is None or prior == 0:
        return None

    return round(((current - prior) / prior) * 100, 2)


def format_metric_result(metric_name: str, concept_data: Dict[str, Any]) -> Dict[str, Any]:
    records = concept_data["records"]

    if not records:
        return {
            "metric": metric_name,
            "status": "not_found",
            "concept_used": None,
            "warning": "No clean annual 10-K FY record found.",
        }

    current = records[0]
    prior = records[1] if len(records) > 1 else None

    current_value = current["value"]
    prior_value = prior["value"]if prior else None
    if metric_name == "Revenue" and current_value < 100_000_000_000:
        return {
            "metric": metric_name,
            "status": "warning",
            "concept_used": concept_data["concept_used"],
            "current_value": current_value,
            "prior_value": prior_value,
            "warning": "Revenue value looks too small for this company. Check alternate XBRL revenue concepts."
        }
    current_fmt = normalize_value(current_value, current["unit"])
    prior_fmt = normalize_value(prior_value, prior["unit"]) if prior else None

    return {
        "metric": metric_name,
        "status": "ok",
        "current_year": current["fy"],
        "prior_year": prior["fy"] if prior else None,

        # raw values (for calculations)
        "current_value": current_value,
        "prior_value": prior_value,
        "yoy_change_percent": calculate_yoy(current_value, prior_value),

        # formatted values (for UI)
        "current_display": format_currency(current_value),
        "prior_display": format_currency(prior_value),
        "yoy_display": format_percent(calculate_yoy(current_value, prior_value)),
    }


def calculate_financial_analytics(ticker: str) -> dict:
    company_facts = get_company_facts(ticker)

    analytics = {}

    for metric_name, concepts in FINANCIAL_CONCEPTS.items():
        concept_data = find_best_concept_records(
            company_facts,
            metric_name,
            concepts
        )

        result = format_metric_result(metric_name, concept_data)

        if concept_data["records"]:
            result["trend"] = get_multi_year_series(
                company_facts,
                concept_data["concept_used"],
                metric_name
            )

        analytics[metric_name] = result

    net_income = analytics.get("Net Income", {})
    dividends = analytics.get("Dividends Paid", {})

    net_income_value = net_income.get("current_value")
    dividends_value = dividends.get("current_value")

    if net_income_value is not None and dividends_value is not None:
        analytics["Dividend Payout Ratio"] = {
            "metric": "Dividend Payout Ratio",
            "formula": "abs(Dividends Paid) / Net Income * 100",
            "current_year": net_income.get("current_year"),
            "value_percent": round((abs(dividends_value) / net_income_value) * 100, 2),
            "numerator": dividends.get("current_display"),
            "denominator": net_income.get("current_display"),
            "status": "ok",
        }
    else:
        analytics["Dividend Payout Ratio"] = {
            "metric": "Dividend Payout Ratio",
            "status": "not_available",
            "warning": "Could not compute payout ratio because either Net Income or Dividends Paid was unavailable.",
            "net_income_available": net_income_value is not None,
            "dividends_available": dividends_value is not None,
        }

    return {
        "ticker": ticker.upper(),
        "source": "SEC Company Facts XBRL API",
        "note": "Uses annual 10-K FY records only, deduplicated by fiscal year.",
        "financial_analytics": analytics,
    }

def format_currency(value):
    if value is None:
        return "N/A"

    if abs(value) >= 1_000_000_000:
        return f"${value / 1_000_000_000:,.2f}B"

    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:,.2f}M"

    return f"${value:,.0f}"

def format_percent(value):
    if value is None:
        return "N/A"

    sign = "+" if value > 0 else ""
    return f"{sign}{value:.2f}%"

if __name__ == "__main__":
    result = calculate_financial_analytics("WMT")
    print(json.dumps(result, indent=2))