import asyncio
import json
import os
import sys
import traceback

import pandas as pd
import streamlit as st

from agent import (
    decide_tool_with_llm,
    normalize_tool_args,
    synthesize_answer,
    validate_agent_plan,
    build_execution_plan,
)
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


# =========================================================
# App Configuration
# =========================================================

st.set_page_config(
    page_title="SEC MCP 10-K Analyst",
    page_icon="",
    layout="wide",
)


# =========================================================
# Environment / Secrets
# =========================================================

def load_secrets() -> None:
    try:
        if "OPENAI_API_KEY" in st.secrets:
            os.environ["OPENAI_API_KEY"] = st.secrets["OPENAI_API_KEY"]

        if "SEC_USER_AGENT" in st.secrets:
            os.environ["SEC_USER_AGENT"] = st.secrets["SEC_USER_AGENT"]
    except Exception:
        pass


# =========================================================
# MCP Helpers
# =========================================================

def parse_mcp_response(response) -> dict:
    if not response.content:
        return {"error": "Empty MCP response"}

    text = response.content[0].text

    if not text or not text.strip():
        return {"error": "MCP returned blank response"}

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {
            "raw_text": text,
            "answer": text,
            "metadata": {},
            "evidence_chunks": [],
        }


def get_tool_names(tool_list_response) -> list:
    return [tool.name for tool in tool_list_response.tools]


async def run_agent(ticker: str, form_type: str, question: str):
    initial_plan = decide_tool_with_llm(ticker, form_type, question)

    server = StdioServerParameters(
        command=sys.executable,
        args=[os.path.abspath("server.py")],
        env=os.environ.copy(),
    )

    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tool_list_response = await session.list_tools()
            available_tools = get_tool_names(tool_list_response)

            validated_plan = validate_agent_plan(
                agent_plan=initial_plan,
                available_tools=available_tools,
                ticker=ticker,
                form_type=form_type,
                question=question,
            )

            validated_plan = normalize_tool_args(
                validated_plan,
                ticker,
                form_type,
                question,
            )
            selected_tools = [validated_plan["tool_name"]]
            execution_plan = build_execution_plan(
                question=question,
                selected_tools=selected_tools
            )

            response = await session.call_tool(
                validated_plan["tool_name"],
                validated_plan["tool_args"],
            )

            tool_result = parse_mcp_response(response)

            final_answer = synthesize_answer(
                question=question,
                tool_result=tool_result,
                agent_plan=validated_plan,
            )

            return {
                "initial_plan": initial_plan,
                "validated_plan": validated_plan,
                "available_tools": available_tools,
                "tool_result": tool_result,
                "final_answer": final_answer,
                "execution_plan": execution_plan,
            }

async def run_specific_tool(tool_name: str, tool_args: dict):
    server = StdioServerParameters(
        command=sys.executable,
        args=[os.path.abspath("server.py")],
        env=os.environ.copy(),
    )

    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            response = await session.call_tool(
                tool_name,
                tool_args
            )

            return parse_mcp_response(response)

# =========================================================
# Error Display
# =========================================================

def show_exception_group(error, level=0):
    if isinstance(error, BaseExceptionGroup):
        for i, sub_error in enumerate(error.exceptions, start=1):
            st.markdown(f"{'###' if level == 0 else '####'} Nested Error {i}")
            show_exception_group(sub_error, level + 1)
    else:
        st.exception(error)
        st.code("".join(traceback.format_exception(error)))


# =========================================================
# UI Components
# =========================================================
# QuantLink: Bridging the gap between the lab and the ledger

def render_header():
    st.title("SEC 10-K Analyst QuantLink")
    st.caption("\nAnalyzes 10-K filings, financial metrics and performs basic evaluations.\nBuilt with FastMCP and Streamlit."
    )

