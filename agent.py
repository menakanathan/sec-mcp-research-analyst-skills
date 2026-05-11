import json
import os
import re
from typing import Any, Dict, List

from openai import OpenAI

FINANCIAL_KEYWORDS = [
    "eps",
    "earnings per share",
    "operating income",
    "revenue",
    "dividends",
    "net income",
    "dividend",
    "payout",
    "yoy",
    "year over year",
    "year-over-year",
    "percentage",
    "growth",
    "profitability",
    "margin",
    "cash flow",
    "assets",
    "liabilities",
    "equity",
]

RAG_KEYWORDS = [
    "risk",
    "risks",
    "management",
    "discussion",
    "md&a",
    "strategy",
    "strategic",
    "competition",
    "competitive",
    "market",
    "growth drivers",
    "demand",
    "guidance",
    "future outlook",
    "outlook",
    "supply chain",
    "supplier",
    "customer concentration","uncertainty", "uncertainties",
    "cybersecurity",
    "security",
    "privacy",
    "regulation",
    "regulatory",
    "lawsuit",
    "litigation",
    "macro",
    "inflation",
    "interest rates",
    "ai",
    "artificial intelligence",
    "copilot",
    "gpu",
    "data center",
    "cloud",
    "investments",
    "capex",
    "capital allocation",
    "operations",
    "manufacturing",
    "inventory",
    "headwinds",
    "tailwinds",
    "semiconductor",
    "tariffs",
    "geopolitical",
]

EVALUATION_KEYWORDS = [
    "evaluate",
    "validate",
    "check",
    "compare against",
    "ground truth",
    "is this correct",
    "accuracy",
    "pass",
    "fail",
]

METRIC_ALIASES = {
    "dividend": "wmt_dividend_payout_ratio_2024",
    "payout": "wmt_dividend_payout_ratio_2024",
    "operating income": "wmt_operating_income_yoy_2024",
    "eps": "wmt_basic_eps_yoy_2024",
    "earnings per share": "wmt_basic_eps_yoy_2024",
}


def load_skills_md() -> str:
    try:
        with open("SKILLS.md", "r", encoding="utf-8") as file:
            return file.read()
    except FileNotFoundError:
        return ""

def build_execution_plan(question: str, selected_tools: list):

    steps = []

    step_number = 1

    for tool in selected_tools:

        if tool == "answer_question_with_rag":
            steps.append(
                f"{step_number}. Perform semantic RAG retrieval from SEC filing"
            )

        elif tool == "get_financial_analytics":
            steps.append(
                f"{step_number}. Compute structured financial analytics from SEC XBRL data"
            )

        elif tool == "evaluate_financial_answer":
            steps.append(
                f"{step_number}. Validate financial calculations and fiscal-year consistency"
            )

        elif tool == "build_sec_rag_index":
            steps.append(
                f"{step_number}. Build semantic vector index for SEC filing"
            )

        elif tool == "rag_search_sec_filing":
            steps.append(
                f"{step_number}. Retrieve top semantic filing evidence chunks"
            )

        elif tool == "send_research_digest":
            steps.append(
                f"{step_number}. Generate and distribute research digest"
            )

        else:
            steps.append(
                f"{step_number}. Execute tool: {tool}"
            )

        step_number += 1

    return {
        "user_goal": question,
        "steps": steps
    }

def extract_json_from_text(text: str) -> Dict[str, Any]:
    """
    Handles cases where an LLM returns JSON with extra text around it.
    """
    if not text:
        raise ValueError("Empty LLM response")

    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found in LLM response: {text}")

    return json.loads(match.group(0))


def infer_metric_name(question: str) -> str:
    q = question.lower()

    # If the question already contains a ground truth key, use it directly.
    known_keys = [
        "wmt_dividend_payout_ratio_2024",
        "wmt_operating_income_yoy_2024",
        "wmt_basic_eps_yoy_2024",
    ]

    for key in known_keys:
        if key in q:
            return key

    for keyword, metric_name in METRIC_ALIASES.items():
        if keyword in q:
            return metric_name

    return "wmt_dividend_payout_ratio_2024"

