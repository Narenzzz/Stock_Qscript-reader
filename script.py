import streamlit as st
import httpx
from bs4 import BeautifulSoup
from google import genai
from google.genai import types

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="Concall & PPT Value Extractor",
    page_icon="📑",
    layout="wide"
)

st.title("📑 Earnings Presentation & Concall Value Extractor")
st.caption("Zero-fluff fundamental analysis & multi-quarter 'Say-Do' management audit.")

# --- SAFE API KEY LOADER ---
try:
    api_key = st.secrets["GEMINI_API_KEY"]
except Exception:
    api_key = None

if not api_key:
    with st.sidebar:
        api_key = st.text_input("🔑 Enter Gemini API Key:", type="password")

# --- PROMPT 1: SINGLE QUARTER DEEP-DIVE ---
SINGLE_QUARTER_PROMPT = """
You are a ruthless, Warren Buffett & Charlie Munger-style fundamental value investor analyzing an Indian listed company's quarterly Investor Presentation (PPT) and Earnings Concall Transcript.
Ignore corporate PR fluff, fancy graphics, and macro excuses. Extract ONLY hard numbers, structural business updates, and high-signal insights.

Format your output strictly using the following 5 Markdown sections separated by exact horizontal rules (---):

## 1. Core Business & Growth Quality
- **Headline Numbers:** Revenue, EBITDA, and PAT growth (YoY and QoQ).
- **Volume vs. Price Mix:** Explicitly state whether revenue growth came from real volume expansion, price hikes, or product mix shift.
- **Order Book & Visibility:** Current order book size, new inflows this quarter, execution timeline, and export vs. domestic split (if applicable).

---

## 2. Moat, Margins & Pricing Power
- **Margin Drivers:** Gross Margin and Operating (EBITDA) Margin movement (bps change YoY/QoQ) and the exact reasons.
- **Pricing Power Test:** Is the company able to pass on raw material/freight inflation to customers immediately, or is there a lag? Are competitors forcing price cuts?
- **Operating Leverage:** Are fixed costs scaling down as a % of revenue?

---

## 3. Capital Allocation & Balance Sheet Health
- **Capex & Capacity:** Ongoing capex projects, commissioning timelines, current capacity utilization (%), and expected peak revenue/asset turnover from new capex.
- **Working Capital & Cash Flow:** Any red flags in trade receivables (debtor days), inventory pile-up, cash conversion, or debt levels.

---

## 4. Concall Q&A Grilling & Management Candor
- **Top 3 Toughest Analyst Questions:** Summarize the hardest questions asked during the Q&A and evaluate whether management gave direct, number-backed answers or dodged them.
- **Forward Guidance:** What specific numerical targets or timelines did management commit to for the next 1-2 years?

---

## 5. The 60-Second Value Investor Verdict
- **The Bull Case (What's Working):** 3-4 crisp, fact-backed points.
- **The Bear Case / Key Risks:** 3-4 crisp, fact-backed points to watch in upcoming quarters.
- **Moat Direction:** Is the competitive moat widening, stable, or narrowing based on this quarter's execution?
"""

# --- PROMPT 2: MULTI-QUARTER "SAY-DO" AUDIT ---
SAY_DO_AUDIT_PROMPT = """
You are a forensic fundamental value investor conducting a multi-quarter "Say-Do Ratio" Audit on an Indian listed company.
You have been provided with filings from an EARLIER QUARTER (Baseline) and a LATER QUARTER (Current).
Your job is to test management integrity, execution capability, and guidance accuracy.

Format your output strictly using the following 5 Markdown sections separated by exact horizontal rules (---):

## 1. The "Say-Do" Scorecard (Promises vs. Reality)
- Create a Markdown comparison table with columns: `Metric / Project`, `What Management Promised in Earlier Quarter`, `Actual Delivery in Later Quarter`, and `Verdict (Beat / Met / Missed / Quietly Dropped)`.
- Cover revenue growth guidance, EBITDA margin targets, order book inflows, and new product/export launches.

---

## 2. Capex & Project Execution Audit
- **Timeline Slippage Check:** Did new plants, capacity expansions, or commissioning dates happen on time as promised in the earlier quarter, or were they delayed?
- **Capacity Utilization & ROI:** How has capacity utilization and revenue contribution progressed across the two periods?

---

## 3. Narrative Shift & Goalpost Moving
- **The Excuse Detector:** Did management blame macro headwinds, elections, monsoons, or raw material prices for missing earlier targets?
- **Omission Check:** What topics or growth triggers was management excitedly boasting about in the earlier quarter that they completely stopped talking about in the later quarter?

---

## 4. Structural Business Trajectory (Then vs. Now)
- **Moat & Margin Evolution:** Compare Gross/EBITDA margins, pricing power, and working capital health between the two quarters. Is the underlying business stronger or weaker today?
- **Order Book / Demand Trajectory:** How has customer demand visibility evolved between the two periods?

---

## 5. Management Integrity & Capital Allocator Rating
- **Credibility Score (Out of 10):** Rate management's candor and execution reliability with clear justification.
- **Conservative vs. Promotional:** Does this management team under-promise and over-deliver, or do they consistently paint rosy pictures and shift goalposts?
"""