def render_sidebar():


    st.sidebar.header("Research Input")

    ticker = st.sidebar.text_input("Ticker", value="AAPL").upper().strip()

    form_type = st.sidebar.selectbox(
        "Filing Type",
        ["10-K", "10-Q", "8-K"],
    )

    demo_questions = [
        "What AI-related risks are discussed?",
        "What is the filing date of the latest 10-K?",
       # "What are the key factors affecting profitability?",
       # "What are the major business risks discussed in the filing?",
        "What are the major uncertainties mentioned by management?",
      #  "How does management describe their competitive advantage over other technical peers?",
        "What percentage of Net Income was paid as dividends?",
        "How has revenue changed compared to the prior year?",
        "What was EPS YoY change?",
        "Compute Inventory and Asset Turnover ratios. What do they indicate about operational efficiency?",
        "Look at the 5-year trend. Is revenue growing consistently, or is it volatile?",
        "List all 'Legal Proceedings' (Item 3) that involve intellectual property, patent infringement, or product failures",
        "Compare the Risk Factors (Item 1A) to last year's filing. Which are new, and which boilerplate risks were removed?",
        #"Evaluate this answer against wmt_operating_income_yoy_2024: Operating income increased by 4.2%.",
        #"Compute Interest coverage ration and Flag any debt maturing in the next 24 months.",
        #"How much remains for shareholders after every single expense, including taxes and interest, is paid.",
        "Compute the difference between Net Income and Operating Cash Flow."
       # "Are Accounts Receivable growing faster than Revenue? If so, is the company struggling to collect payments from its customers?",
       # "Calculate the Free Cash Flow (FCF). Is the company generating enough cash from operations to fund its own CapEx, or is it relying on new debt?"
    ]

    selected_question = st.sidebar.selectbox(
        "Quick Demo Question",
        demo_questions,
    )

    question = st.sidebar.text_area(
        "Question",
        value=selected_question,
        height=160,
    )

    run_button = st.sidebar.button("Run Analysis", type="primary")

    return ticker, form_type, question, run_button

def render_execution_plan(result: dict):
    execution_plan = result.get("execution_plan")

    if not execution_plan:
        return

    st.subheader(" Agent Execution Plan")

    st.info(f"User Goal: {execution_plan.get('user_goal')}")

    for step in execution_plan.get("steps", []):
        st.markdown(f"- {step}")

def render_agent_decision(result: dict):
    st.subheader(" Available MCP Tools")
    st.write(result["available_tools"])

    col1, col2 = st.columns(2)

    with col1:
        st.subheader(" Initial Agent Decision")
        st.json(result["initial_plan"])

    with col2:
        st.subheader(" Validated Agent Decision")
        st.json(result["validated_plan"])

    if "validation_warning" in result["validated_plan"]:
        st.warning(result["validated_plan"]["validation_warning"])

def render_final_answer_cards(result: dict):
    final_answer = result.get("final_answer")

    if not final_answer:
        return

   # st.subheader(" Analyst Summary")

    icon_map = {
        "Executive Summary": " Executive Summary",
        "Evidence and Calculation": " Evidence and Calculation",
        "Analyst Interpretation": " Analyst Interpretation",
        "Limitations": " Limitations",
        "Disclaimer": " Disclaimer",
    }

    sections = final_answer.split("## ")

    for section in sections:
        if not section.strip():
            continue

        lines = section.split("\n", 1)

        title = lines[0].strip()
        body = lines[1].strip() if len(lines) > 1 else ""

        display_title = icon_map.get(title, title)

        formatted_lines = []

        for line in body.split("\n"):
            line = line.strip()

            if not line:
                continue

            if line.startswith("- "):
                formatted_lines.append(
                    f"<div style='margin-left:14px; margin-bottom:6px;'>• {line[2:]}</div>"
                )
            else:
                formatted_lines.append(
                    f"<div style='margin-bottom:6px;'>{line}</div>"
                )

        formatted_body = "".join(formatted_lines)

        st.markdown(
            f"""
<div style="
    background-color:#F8FAFC;
    padding:20px;
    border-radius:14px;
    margin-bottom:18px;
    border:1px solid #E5E7EB;
    box-shadow:0 2px 8px rgba(0,0,0,0.05);
">

<div style="
    font-size:20px;
    font-weight:700;
    margin-bottom:12px;
    color:#111827;
">
{display_title}
</div>

<div style="
    font-size:15px;
    line-height:1.8;
    color:#374151;
">
{formatted_body}
</div>

</div>
""",
            unsafe_allow_html=True,
        )

def render_final_answer(result: dict):
    final_answer = result.get("final_answer")

    if not final_answer:
        return

    #st.subheader(" Analyst Summary")

    sections = final_answer.split("## ")

    for section in sections:
        if not section.strip():
            continue

        lines = section.split("\n", 1)

        title = lines[0].strip()
                
        body = lines[1].strip() if len(lines) > 1 else ""
        # Remove markdown formatting artifacts
        body = body.replace("**", "")
        body = body.replace("__", "")
        body = body.replace("`", "")

        st.markdown(f"### {title}")
        st.write(body)