def extract_numeric_answer(question: str) -> str:
    """
    Extracts the last numeric value from an evaluation-style question.
    Example:
    'Evaluate ... Operating income increased by 4.2%.' -> '4.2'
    """
    matches = re.findall(r"-?\d+\.?\d*", question)
    return matches[-1] if matches else question


def is_evaluation_question(question: str) -> bool:
    q = question.lower()
    return any(keyword in q for keyword in EVALUATION_KEYWORDS)
 

def is_financial_question(question: str) -> bool:
    q = question.lower()
    return any(keyword in q for keyword in FINANCIAL_KEYWORDS)

def is_rag_question(question: str) -> bool:
    q = question.lower()
    return any(keyword in q for keyword in RAG_KEYWORDS)   

def fallback_plan(ticker: str, form_type: str, question: str) -> Dict[str, Any]:
    """
    Deterministic fallback when OpenAI API is unavailable or quota-limited.
    """
    # ---------------------------------------------------------
    # Evaluation questions
    # ---------------------------------------------------------
    if is_evaluation_question(question):
        return {
            "tool_name": "evaluate_financial_answer",
            "tool_args": {
                "answer": extract_numeric_answer(question),
                "metric_name": infer_metric_name(question),
            },
            "reason": (
                "Fallback selected evaluation because "
                "the question asks to validate an answer."
            ),
        }
    # ---------------------------------------------------------
    # Structured financial analytics
    # ---------------------------------------------------------
    if is_financial_question(question):
        return {
            "tool_name": "analyze_financial_metrics",
            "tool_args": {
                "ticker": ticker,
            },
            "reason": (
                "Fallback selected financial analytics "
                "because the question asks about financial metrics."
            ),
        }

    # ---------------------------------------------------------
    # Narrative / RAG questions
    # ---------------------------------------------------------
    if is_rag_question(question):
        return {
            "tool_name": "answer_question_with_rag",
            "tool_args": {
                "ticker": ticker,
                "form_type": form_type,
                "question": question,
            },
            "reason": (
                "Narrative SEC filing question detected. "
                "Using semantic RAG retrieval."
            ),
        }


    # ---------------------------------------------------------
    # Generic filing fallback
    # ---------------------------------------------------------
    return {
        "tool_name": "answer_question_from_sec_filing",
        "tool_args": {
            "ticker": ticker,
            "form_type": form_type,
            "question": question,
        },
        "reason": (
            "Fallback selected general SEC filing question answering."
        ),
    }

def validate_agent_plan(
    agent_plan: Dict[str, Any],
    available_tools: List[str],
    ticker: str,
    form_type: str,
    question: str,
) -> Dict[str, Any]:
    """
    Ensures the selected tool exists in the MCP server.
    If not, replaces it with a safe fallback.
    """
    selected_tool = agent_plan.get("tool_name")

    if selected_tool in available_tools:
        return agent_plan

    safe_plan = fallback_plan(ticker, form_type, question)

    if safe_plan["tool_name"] not in available_tools:
        # Emergency fallback: use a general SEC QA tool if present.
        if "answer_question_from_sec_filing" in available_tools:
            safe_plan = {
                "tool_name": "answer_question_from_sec_filing",
                "tool_args": {
                    "ticker": ticker,
                    "form_type": form_type,
                    "question": question,
                },
                "reason": "Emergency fallback selected general SEC QA tool.",
            }
        elif available_tools:
            safe_plan = {
                "tool_name": available_tools[0],
                "tool_args": {},
                "reason": "Emergency fallback selected the first available MCP tool.",
            }
        else:
            safe_plan = {
                "tool_name": "",
                "tool_args": {},
                "reason": "No MCP tools available.",
            }

    safe_plan["validation_warning"] = (
        f"Original tool '{selected_tool}' was not found in MCP server. "
        f"Replaced with '{safe_plan.get('tool_name')}'."
    )

    return safe_plan


