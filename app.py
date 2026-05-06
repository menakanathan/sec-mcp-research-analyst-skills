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
)
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


# =========================================================
# App Configuration
# =========================================================

st.set_page_config(
    page_title="SEC GenAI Research Analyst",
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
            }


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

def render_header():
    st.title("SEC MCP Research Analyst")
    st.caption(
        " MCP Agent with SKILLS.md and Financial Analytics, Evaluation Metrics"
    )

def render_sidebar():
    st.sidebar.header("Research Input")

    ticker = st.sidebar.text_input("Ticker", value="AAPL").upper().strip()

    form_type = st.sidebar.selectbox(
        "Filing Type",
        ["10-K", "10-Q", "8-K"],
    )

    demo_questions = [
        "What is the filing date of the latest 10-K?",
        "What is the CIK for Apple?",
        "What are the major business risks discussed in the filing?",
        "For AAPL, what was the YoY change in Basic EPS?",
        "Compared to the prior year, what percentage did Apple's operating income increase by?",
        "What percentage of Net Income was paid as dividends?",
        "Evaluate this answer against aapl_operating_income_yoy_2024: Operating income increased by 4.2%.",
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


def render_final_answer(result: dict):
    st.subheader(" Final Analyst Answer")
    st.markdown(result["final_answer"])


def render_kpi_dashboard(tool_result: dict):
    if "financial_analytics" not in tool_result:
        return

    analytics = tool_result["financial_analytics"]

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


def render_results(result: dict):
    render_agent_decision(result)
    render_final_answer(result)

    tool_result = result["tool_result"]

    render_kpi_dashboard(tool_result)
    render_metadata(tool_result)
    render_evidence_chunks(tool_result)
    render_raw_output(tool_result)


# =========================================================
# Main App
# =========================================================

def main():
    load_secrets()
    render_header()

    ticker, form_type, question, run_button = render_sidebar()

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