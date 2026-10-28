import streamlit as st
import httpx
from bs4 import BeautifulSoup
import io
from pypdf import PdfReader
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
You are a ruthless, Warren Buffett & Charlie Munger-style fundamental value investor analyzing an Indian listed company's quarterly Earnings Concall Transcript and Investor Presentation text.
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

# --- HELPER 1: EXTRACT TEXT FROM PDF BYTES ---
def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extracts clean text strings from raw PDF bytes using pypdf."""
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        text = ""
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n"
        return text
    except Exception as e:
        return f"[Error extracting text from PDF: {e}]"

# --- HELPER 2: SCRAPE CONCALL & PPT LINKS FROM SCREENER.IN ---
@st.cache_data(ttl=3600)
def fetch_quarter_documents(ticker: str):
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

# --- HELPER 3: DOWNLOAD PDF BYTES ---
def download_pdf_bytes(url: str) -> bytes | None:
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
    st.header("⚙️ Settings")
    source_mode = st.radio(
        "How to load filings?",
        ["Auto-Fetch by Ticker", "Upload PDF Files Directly"]
    )
    
    custom_focus = st.text_area(
        "🎯 Optional: Specific Question to Check",
        placeholder="e.g., Check management commentary on export margins..."
    )

contents_payload = [SINGLE_QUARTER_PROMPT]
doc_summary_labels = []

# --- MODE 1: AUTO-FETCH ---
if source_mode == "Auto-Fetch by Ticker":
    ticker = st.text_input("Enter NSE Ticker (or BSE Code):", value="TDPOWERSYS").upper()
    
    if ticker:
        quarters = fetch_quarter_documents(ticker)
        if not quarters:
            st.warning("Could not auto-detect concall links for this ticker. Switch to manual upload.")
        else:
            quarter_options = [f"{q['quarter']} ({', '.join(q['links'].keys())})" for q in quarters[:10]]
            selected_idx = st.selectbox("Select Quarter to Analyze:", range(len(quarter_options)), format_func=lambda i: quarter_options[i])
            selected_q = quarters[selected_idx]
            
            if st.button("🚀 Extract & Generate Value Brief", type="primary", use_container_width=True):
                with st.spinner(f"Downloading and extracting text for {ticker} ({selected_q['quarter']})..."):
                    for doc_type, link in selected_q["links"].items():
                        raw_bytes = download_pdf_bytes(link)
                        if raw_bytes:
                            extracted_text = extract_text_from_pdf(raw_bytes)
                            contents_payload.append(f"\n--- {doc_type.upper()} ({selected_q['quarter']}) ---\n{extracted_text}")
                            doc_summary_labels.append(f"{doc_type} ({selected_q['quarter']})")
                        else:
                            st.warning(f"Exchange blocked direct download for {doc_type}. Please use manual upload mode.")

# --- MODE 2: MANUAL UPLOAD ---
else:
    uploaded_files = st.file_uploader(
        "Drop Concall Transcript or PPT PDF files here:",
        type=["pdf"],
        accept_multiple_files=True
    )
    if st.button("🚀 Process Uploaded Files & Analyze", type="primary", use_container_width=True):
        if uploaded_files:
            with st.spinner("Extracting text from uploaded PDFs..."):
                for f in uploaded_files:
                    extracted_text = extract_text_from_pdf(f.read())
                    contents_payload.append(f"\n--- DOCUMENT: {f.name} ---\n{extracted_text}")
                    doc_summary_labels.append(f.name)
        else:
            st.warning("Please upload at least one PDF file.")

# --- EXECUTE GEMINI ANALYSIS & RENDER TABS ---
if len(contents_payload) > 1 and doc_summary_labels:
    if not api_key:
        st.error("Please add `GEMINI_API_KEY` to your Streamlit Secrets or enter it in the sidebar.")
    else:
        with st.spinner(f"Analyzing extracted text from: {', '.join(doc_summary_labels)}..."):
            try:
                client = genai.Client(api_key=api_key)
                
                if custom_focus.strip():
                    contents_payload.append(f"\nADDITIONAL SPECIFIC INVESTOR QUESTION TO ANSWER:\n{custom_focus}")
                
                # Standard text-based generation call (100% stable across all SDK versions)
                response = client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=contents_payload,
                    config=types.GenerateContentConfig(temperature=0.1)
                )
                
                full_report = response.text
                st.success(f"Successfully Analyzed: {', '.join(doc_summary_labels)}")
                
                sections = [s.strip() for s in full_report.split("---") if s.strip()]
                tab_titles = [
                    "📈 1. Growth & Order Book",
                    "🏰 2. Moat & Margins",
                    "💰 3. Capex & Balance Sheet",
                    "🎙️ 4. Concall Q&A Grilling",
                    "⚖️ 5. 60-Sec Verdict",
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
            
            except Exception as e:
                st.error(f"API Execution Error: {e}")
