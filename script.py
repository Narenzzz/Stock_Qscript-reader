import streamlit as ui_app
import os
import time
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

def generate_with_retry(client, model_name, prompt, max_retries=3):
    """Attempts to generate content, retrying with exponential backoff if a 503 error occurs."""
    delay = 2  # Starting delay in seconds
    
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
            )
            return response
        except APIError as api_err:
            # If it's a 503 server error or high-demand message, retry
            is_503 = (api_err.code == 503) or ("high demand" in str(api_err).lower())
            
            if is_503 and attempt < max_retries - 1:
                ui_app.warning(f"Gemini is busy (Attempt {attempt + 1}/{max_retries}). Retrying in {delay} seconds...")
                time.sleep(delay)
                delay *= 2  # Double the wait time for the next loop
            else:
                # Re-raise the error if max retries reached or it's a different error code (like 404 or 400)
                raise api_err

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
                    
                    # 4. Attempt generation using primary flash model with automatic retries
                    try:
                        ui_app.info("Sending request to Gemini 3.8 Flash...")
                        response = generate_with_retry(client, 'gemini-3.8-flash', prompt)
                    except APIError as api_err:
                        # Fallback step if the primary model fails all retries due to server capacity limits
                        is_server_error = (api_err.code == 503) or ("high demand" in str(api_err).lower())
                        if is_server_error:
                            ui_app.warning("Gemini 3.8 Flash is completely saturated. Falling back to alternative model tier...")
                            # Attempt with the robust backup model tier
                            response = generate_with_retry(client, 'gemini-2.5-pro', prompt)
                        else:
                            raise api_err
                    
                    # 5. Output response to the application surface
                    ui_app.markdown("---")
                    ui_app.subheader("📊 Earnings Call Summary")
                    ui_app.markdown(response.text)
                    
                except APIError as api_err:
                    ui_app.error(f"Gemini API Error: {api_err}")
                except Exception as e:
                    ui_app.error(f"An unexpected error occurred: {e}")
