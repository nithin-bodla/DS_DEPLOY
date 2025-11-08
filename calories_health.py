# app.py
from dotenv import load_dotenv
load_dotenv()  # local development only; .env must be in .gitignore

import os
import streamlit as st
from PIL import Image
import google.generativeai as genai
from google.api_core.exceptions import InvalidArgument, ResourceExhausted, GoogleAPIError

# Prefer Streamlit secrets in deployment; fallback to environment variable for local dev

API_KEY = None
try:
    # Try Streamlit Cloud secrets
    API_KEY = st.secrets["GOOGLE_API_KEY"]
except Exception:
    # Fallback for local machine (.env or exported variable)
    API_KEY = os.getenv("GOOGLE_API_KEY")

if not API_KEY:
    st.error("""
❌ No API key found.

Fix:
- Local run: Add GOOGLE_API_KEY to your .env file or export it in terminal
- Streamlit Cloud: Add GOOGLE_API_KEY in project Secrets
""")
    st.stop()


def get_gemini_response(prompt_text, image_parts, user_text):
    """
    Call Gemini and return text response. image_parts is the list-of-dict
    prepared by input_image_setup (or None if not used).
    """
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        # The order/content you send depends on your prompt design.
        # Here we pass: user_text, first image part, prompt_text
        response = model.generate_content([user_text, image_parts[0] if image_parts else None, prompt_text])
        # The response structure may differ; check the exact property name in your library version
        return getattr(response, "text", str(response))
    except InvalidArgument as e:
        # Typical message for expired key: "API key expired. Please renew the API key."
        if "API key expired" in str(e) or "API_KEY_INVALID" in str(e):
            return "⚠️ Your API key is invalid or expired. Renew it in Google AI Studio."
        return f"❌ Invalid argument: {e}"
    except ResourceExhausted as e:
        return "🚫 Quota exceeded. Please wait and try again later."
    except GoogleAPIError as e:
        return f"❗ Google API error: {e}"
    except Exception as e:
        return f"💥 Unexpected error: {e}"

def input_image_setup(uploaded_file):
    """
    Convert uploaded file (Streamlit Upload) into the image_parts structure
    expected by your use of Gemini images.
    """
    if uploaded_file is None:
        return None
    bytes_data = uploaded_file.getvalue()
    image_parts = [
        {
            "mime_type": uploaded_file.type,
            "data": bytes_data
        }
    ]
    return image_parts

# --- Streamlit UI ---
st.set_page_config(page_title="Gemini Image Demo")
st.title("🍽️ Nutrition Image Analyzer (Gemini)")

user_input = st.text_input("Add any extra instructions or context (optional):", key="user_input")

uploaded_file = st.file_uploader("Upload an image of food", type=["jpg", "jpeg", "png"])
if uploaded_file:
    try:
        display_image = Image.open(uploaded_file)
        st.image(display_image, caption="Uploaded image", use_container_width=True)
    except Exception:
        st.warning("Unable to open the uploaded image for preview.")

submit = st.button("Analyze image and estimate calories")

# Prompt template (you can change wording)
input_prompt = """You are an expert nutritionist. Look at the image and identify each food item,
estimate its calories, and list results in this format:

1. Item 1 - number of calories
2. Item 2 - number of calories
----
Also provide short notes about portion size assumptions you used.
"""

if submit:
    if uploaded_file is None:
        st.error("Please upload an image first.")
    else:
        image_parts = input_image_setup(uploaded_file)
        with st.spinner("Analyzing image with Gemini…"):
            response_text = get_gemini_response(input_prompt, image_parts, user_input)
        st.subheader("Result")
        st.write(response_text)