def normalize_tool_args(
    agent_plan: Dict[str, Any],
    ticker: str,
    form_type: str,
    question: str,
) -> Dict[str, Any]:
    """
    Fixes common LLM schema mistakes before MCP execution.
    Prevents errors such as:
    - filing_type instead of form_type
    - user_answer instead of answer
    - requested_metric instead of metric_name
    """
    tool_name = agent_plan.get("tool_name")
    tool_args = agent_plan.get("tool_args", {}) or {}

    if "filing_type" in tool_args and "form_type" not in tool_args:
        tool_args["form_type"] = tool_args.pop("filing_type")

    if "user_answer" in tool_args and "answer" not in tool_args:
        tool_args["answer"] = tool_args.pop("user_answer")

    if "requested_metric" in tool_args and "metric_name" not in tool_args:
        tool_args["metric_name"] = tool_args.pop("requested_metric")

    if tool_name == "answer_question_from_sec_filing":
        tool_args = {
            "ticker": ticker,
            "form_type": form_type,
            "question": question,
        }

    elif tool_name == "search_latest_filing":
        tool_args = {
            "ticker": ticker,
            "form_type": form_type,
            "query": question,
        }

    elif tool_name == "get_latest_filing":
        tool_args = {
            "ticker": ticker,
            "form_type": form_type,
        }

    elif tool_name == "get_company_cik":
        tool_args = {
            "ticker": ticker,
        }

    elif tool_name == "analyze_financial_metrics":
        tool_args = {
            "ticker": ticker,
        }

    elif tool_name == "build_sec_rag_index":
        tool_args = {
        "ticker": ticker,
        "form_type": form_type
    }
    elif tool_name == "rag_search_sec_filing":
        tool_args = {
            "ticker": ticker,
            "form_type": form_type,
            "query": question,
            "top_k": int(tool_args.get("top_k", 5))
        }

    elif tool_name == "answer_question_with_rag":
        tool_args = {
            "ticker": ticker,
            "form_type": form_type,
            "question": question
        }


    elif tool_name == "evaluate_financial_answer":
        tool_args = {
            "answer": str(tool_args.get("answer", extract_numeric_answer(question))),
            "metric_name": tool_args.get("metric_name", infer_metric_name(question)),
        }

    agent_plan["tool_args"] = tool_args
    return agent_plan


def decide_tool_with_llm(ticker: str, form_type: str, question: str) -> Dict[str, Any]:
    """
    LLM planner.
    Falls back to deterministic logic when no API key, quota issue, or invalid JSON.
    """

    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        return fallback_plan(ticker, form_type, question)

    try:
        client = OpenAI(api_key=api_key)
        skills = load_skills_md()

        prompt = f"""
You are an autonomous MCP research and financial analyst agent.

Read SKILLS.md and choose the best MCP tool.

Available skills:
{skills}

User request:
Ticker: {ticker}
Form type: {form_type}
Question: {question}

Allowed tools:
1. get_company_cik
2. get_latest_filing
3. search_latest_filing
4. answer_question_from_sec_filing
5. analyze_financial_metrics
6. evaluate_financial_answer
7. build_sec_rag_index
8. rag_search_sec_filing
9. answer_question_with_rag

Return ONLY valid JSON in this exact structure:
{{
  "tool_name": "tool_name_here",
  "tool_args": {{}},
  "reason": "brief reason"
}}

Tool selection rules:
- If user asks for CIK, use get_company_cik.
- If user asks for filing date, accession number, or filing URL, use get_latest_filing.
- If user asks to search or find relevant filing text, use search_latest_filing.
- If user asks about EPS, operating income, revenue, net income, dividends, payout ratio, YoY change, percentage growth, margin, or profitability, use analyze_financial_metrics.
- If user asks to evaluate or validate an answer against ground truth, use evaluate_financial_answer.
- If user asks a narrative question about filing content, risks, strategy, competition, AI, supply chain, or management discussion, prefer answer_question_with_rag.
- If user asks to build or refresh RAG index, use build_sec_rag_index.
- If user asks to search filing evidence semantically, use rag_search_sec_filing.
- For narrative SEC filing questions about risks, uncertainties, management discussion, strategy, outlook, competition, AI, supply chain, cybersecurity, regulation, or growth drivers, ALWAYS use answer_question_with_rag.Do NOT use answer_question_from_sec_filing unless RAG is unavailable.

Argument rules:
- get_company_cik must use: {{"ticker": "{ticker}"}}
- get_latest_filing must use: {{"ticker": "{ticker}", "form_type": "{form_type}"}}
- search_latest_filing must use: {{"ticker": "{ticker}", "form_type": "{form_type}", "query": "{question}"}}
- answer_question_from_sec_filing must use: {{"ticker": "{ticker}", "form_type": "{form_type}", "question": "{question}"}}
- analyze_financial_metrics must use: {{"ticker": "{ticker}"}}
- evaluate_financial_answer must use: {{"answer": "<numeric or text answer>", "metric_name": "<metric key from ground_truth.json>"}}

Important:
- Use exact key `form_type`, not `filing_type`.
- Use exact key `answer`, not `user_answer`.
- Use exact key `metric_name`, not `requested_metric`.
"""

        response = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt,
        )

        return extract_json_from_text(response.output_text)

    except Exception:
        return fallback_plan(ticker, form_type, question)