def render_kpi_dashboard(tool_result: dict):
    if not isinstance(tool_result, dict):
        st.warning("No valid MCP tool result available for KPI dashboard.")
        return

    if "financial_analytics" not in tool_result:
        return

    analytics = tool_result["financial_analytics"]

    dashboard_current_fy = tool_result.get("dashboard_current_fy")
    dashboard_prior_fy = tool_result.get("dashboard_prior_fy")

    # Find one metric with valid period dates
    sample_metric = None

    for _, values in analytics.items():
        if isinstance(values, dict) and values.get("current_period_end"):
            sample_metric = values
            break

    current_end = sample_metric.get("current_period_end") if sample_metric else "N/A"
    prior_end = sample_metric.get("prior_period_end") if sample_metric else "N/A"

    st.info(
        f"""
    Dashboard Fiscal Comparison: FY{dashboard_current_fy} vs FY{dashboard_prior_fy}

    Period End: {current_end} vs {prior_end}
    """
    )

    st.subheader(" KPI Dashboard")

    cols = st.columns(3)
    index = 0

    for metric, values in analytics.items():
        if not isinstance(values, dict):
            continue

        if "current_display" not in values and "value_percent" not in values:
            continue

        col = cols[index % 3]

        if "value_percent" in values:
            col.metric(
                label=metric,
                value=f"{values.get('value_percent')}%",
            )
        else:
            col.metric(
                label=metric,
                value=values.get("current_display", "N/A"),
                delta=values.get("yoy_display", values.get("yoy_change_percent")),
            )
        if metric == "Dividend Payout Ratio":
            col.caption(f"FY{values.get('current_year', 'N/A')}")
        else:
            col.caption(
                f"FY{values.get('current_year', 'N/A')} vs FY{values.get('prior_year', 'N/A')}"
            )
        index += 1

def render_metadata(tool_result: dict):
    metadata = tool_result.get("metadata")

    if metadata:
        st.subheader(" Filing Metadata")
        st.json(metadata)


def render_evidence_chunks(tool_result: dict):
    chunks = tool_result.get("evidence_chunks", [])

    if not chunks:
        return

    st.subheader(" Evidence Chunks")

    for chunk in chunks:
        with st.expander(
            f"Chunk {chunk.get('chunk_id', 'N/A')}",
            expanded=False,
        ):
            st.write(chunk.get("text", ""))

def render_raw_output(tool_result: dict):
    st.subheader(" MCP Tool Result")
    st.json(tool_result)

def render_capex_waterfall(tool_result):
    analytics = tool_result.get("financial_analytics", {})

    capex = analytics.get("Capital Expenditure", {})

    raw_capex_value = capex.get("current_value")

    if raw_capex_value is None:
        st.info(
            "CapEx Waterfall not available because Capital Expenditure value is missing "
            "for the dashboard fiscal year."
        )
        return

    capex_value = abs(raw_capex_value)

    if capex_value == 0:
        st.info("CapEx Waterfall not available because Capital Expenditure is zero.")
        return

    st.subheader(" CapEx Waterfall")

    maintenance = capex_value * 0.35
    growth = capex_value * 0.65

    df = pd.DataFrame({
        "Category": ["Maintenance CapEx", "Growth CapEx"],
        "Amount ($B)": [
            maintenance / 1_000_000_000,
            growth / 1_000_000_000
        ]
    })

    st.bar_chart(df, x="Category", y="Amount ($B)")

    st.caption(
        "Note: Maintenance vs Growth split is estimated. SEC filings usually do not provide a clean standardized split."
    )


def render_risk_heatmap(tool_result):
    chunks = tool_result.get("evidence_chunks", [])

    if not chunks:
        return

    st.subheader(" Risk Keyword Heatmap")

    text = " ".join(chunk.get("text", "") for chunk in chunks).lower()

    risk_keywords = {
        "Supply Chain": ["supply chain", "supplier", "inventory"],
        "Interest Rates": ["interest rate", "rates", "borrowing"],
        "Inflation": ["inflation", "cost pressure", "pricing"],
        "Competition": ["competition", "competitive"],
        "Regulation": ["regulation", "regulatory", "compliance"],
        "Cybersecurity": ["cybersecurity", "cyber", "data breach"],
        "Labor": ["labor", "employee", "workforce"],
        "Demand": ["demand", "consumer", "sales"]
    }

    rows = []

    for risk, terms in risk_keywords.items():
        count = sum(text.count(term) for term in terms)

        if count > 0:
            rows.append({
                "Risk": risk,
                "Frequency": count
            })

    if not rows:
        st.info("No major risk keywords found in retrieved evidence chunks.")
        return

    df = pd.DataFrame(rows).sort_values("Frequency", ascending=False)

    st.bar_chart(df, x="Risk", y="Frequency")

    st.caption(
        "Larger bars indicate more frequent mentions in retrieved filing evidence, not necessarily higher actual business risk."
    )

