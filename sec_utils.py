import os
import re
import requests
from bs4 import BeautifulSoup


def sec_headers():
    return {
        "User-Agent": os.getenv(
            "SEC_USER_AGENT",
            "Academic SEC MCP Demo your.email@example.com"
        ),
        "Accept-Encoding": "gzip, deflate",
        "Accept": "application/json,text/html"
    }


def safe_get_json(url):
    response = requests.get(url, headers=sec_headers(), timeout=30)

    if response.status_code != 200:
        raise Exception(
            f"SEC request failed. Status: {response.status_code}. "
            f"Response preview: {response.text[:300]}"
        )

    try:
        return response.json()
    except Exception:
        raise Exception(
            f"SEC did not return JSON. Response preview: {response.text[:500]}"
        )


def safe_get_text(url):
    response = requests.get(url, headers=sec_headers(), timeout=60)

    if response.status_code != 200:
        raise Exception(
            f"SEC filing download failed. Status: {response.status_code}. "
            f"Response preview: {response.text[:300]}"
        )

    return response.text


def get_cik(ticker):
    ticker = ticker.upper().strip()

    data = safe_get_json("https://www.sec.gov/files/company_tickers.json")

    for company in data.values():
        if company["ticker"].upper() == ticker:
            return str(company["cik_str"]).zfill(10)

    raise Exception(f"Ticker not found: {ticker}")


def clean_html(html):
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style"]):
        tag.decompose()

    text = soup.get_text(separator=" ")
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def get_latest_filing(ticker, form_type):
    cik = get_cik(ticker)

    submissions_url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    data = safe_get_json(submissions_url)

    recent = data["filings"]["recent"]

    forms = recent["form"]
    accession_numbers = recent["accessionNumber"]
    primary_docs = recent["primaryDocument"]
    filing_dates = recent["filingDate"]

    for i, form in enumerate(forms):
        if form.upper() == form_type.upper():
            accession = accession_numbers[i]
            accession_no_dash = accession.replace("-", "")
            primary_doc = primary_docs[i]

            filing_url = (
                f"https://www.sec.gov/Archives/edgar/data/"
                f"{int(cik)}/{accession_no_dash}/{primary_doc}"
            )

            html = safe_get_text(filing_url)
            text = clean_html(html)

            return {
                "metadata": {
                    "ticker": ticker.upper(),
                    "cik": cik,
                    "form": form,
                    "filing_date": filing_dates[i],
                    "accession_number": accession,
                    "filing_url": filing_url
                },
                "text": text[:200000]
            }

    raise Exception(f"No {form_type} filing found for {ticker}")