def synthesize_answer(
    question: str,
    tool_result: Dict[str, Any],
    agent_plan: Dict[str, Any],
) -> str:
    """
    LLM synthesis.
    Falls back to deterministic readable output if LLM fails or quota is exceeded.
    """
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        return fallback_synthesis(question, tool_result, agent_plan)

    try:
        client = OpenAI(api_key=api_key)

        prompt = f"""
You are a professional SEC research and financial analyst.

User question:
{question}

Agent decision:
{json.dumps(agent_plan, indent=2)}

MCP tool result:
{json.dumps(tool_result, indent=2)}

Create a clear analyst-style answer.

Required format:

## Summary
Give a 2-3 sentence direct answer.

## Evidence and Calculation
Show the metric values, prior/current fiscal years, and calculation.

## Analyst Interpretation
Explain what the result means from a business and financial perspective.

## Limitations
List 2-3 limitations.

## Disclaimer
State that this is based on SEC filing data and is not investment advice.

Rules:
- Use only the MCP tool result.
- Do not invent numbers.
- If financial_analytics is available, use those values.
- If an evaluation result is available, clearly explain pass/fail.
- If the exact requested metric is not available, say so clearly.
- Use markdown headings with ##.
- Do not use numbered headings like "1. Direct Answer".
- Keep the answer concise and academic.
"""

        response = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt,
        )

        return response.output_text

    except Exception as error:
        return f"""
## LLM Reasoning Failed

The MCP tool ran, but the LLM reasoning layer failed.

**Reason:** {str(error)}

## Fallback Output

{fallback_synthesis(question, tool_result, agent_plan)}
"""


def fallback_synthesis(
    question: str,
    tool_result: Dict[str, Any],
    agent_plan: Dict[str, Any],
) -> str:
    """
    Readable deterministic output used when LLM is unavailable.
    """
    if "evaluation_result" in tool_result or "passed" in tool_result:
        return f"""
## Evaluation Result

**Question:** {question}

**Tool Used:** {agent_plan.get("tool_name")}

```json
{json.dumps(tool_result, indent=2)}
```

## Interpretation

The evaluation tool compared the provided answer against the expected ground-truth value using a tolerance-based check.

## Disclaimer

This is for academic demonstration only and is not investment advice.
"""

    if "financial_analytics" in tool_result:
        analytics = tool_result["financial_analytics"]

        output = f"""
## Financial Analytics Result

**Question:** {question}

**Tool Used:** {agent_plan.get("tool_name")}

"""

        if "validation_warning" in agent_plan:
            output += f"""
**Validation Warning:** {agent_plan["validation_warning"]}

"""

        for metric, values in analytics.items():
            output += f"""
### {metric}

```json
{json.dumps(values, indent=2)}
```
"""

        output += """
## Interpretation

The MCP financial analytics tool extracted available SEC XBRL company facts and calculated year-over-year changes where current and prior-year values were available.

## Disclaimer

This is for academic demonstration only and is not investment advice.
"""
        return output

    if "answer" in tool_result:
        return str(tool_result["answer"])

    if "error" in tool_result:
        return f"""
## Tool Error

{tool_result.get("error")}

## Raw Output

```json
{json.dumps(tool_result, indent=2)}
```
"""

    return json.dumps(tool_result, indent=2)
