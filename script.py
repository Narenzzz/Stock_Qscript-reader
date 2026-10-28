import streamlit as ui_app
import os
from pypdf import PdfReader
from google import genai
from google.genai.errors import APIError

# Set up the Streamlit page configuration
ui_app.set_page_config(
    page_title="Company Con-Call Summarizer",
    page_icon="📈",
    layout="wide"
)

# App Title & Header
ui_app.title("📈 Company Con-Call Summarizer")
ui_app.markdown(
    "Upload a corporate earnings call transcript PDF to get a structured financial summary using Gemini."
)

# Sidebar Configuration for API Key
with ui_app.sidebar:
    ui_app.header("Configuration")
    user_api_key = ui_app.text_input(
        "Enter Gemini API Key (Optional if set in environment)",
        type="password",
        help="If you leave this blank, the app will look for the GEMINI_API_KEY environment variable."
    )

def extract_text_from_pdf(uploaded_file):
    """Reads an uploaded file object and extracts all text content page by page."""
    reader = PdfReader(uploaded_file)
    text_content = []
    
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text_content.append(page_text)
            
    return "\n".join(text_content)

# File Uploader Widget
uploaded_file = ui_app.file_uploader(
    "Choose a conference call PDF file", 
    type=["pdf"]
)

if uploaded_file is not None:
    ui_app.success("File uploaded successfully!")
    
    # Initialize the Gemini Client
    # Priorities: 1. Sidebar input key -> 2. Environment variable key
    api_key_to_use = user_api_key if user_api_key.strip() else os.environ.get("GEMINI_API_KEY")
    
    if not api_key_to_use:
        ui_app.error("API Key Missing! Please enter your Gemini API Key in the sidebar or set it as an environment variable.")
    else:
        # Trigger processing when the user clicks the button
        if ui_app.button("Generate Summary", type="primary"):
            with ui_app.spinner("Extracting text and analyzing transcript with Gemini..."):
                try:
                    # 1. Initialize client with the valid key
                    client = genai.Client(api_key=api_key_to_use)
                    
                    # 2. Extract raw text from the uploaded PDF data
                    transcript_text = extract_text_from_pdf(uploaded_file)
                    
                    # 3. Formulate the financial prompt
                    prompt = f"""
                    You are an expert financial analyst. Analyze the following company earnings conference call transcript and provide a structured summary containing:
                    
                    1. **Executive Summary**: A high-level overview of the quarter/year performance.
                    2. **Key Financial Highlights**: Revenue, margins, guidance, and important metrics.
                    3. **Strategic Initiatives & Operational Updates**: Main updates provided by management.
                    4. **Q&A Insights**: The most critical questions asked by analysts and how management addressed them (risks, tailwinds, headwinds).
                    
                    Transcript content:
                    {transcript_text}
                    """
                    
                    # 4. Request generation using the updated gemini-3.8-flash model
                    response = client.models.generate_content(
                        model='gemini-3.8-flash',
                        contents=prompt,
                    )
                    
                    # 5. Output response to the application surface
                    ui_app.markdown("---")
                    ui_app.subheader("📊 Earnings Call Summary")
                    ui_app.markdown(response.text)
                    
                except APIError as api_err:
                    ui_app.error(f"Gemini API Error: {api_err}")
                except Exception as e:
                    ui_app.error(f"An unexpected error occurred: {e}")
