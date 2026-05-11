# SKILLS.md

## Core Concept
Separate reasoning (LLM) from execution (MCP tools)

## Tools

## RAG Skills

### build_sec_rag_index

Builds a semantic vector index from the latest SEC filing.

Use when:
- User wants to prepare a filing for semantic search
- User asks to build or refresh the RAG index

Input:
- ticker
- form_type

Output:
- index path
- chunk count
- filing metadata

---

### rag_search_sec_filing

Performs semantic search over SEC filing chunks.

Use when:
- User asks for relevant filing evidence
- User asks to search conceptually, not only by keyword

Input:
- ticker
- form_type
- query
- top_k

Output:
- retrieved chunks
- similarity scores

---

### answer_question_with_rag

Answers a question using semantic retrieval and retrieved SEC filing chunks.

Use when:
- User asks narrative SEC filing questions
- User asks risks, strategy, growth drivers, competition, AI investments, supply chain, or management discussion questions

Output:
- analyst-style answer
- retrieved chunks
- similarity scores

### get_company_cik
Returns CIK for ticker

### get_latest_filing
Returns filing metadata

### search_latest_filing
Returns relevant chunks

### answer_question_from_sec_filing
Full analysis tool


## Agent Behavior

1. Understand user query
2. Choose tool
3. Execute via MCP
4. Interpret results
5. Generate answer

## Tool Rules

- CIK → get_company_cik
- Filing metadata → get_latest_filing
- Search → search_latest_filing
- Research question → answer_question_from_sec_filing
- If user asks a narrative SEC question, use `answer_question_from_sec_filing`.
- If user asks for financial ratios, YoY growth, EPS, dividends, or profitability, use `analyze_financial_metrics`.
- If user asks to validate or evaluate an answer, use `evaluate_financial_answer`.
## Financial Analytics Skills

### analyze_financial_metrics

Calculates key financial analytics for a ticker using SEC company facts.

Use when the user asks:
- revenue growth
- operating income growth
- net income growth
- earnings per share change
- dividend payout ratio
- profitability trend

Output:
- current year value
- prior year value
- YoY percentage change
- dividend payout ratio where available

---

### evaluate_financial_answer

Evaluates the generated answer against predefined ground truth.

Use when:
- validating the agent output
- checking numeric accuracy
- measuring academic project performance

Output:
- expected value
- actual value
- absolute error
- pass/fail result
- tolerance