def generate_divergence_explanation(ni_yoy, ocf_yoy):
    diff = abs(ni_yoy - ocf_yoy)

    if ni_yoy > 0 and ocf_yoy < 0:
        severity = "High"
        explanation = (
            "Net Income increased while Operating Cash Flow declined. "
            "This is a strong earnings-quality warning. It may indicate working capital pressure, "
            "higher receivables, inventory build up, non-cash gains, or timing differences."
        )

    elif ni_yoy < 0 and ocf_yoy > 0:
        severity = "Medium"
        explanation = (
            "Net Income declined while Operating Cash Flow improved. "
            "This may suggest stronger cash conversion despite weaker accounting earnings. "
            "Review depreciation, restructuring charges, impairment charges, and working capital movements."
        )

    elif diff >= 100:
        severity = "Medium"
        explanation = (
            f"Both Net Income and Operating Cash Flow moved in the same direction, but the gap is large "
            f"({diff:.2f} percentage points). This may indicate a difference between accounting earnings "
            "growth and cash generation. Review cash flow statement adjustments, accounts receivable, "
            "inventory, payables, and non-cash items."
        )

    else:
        severity = "Low"
        explanation = (
            "Net Income and Operating Cash Flow are broadly aligned. "
            "No major earnings versus cash flow divergence is detected based on YoY movement."
        )

    return severity, explanation


def render_divergence_alert(tool_result):
    analytics = tool_result.get("financial_analytics", {})

    net_income = analytics.get("Net Income", {})
    operating_cf = analytics.get("Operating Cash Flow", {})

    ni_yoy = net_income.get("yoy_change_percent")
    ocf_yoy = operating_cf.get("yoy_change_percent")

    if ni_yoy is None or ocf_yoy is None:
        return

    st.subheader(" Divergence Alert")

    severity, explanation = generate_divergence_explanation(ni_yoy, ocf_yoy)

    if severity == "High":
        st.error(
            f"High divergence detected. Net Income YoY: {ni_yoy}%, "
            f"Operating Cash Flow YoY: {ocf_yoy}%."
        )
    elif severity == "Medium":
        st.warning(
            f"Potential divergence detected. Net Income YoY: {ni_yoy}%, "
            f"Operating Cash Flow YoY: {ocf_yoy}%."
        )
    else:
        st.success(
            f"No major divergence detected. Net Income YoY: {ni_yoy}%, "
            f"Operating Cash Flow YoY: {ocf_yoy}%."
        )

    st.markdown("### Analyst Explanation")
    st.write(explanation)


def render_results(result: dict):
    #render_agent_decision(result)
    render_execution_plan(result)   
    render_final_answer(result)

    tool_result = result["tool_result"]

    if "retrieved_chunks" in tool_result:
        st.subheader(" RAG Retrieved Chunks")

        for chunk in tool_result["retrieved_chunks"]:
            with st.expander(
                f"Chunk {chunk.get('chunk_id')} | Similarity {chunk.get('similarity_score')}",
                expanded=False
            ):
                st.write(chunk.get("text"))

    #tool_result = result.get("tool_result") if isinstance(result, dict) else None

    if not isinstance(tool_result, dict):
        st.error("Tool result is missing or invalid.")
        st.json(result)
        return

    render_kpi_dashboard(tool_result)
    #New visual analytics
    #render_capex_waterfall(tool_result)
    #render_risk_heatmap(tool_result)
    render_divergence_alert(tool_result)
    #render_metadata(tool_result)
    render_evidence_chunks(tool_result)
    #render_raw_output(tool_result)


# =========================================================
# Main App
# =========================================================

def main():

    if st.sidebar.button("Clear Result Cache"):
        st.session_state.last_result = None
        st.rerun()

    load_secrets()
    render_header()

    ticker, form_type,question, run_button = render_sidebar()

    if "last_result" not in st.session_state:
        st.session_state.last_result = None

    if run_button:
        if not ticker or not question:
            st.error("Please enter both ticker and question.")
            return

        try:
            with st.spinner("Running MCP research agent..."):
                result = asyncio.run(
                    run_agent(
                        ticker=ticker,
                        form_type=form_type,
                        question=question,
                    )
                )

            st.session_state.last_result = result
            st.success("Analysis complete.")

        except BaseExceptionGroup as eg:
            st.error("MCP TaskGroup failed. Full nested error:")
            show_exception_group(eg)
            return

        except Exception as e:
            st.error("Unexpected error")
            st.exception(e)
            st.code("".join(traceback.format_exception(e)))
            return
        
    if st.session_state.last_result:
        render_results(st.session_state.last_result)

if __name__ == "__main__":
    main()