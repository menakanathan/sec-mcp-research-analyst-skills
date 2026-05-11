# SEC GenAI MCP Agent

## Concepts
- MCP tools
- Autonomous LLM agent
- SKILLS.md
- Streamlit UI

## Run

python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
streamlit run app.py

## After any changes
source venv/bin/activate
pip install matplotlib pandas
python -m streamlit run app.py

GenAI research analyst with MCP server tools that:

Reads available capabilities from SKILLS.md
Lets the LLM or fallback logic select an MCP tool
Validates that the selected tool exists in the MCP server
Falls back safely if the selected tool is unavailable
Executes SEC filing or financial analytics tools
Generates a final analyst-style answer
Displays raw tool output for transparency

The KPI Dashboard derives values from SEC Company Facts XBRL filings using standardized US-GAAP concepts. 
The system filters for annual 10-K fiscal-year records and computes YoY changes using consistent concepts and units. 
This approach prioritizes filed accounting accuracy over third-party normalized market datasets such as yfinance.

Debugging
source venv/bin/activate
python financials.py


RAG Demo
1. Select ticker: MSFT
2. Filing type: 10-K
3. Click Build RAG Index
4. Ask: What does the company say about AI infrastructure investment?
5. Show retrieved chunks and similarity scores
6. Show analyst answer generated only from retrieved context


Layer	                File
UI	                    app.py
Agent reasoning	        agent.py
Skill guidance	        SKILLS.md
Tool infrastructure	    server.py
Structured analytics	financials.py
RAG retrieval	        rag_utils.py
LLM grounded synthesis	llm-reasoner.py
Validation/evaluation	evaluation.py