# --- HELPER 1: SCRAPE CONCALL & PPT LINKS FROM SCREENER.IN ---
@st.cache_data(ttl=3600)
def fetch_quarter_documents(ticker: str):
    """Fetches available Concall Transcripts and PPT PDF links from Screener.in"""
    ticker = ticker.strip().upper()
    url = f"https://www.screener.in/company/{ticker}/consolidated/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }
    
    with httpx.Client(headers=headers, follow_redirects=True, timeout=20.0) as client:
        resp = client.get(url)
        if resp.status_code != 200:
            url = f"https://www.screener.in/company/{ticker}/"
            resp = client.get(url)
            if resp.status_code != 200:
                return []

    soup = BeautifulSoup(resp.text, "html.parser")
    concalls_div = soup.find("div", class_="concalls")
    if not concalls_div:
        return []

    quarters_data = []
    for li in concalls_div.find_all("li"):
        date_el = li.find("div", class_="ink-600") or li.find("span")
        quarter_label = date_el.get_text(strip=True) if date_el else "Recent Quarter"
        
        links = {}
        for a in li.find_all("a", href=True):
            link_text = a.get_text(strip=True).lower()
            if "transcript" in link_text:
                links["Transcript"] = a["href"]
            elif "ppt" in link_text or "presentation" in link_text:
                links["PPT"] = a["href"]
                
        if links:
            quarters_data.append({"quarter": quarter_label, "links": links})
            
    return quarters_data

