import streamlit as st
from pypdf import PdfReader
from google import genai
from google.genai.errors import APIError

# Set up the web page title and layout
st.set_page_config(page_title="Earnings Call Summarizer", page_icon="📈", layout="centered")

st.title("📈 Company Con-Call Summarizer")
st.write("Upload a corporate earnings call transcript PDF to get a structured financial summary using Gemini.")

# Sidebar for API key input as a fallback
st.sidebar.header("Configuration")
api_key_input = st.sidebar.text_input("Enter Gemini API Key (Optional if set in environment)", type="password")

# Initialize the Gemini Client
def get_gemini_client():
    # Priority 1: Use the sidebar input if provided
    if api_key_input:
        return genai.Client(api_key=api_key_input)
    
    # Priority 2: Automatically look for GEMINI_API_KEY env variable
    try:
        return genai.Client()
    except Exception:
        return None

# File uploader widget
uploaded_file = st.file_uploader("Choose a conference call PDF file", type="pdf")

if uploaded_file is not None:
    st.success("File uploaded successfully!")
    
    # Action button
    if st.button("Generate Summary", type="primary"):
        client = get_gemini_client()
        
        if client is None:
            st.error("API Key not found. Please set the GEMINI_API_KEY environment variable or enter it in the sidebar.")
        else:
            with st.spinner("Extracting text and analyzing transcript with Gemini..."):
                try:
                    # Read the uploaded PDF file
                    reader = PdfReader(uploaded_file)
                    text_content = []
                    for page in reader.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text_content.append(page_text)
                    
                    full_transcript = "\n".join(text_content)
                    
                    if not full_transcript.strip():
                        st.error("Could not extract text from this PDF. It might be a scanned image or empty.")
                    else:
                        # Construct the prompt
                        prompt = f"""
                        You are an expert financial analyst. Analyze the following company earnings conference call transcript and provide a structured summary containing:
                        
                        1. **Executive Summary**: A high-level overview of the quarter/year performance.
                        2. **Key Financial Highlights**: Revenue, margins, guidance, and important metrics.
                        3. **Strategic Initiatives & Operational Updates**: Main updates provided by management.
                        4. **Q&A Insights**: The most critical questions asked by analysts and how management addressed them (risks, tailwinds, headwinds).
                        
                        Transcript content:
                        {full_transcript}
                        """
                        
                        # Generate the content
                        response = client.models.generate_content(
                            model='gemini-2.5-flash',
                            contents=prompt,
                        )
                        
                        # Display the final summary on the UI
                        st.markdown("---")
                        st.subheader("📋 Earnings Call Summary")
                        st.markdown(response.text)
                        
                except APIError as api_err:
                    st.error(f"Gemini API Error: {api_err}")
                except Exception as e:
                    st.error(f"An unexpected error occurred: {e}")
