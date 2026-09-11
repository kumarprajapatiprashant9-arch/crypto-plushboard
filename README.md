# crypto-plushboard
A Streamlit cryptocurrency dashboard powered by the CoinGecko API.

## Features

- Live cryptocurrency market data
- Total market capitalization
- 24-hour trading volume
- Bitcoin dominance
- 1-hour, 24-hour, and 7-day changes
- Searchable market table
- Coin selection
- Seven-day price chart
- Top movers section
- Automatic refresh every 60 seconds
- Responsive Streamlit layout

## Run Locally

### Windows PowerShell

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

### macOS/Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Open the local URL shown in the terminal, usually:

```text
http://localhost:8501
```