# --- HELPER 2: DOWNLOAD PDF INTO MEMORY ---
def download_pdf_bytes(url: str) -> bytes | None:
    """Downloads PDF from BSE/NSE/Company link with proper headers."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/pdf,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": "https://www.bseindia.com/"
    }
    try:
        with httpx.Client(headers=headers, follow_redirects=True, timeout=30.0) as client:
            resp = client.get(url)
            if resp.status_code == 200 and b"%PDF" in resp.content[:1024]:
                return resp.content
    except Exception:
        return None
    return None

# --- SIDEBAR CONTROLS ---
with st.sidebar:
    st.header("⚙️ 1. Analysis Mode")
    analysis_type = st.radio(
        "Select Research Workflow:",
        [
            "Single Quarter Deep-Dive",
            "Multi-Quarter 'Say-Do' Audit (Compare 2 Quarters)"
        ]
    )
    
    st.header("📥 2. Document Source")
    source_mode = st.radio(
        "How to load filings?",
        ["Auto-Fetch by Ticker", "Upload PDFs / Paste URLs"]
    )
    
    custom_focus = st.text_area(
        "🎯 Optional: Specific Question to Check",
        placeholder="e.g., Check if they hit their 20% export growth guidance or check capex commissioning..."
    )

contents_payload = []
doc_summary_labels = []

# --- SOURCE MODE 1: AUTO-FETCH BY TICKER ---
if source_mode == "Auto-Fetch by Ticker":
    ticker = st.text_input("Enter NSE Ticker (or BSE Code):", value="TDPOWERSYS").upper()
    
    if ticker:
        quarters = fetch_quarter_documents(ticker)
        if not quarters:
            st.warning("Could not auto-detect concall links for this ticker. Switch to 'Upload PDFs / Paste URLs' in the sidebar.")
        else:
            quarter_options = [
                f"{q['quarter']} ({', '.join(q['links'].keys())})"
                for q in quarters[:12]
            ]
            
            if analysis_type == "Single Quarter Deep-Dive":
                selected_idx = st.selectbox(
                    "Select Quarter to Analyze:",
                    range(len(quarter_options)),
                    format_func=lambda i: quarter_options[i]
                )
                selected_q = quarters[selected_idx]
                
                st.markdown(
                    "**Detected Filings:** " + 
                    " | ".join([f"[📄 {k}]({v})" for k, v in selected_q["links"].items()])
                )
                
                if st.button("🚀 Generate Single-Quarter Value Brief", type="primary", use_container_width=True):
                    contents_payload.append(SINGLE_QUARTER_PROMPT)
                    with st.spinner(f"Downloading filings for {ticker} ({selected_q['quarter']})..."):
                        for doc_type, link in selected_q["links"].items():
                            raw_bytes = download_pdf_bytes(link)
                            if raw_bytes:
                                contents_payload.append(f"DOCUMENT: {doc_type} for {selected_q['quarter']}")
                                contents_payload.append(types.Part.from_bytes(data=raw_bytes, mime_type="application/pdf"))
                                doc_summary_labels.append(f"{doc_type} ({selected_q['quarter']})")
                            else:
                                st.error(f"Exchange firewall blocked direct download of {doc_type} ({selected_q['quarter']}). Download via the [Direct Link]({link}) and use Upload mode.")

            else:
                col1, col2 = st.columns(2)
                with col1:
                    default_past = min(4, len(quarter_options) - 1)
                    past_idx = st.selectbox(
                        "⏪ 1. Select EARLIER Quarter (Baseline Promises):",
                        range(len(quarter_options)),
                        index=default_past,
                        format_func=lambda i: quarter_options[i]
                    )
                    past_q = quarters[past_idx]
                    st.markdown(
                        "**Earlier Filings:** " + 
                        " | ".join([f"[📄 {k}]({v})" for k, v in past_q["links"].items()])
                    )
                with col2:
                    latest_idx = st.selectbox(
                        "⏩ 2. Select LATER Quarter (Actual Delivery):",
                        range(len(quarter_options)),
                        index=0,
                        format_func=lambda i: quarter_options[i]
                    )
                    latest_q = quarters[latest_idx]
                    st.markdown(
                        "**Later Filings:** " + 
                        " | ".join([f"[📄 {k}]({v})" for k, v in latest_q["links"].items()])
                    )

                if st.button("⚖️ Run Multi-Quarter 'Say-Do' Management Audit", type="primary", use_container_width=True):
                    contents_payload.append(SAY_DO_AUDIT_PROMPT)
                    with st.spinner(f"Downloading filings for {past_q['quarter']} and {latest_q['quarter']}..."):
                        for doc_type, link in past_q["links"].items():
                            raw_bytes = download_pdf_bytes(link)
                            if raw_bytes:
                                contents_payload.append(
                                    f"EARLIER BASELINE QUARTER ({past_q['quarter']}) - {doc_type}:"
                                )
                                contents_payload.append(types.Part.from_bytes(data=raw_bytes, mime_type="application/pdf"))
                                doc_summary_labels.append(f"{doc_type} ({past_q['quarter']})")
                            else:
                                st.error(f"Blocked download for {doc_type} ({past_q['quarter']}).")
                        
                        for doc_type, link in latest_q["links"].items():
                            raw_bytes = download_pdf_bytes(link)
                            if raw_bytes:
                                contents_payload.append(
                                    f"LATER DELIVERY QUARTER ({latest_q['quarter']}) - {doc_type}:"
                                )
                                contents_payload.append(types.Part.from_bytes(data=raw_bytes, mime_type="application/pdf"))
                                doc_summary_labels.append(f"{doc_type} ({latest_q['quarter']})")
                            else:
                                st.error(f"Blocked download for {doc_type} ({latest_q['quarter']}).")

# --- SOURCE MODE 2: MANUAL UPLOAD ---
else:
    if analysis_type == "Single Quarter Deep-Dive":
        uploaded_files = st.file_uploader(
            "Drop Investor Presentation & Concall Transcript PDFs here:",
            type=["pdf"],
            accept_multiple_files=True
        )
        if st.button("🚀 Analyze Uploaded Documents", type="primary"):
            contents_payload.append(SINGLE_QUARTER_PROMPT)
            for f in uploaded_files:
                contents_payload.append(f"DOCUMENT: {f.name}")
                contents_payload.append(types.Part.from_bytes(data=f.read(), mime_type="application/pdf"))
                doc_summary_labels.append(f.name)
    else:
        col1, col2 = st.columns(2)
        with col1:
            past_files = st.file_uploader(
                "⏪ Drop EARLIER Quarter PDFs (Promises):",
                type=["pdf"],
                accept_multiple_files=True,
                key="past_up"
            )
        with col2:
            latest_files = st.file_uploader(
                "⏩ Drop LATER Quarter PDFs (Actual Delivery):",
                type=["pdf"],
                accept_multiple_files=True,
                key="latest_up"
            )
        if st.button("⚖️ Run Multi-Quarter 'Say-Do' Audit", type="primary"):
            contents_payload.append(SAY_DO_AUDIT_PROMPT)
            for f in past_files:
                contents_payload.append(f"EARLIER BASELINE QUARTER DOCUMENT ({f.name}):")
                contents_payload.append(types.Part.from_bytes(data=f.read(), mime_type="application/pdf"))
                doc_summary_labels.append(f"Earlier: {f.name}")
            for f in latest_files:
                contents_payload.append(f"LATER DELIVERY QUARTER DOCUMENT ({f.name}):")
                contents_payload.append(types.Part.from_bytes(data=f.read(), mime_type="application/pdf"))
                doc_summary_labels.append(f"Later: {f.name}")

# --- EXECUTE GEMINI ANALYSIS & RENDER TABS ---
if len(contents_payload) > 1 and doc_summary_labels:
    if not api_key:
        st.error("Please add `GEMINI_API_KEY` to your Streamlit Secrets or enter it in the sidebar.")
    else:
        with st.spinner(f"Reading & cross-examining {len(doc_summary_labels)} filing(s): {', '.join(doc_summary_labels)}..."):
            # Explicitly initialize the client with the api_key variable
            client = genai.Client(api_key=api_key)
            
            if custom_focus.strip():
                contents_payload.append(f"\nADDITIONAL SPECIFIC INVESTOR QUESTION TO ANSWER:\n{custom_focus}")
                
            response = client.models.generate_content(
                model="gemini-3.5-flash",  # Updated to stable gemini-3.5-flash model
                contents=contents_payload,
                config=types.GenerateContentConfig(temperature=0.1)
            )
            
            full_report = response.text
            st.success(f"Completed! Analyzed: {', '.join(doc_summary_labels)}")
            
            sections = [s.strip() for s in full_report.split("---") if s.strip()]
            
            if analysis_type == "Single Quarter Deep-Dive":
                tab_titles = [
                    "📈 1. Growth & Order Book",
                    "🏰 2. Moat & Margins",
                    "💰 3. Capex & Balance Sheet",
                    "🎙️ 4. Concall Q&A Grilling",
                    "⚖️ 5. 60-Sec Verdict",
                    "📝 Full Markdown Report"
                ]
            else:
                tab_titles = [
                    "🎯 1. Say-Do Scorecard",
                    "🏗️ 2. Capex Execution Audit",
                    "🚩 3. Goalpost Moving Check",
                    "📊 4. Business Trajectory",
                    "🏅 5. Integrity Rating",
                    "📝 Full Markdown Report"
                ]

            if len(sections) >= 5:
                tabs = st.tabs(tab_titles)
                for i in range(5):
                    with tabs[i]:
                        st.markdown(sections[i])
                with tabs[5]:
                    st.markdown(full_report)
                    st.download_button(
                        "⬇️ Download Research Note (.md)",
                        data=full_report,
                        file_name="value_investor_concall_note.md",
                        mime="text/markdown"
                    )
            else:
                st.markdown(full_report)
                st.download_button(
                    "⬇️ Download Research Note (.md)",
                    data=full_report,
                    file_name="value_investor_concall_note.md",
                    mime="text/markdown"
                )
