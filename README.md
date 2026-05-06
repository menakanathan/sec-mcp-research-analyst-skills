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