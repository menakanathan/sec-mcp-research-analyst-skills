import json
from mcp.server.fastmcp import FastMCP
from sec_utils import get_latest_filing
from financials import calculate_financial_analytics
from evaluation import evaluate_against_ground_truth

mcp = FastMCP("SEC Agent")


@mcp.tool()
def answer_question_from_sec_filing(ticker: str, form_type: str, question: str) -> str:
    try:
        filing = get_latest_filing(ticker, form_type)

        text = filing["text"]
        metadata = filing["metadata"]

        return json.dumps({
            "metadata": metadata,
            "answer": text[:2000],
            "evidence_chunks": [
                {
                    "chunk_id": 1,
                    "text": text[:1000]
                }
            ]
        })

    except Exception as e:
        return json.dumps({
            "metadata": {
                "ticker": ticker,
                "form": form_type
            },
            "answer": f"Tool error: {str(e)}",
            "evidence_chunks": [],
            "error": str(e)
        })

@mcp.tool()
def analyze_financial_metrics(ticker: str) -> str:
    """
    Calculates financial analytics such as revenue growth, operating income growth,
    net income growth, EPS growth, and dividend payout ratio.
    """
    try:
        result = calculate_financial_analytics(ticker)
        return json.dumps(result, indent=2)

    except Exception as e:
        return json.dumps({
            "ticker": ticker,
            "error": str(e)
        }, indent=2)


@mcp.tool()
def evaluate_financial_answer(answer: str, metric_name: str) -> str:
    """
    Evaluates an answer against ground truth expected values.
    """
    try:
        result = evaluate_against_ground_truth(answer, metric_name)
        return json.dumps(result, indent=2)

    except Exception as e:
        return json.dumps({
            "error": str(e)
        }, indent=2)


@mcp.tool()
def analyze_financial_metrics(ticker: str) -> str:
    try:
        return json.dumps(calculate_financial_analytics(ticker), indent=2)
    except Exception as e:
        return json.dumps({
            "ticker": ticker,
            "error": str(e)
        }, indent=2)
      
if __name__ == "__main__":
    mcp.run(transport="stdio")