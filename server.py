import os
import re
import json
from mcp.server.fastmcp import FastMCP
from sec_utils import get_latest_filing
from financials import calculate_financial_analytics
from evaluation import evaluate_against_ground_truth
from rag_utils import build_rag_index, semantic_search,load_rag_index

mcp = FastMCP("SEC Agent")
@mcp.tool()
def build_sec_rag_index(ticker: str, form_type: str = "10-K") -> str:
    """
    Builds a local semantic RAG index for the latest SEC filing.
    """
    try:
        filing = get_latest_filing(ticker, form_type)

        if isinstance(filing, str):
            text = filing
            metadata = {
                "ticker": ticker.upper(),
                "form_type": form_type
            }
        else:
            text = filing.get("text", "")
            metadata = filing.get("metadata", {})

        if not text:
            return json.dumps({
                "error": "No filing text available to build RAG index.",
                "ticker": ticker,
                "form_type": form_type
            }, indent=2)

        result = build_rag_index(
            ticker=ticker,
            form_type=form_type,
            filing_text=text,
            metadata=metadata
        )

        return json.dumps(result, indent=2)

    except Exception as e:
        return json.dumps({
            "error": str(e),
            "ticker": ticker,
            "form_type": form_type
        }, indent=2)


@mcp.tool()
def rag_search_sec_filing(ticker: str, form_type: str, query: str, top_k: int = 5) -> str:
    """
    Performs semantic search over a previously built SEC filing RAG index.
    """
    try:
        result = semantic_search(
            ticker=ticker,
            form_type=form_type,
            query=query,
            top_k=top_k
        )

        return json.dumps(result, indent=2)

    except Exception as e:
        return json.dumps({
            "error": str(e),
            "ticker": ticker,
            "form_type": form_type,
            "query": query,
            "results": []
        }, indent=2)
    
@mcp.tool()
def answer_question_with_rag(ticker: str, form_type: str, question: str) -> str:
    """
    Answers SEC filing questions using semantic RAG retrieval.
    If the RAG index does not exist, it automatically builds the index first.
    """
    try:
        # ---------------------------------------------------------
        # Step 1: Check if RAG index exists
        # ---------------------------------------------------------
        existing_index = load_rag_index(
            ticker=ticker,
            form_type=form_type
        )

        index_status = "existing_index_used"

        # ---------------------------------------------------------
        # Step 2: Build RAG index automatically if missing
        # ---------------------------------------------------------
        if not existing_index:
            filing = get_latest_filing(
                ticker=ticker,
                form_type=form_type
            )

            if isinstance(filing, str):
                filing_text = filing
                metadata = {
                    "ticker": ticker.upper(),
                    "form_type": form_type
                }
            else:
                filing_text = filing.get("text", "")
                metadata = filing.get("metadata", {})

            if not filing_text:
                return json.dumps({
                    "answer": "Unable to build RAG index because no filing text was available.",
                    "ticker": ticker,
                    "form_type": form_type,
                    "question": question,
                    "retrieved_chunks": [],
                    "metadata": metadata,
                    "index_status": "index_build_failed_no_text"
                }, indent=2)

            build_rag_index(
                ticker=ticker,
                form_type=form_type,
                filing_text=filing_text,
                metadata=metadata
            )

            index_status = "index_missing_built_automatically"

        # ---------------------------------------------------------
        # Step 3: Run semantic search
        # ---------------------------------------------------------
        search_result = semantic_search(
            ticker=ticker,
            form_type=form_type,
            query=question,
            top_k=5
        )

        if "error" in search_result:
            return json.dumps({
                "answer": "RAG semantic search failed.",
                "error": search_result.get("error"),
                "ticker": ticker,
                "form_type": form_type,
                "question": question,
                "retrieved_chunks": [],
                "index_status": index_status
            }, indent=2)

        chunks = search_result.get("results", [])

        if not chunks:
            return json.dumps({
                "answer": "No relevant chunks found.",
                "retrieved_chunks": [],
                "metadata": search_result.get("metadata", {}),
                "index_status": index_status
            }, indent=2)

        # ---------------------------------------------------------
        # Step 4: Build context for LLM
        # ---------------------------------------------------------
        context = "\n\n".join(
            [
                f"Chunk {chunk['chunk_id']} | Similarity {chunk['similarity_score']}\n{chunk['text']}"
                for chunk in chunks
            ]
        )

        api_key = os.getenv("OPENAI_API_KEY")

        if not api_key:
            return json.dumps({
                "answer": (
                    "RAG retrieval succeeded, but OPENAI_API_KEY is missing "
                    "for analyst-style answer generation."
                ),
                "retrieved_chunks": chunks,
                "metadata": search_result.get("metadata", {}),
                "retrieval_method": "semantic_embedding_rag",
                "index_status": index_status
            }, indent=2)

        # ---------------------------------------------------------
        # Step 5: Generate analyst-style answer from retrieved chunks
        # ---------------------------------------------------------
        from openai import OpenAI

        client = OpenAI(api_key=api_key)

        prompt = f"""
You are an SEC filings research analyst.

Answer the user question using only the retrieved filing chunks.

User question:
{question}

Retrieved filing chunks:
{context}

Format:
## Executive Summary
## Evidence
## Analyst Interpretation
## Limitations
## Disclaimer

Rules:
- Use only retrieved context.
- Do not invent facts.
- Cite chunk IDs in the answer.
- If evidence is incomplete, clearly say so.
"""

        response = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt
        )

        return json.dumps({
            "answer": response.output_text,
            "retrieved_chunks": chunks,
            "metadata": search_result.get("metadata", {}),
            "retrieval_method": "semantic_embedding_rag",
            "index_status": index_status
        }, indent=2)

    except Exception as e:
        return json.dumps({
            "error": str(e),
            "ticker": ticker,
            "form_type": form_type,
            "question": question,
            "retrieved_chunks": [],
            "index_status": "rag_tool_failed"
        }, indent=2)
    
@mcp.tool()
def search_latest_filing(ticker: str, form_type: str, query: str) -> str:
    """
    Simple keyword search over latest filing text.
    Returns relevant evidence chunks.
    """
    try:
        filing = get_latest_filing(ticker, form_type)

        if isinstance(filing, str):
            text = filing
            metadata = {
                "ticker": ticker.upper(),
                "form_type": form_type
            }
        elif isinstance(filing, dict):
            text = filing.get("text", "")
            metadata = filing.get(
                "metadata",
                {
                    "ticker": ticker.upper(),
                    "form_type": form_type
                }
            )
        else:
            return json.dumps({
                "metadata": {
                    "ticker": ticker.upper(),
                    "form_type": form_type
                },
                "query": query,
                "error": "Unsupported filing response type.",
                "evidence_chunks": []
            }, indent=2)

        if not text:
            return json.dumps({
                "metadata": metadata,
                "query": query,
                "error": "No filing text available.",
                "evidence_chunks": []
            }, indent=2)

        query_terms = [term.lower() for term in re.findall(r"\w+", query)]

        chunks = []
        chunk_size = 1800
        overlap = 250
        start = 0
        chunk_id = 1

        while start < len(text):
            chunk = text[start:start + chunk_size]
            chunk_lower = chunk.lower()

            score = sum(chunk_lower.count(term) for term in query_terms)

            if score > 0:
                chunks.append({
                    "chunk_id": chunk_id,
                    "score": score,
                    "text": chunk
                })

            start += chunk_size - overlap
            chunk_id += 1

        chunks = sorted(
            chunks,
            key=lambda x: x["score"],
            reverse=True
        )[:5]

        return json.dumps({
            "metadata": metadata,
            "query": query,
            "evidence_chunks": chunks,
            "chunk_count": len(chunks)
        }, indent=2)

    except Exception as e:
        return json.dumps({
            "metadata": {
                "ticker": ticker.upper(),
                "form_type": form_type
            },
            "query": query,
            "error": str(e),
            "evidence_chunks": []
        }, indent=2)

@mcp.tool()
def answer_question_from_sec_filing(ticker: str, form_type: str, question: str) -> str:
    """
    Research analyst style SEC filing Q&A.
    Retrieves relevant filing chunks and generates an analyst style response.
    """
    try:
        search_result = json.loads(
            search_latest_filing(
                ticker=ticker,
                form_type=form_type,
                query=question,
            )
        )

        metadata = search_result.get("metadata", {})
        chunks = search_result.get("evidence_chunks", [])

        if not chunks:
            return json.dumps(
                {
                    "metadata": metadata,
                    "answer": "No relevant filing evidence was found for this question.",
                    "evidence_chunks": [],
                    "confidence": "low",
                },
                indent=2,
            )

        context = "\n\n".join(
            [
                f"Chunk {chunk.get('chunk_id')}:\n{chunk.get('text')}"
                for chunk in chunks[:5]
            ]
        )

        api_key = os.getenv("OPENAI_API_KEY")

        if not api_key:
            fallback_answer = f"""
            Direct Answer:
            Relevant filing sections were found, but LLM reasoning is not enabled.

            Analyst Interpretation:
            The retrieved evidence should be reviewed to answer the question. The system found filing text related to the query, but without the LLM layer it cannot synthesize a full analyst-style response.

            Evidence Preview:
            {chunks[0].get("text", "")[:1200]}

            Limitation:
            Set OPENAI_API_KEY to enable full research analyst style reasoning.
            """
            return json.dumps(
                {
                    "metadata": metadata,
                    "answer": fallback_answer,
                    "evidence_chunks": chunks,
                    "confidence": "medium",
                },
                indent=2,
            )

        from openai import OpenAI

        client = OpenAI(api_key=api_key)

        prompt = f"""
You are a professional SEC filings research analyst.

Ticker: {ticker}
Filing type: {form_type}
Filing metadata:
{json.dumps(metadata, indent=2)}

User question:
{question}

Relevant filing evidence:
{context}

Answer using ONLY the filing evidence above.

Required format:
1. Direct Answer
2. Evidence From Filing
3. Analyst Interpretation
4. Business Implication
5. Limitations / Uncertainties
6. Follow-up Questions
7. Disclaimer

Rules:
- Do not invent facts.
- If evidence is weak, say so clearly.
- Mention the filing date and accession number if available.
- Keep the tone professional and concise.
"""

        response = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt,
        )

        return json.dumps(
            {
                "metadata": metadata,
                "answer": response.output_text,
                "evidence_chunks": chunks,
                "confidence": "high",
                "source": "SEC filing text + LLM synthesis",
            },
            indent=2,
        )

    except Exception as e:
        return json.dumps(
            {
                "metadata": {
                    "ticker": ticker,
                    "form_type": form_type,
                },
                "answer": f"Tool error: {str(e)}",
                "evidence_chunks": [],
                "confidence": "low",
                "error": str(e),
            },
            indent=2,
        )


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

