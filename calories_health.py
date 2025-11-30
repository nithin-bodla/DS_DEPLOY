# app.py
from dotenv import load_dotenv
load_dotenv()  # local development only; .env must be in .gitignore

import os
import requests
import streamlit as st
from PIL import Image
import google.generativeai as genai
from google.api_core.exceptions import InvalidArgument, ResourceExhausted, GoogleAPIError

# --- Configuration / keys ---
GOOGLE_API_KEY = None
try:
    GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
except Exception:
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

CALORIE_NINJAS_KEY = None
try:
    CALORIE_NINJAS_KEY = st.secrets["CALORIE_NINJAS_KEY"]
except Exception:
    CALORIE_NINJAS_KEY = os.getenv("CALORIE_NINJAS_KEY")

# Optional configure for genai client (no-op for some SDK versions)
try:
    if GOOGLE_API_KEY:
        genai.configure(api_key=GOOGLE_API_KEY)
except Exception:
    pass

if not GOOGLE_API_KEY:
    st.error("""
❌ No Google API key found.

Fix:
- Local run: Add GOOGLE_API_KEY to your .env file or export it in terminal
- Streamlit Cloud: Add GOOGLE_API_KEY in project Secrets
""")
    st.stop()

# --- Helpers ---
def get_gemini_response(prompt_text, image_parts, user_text):
    """
    Call Gemini and return a text response.
    image_parts should be a list-of-dict prepared by input_image_setup (or None).
    user_text is optional extra context passed before the prompt.
    """
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content([user_text, image_parts[0] if image_parts else None, prompt_text])
        return getattr(response, "text", str(response))
    except InvalidArgument as e:
        if "API key expired" in str(e) or "API_KEY_INVALID" in str(e):
            return "⚠️ Your Google API key is invalid or expired. Renew it in Google AI Studio."
        return f"❌ Invalid argument: {e}"
    except ResourceExhausted:
        return "🚫 Google API quota exceeded. Try again later."
    except GoogleAPIError as e:
        return f"❗ Google API error: {e}"
    except Exception as e:
        return f"💥 Unexpected error: {e}"

def input_image_setup(uploaded_file):
    if uploaded_file is None:
        return None
    try:
        bytes_data = uploaded_file.getvalue()
        image_parts = [
            {
                "mime_type": uploaded_file.type,
                "data": bytes_data
            }
        ]
        return image_parts
    except Exception as e:
        st.warning(f"Unable to prepare image for upload: {e}")
        return None

@st.cache_data(show_spinner=False)
def lookup_calories_calorieninjas(free_text: str):
    """
    Query CalorieNinjas and return readable string. Cached in session.
    """
    if not CALORIE_NINJAS_KEY:
        return "Calorie lookup unavailable: CALORIE_NINJAS_KEY not set."

    url = "https://api.calorieninjas.com/v1/nutrition"
    headers = {"X-Api-Key": CALORIE_NINJAS_KEY}
    params = {"query": free_text}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=8)
        r.raise_for_status()
        data = r.json()
        items = data.get("items", [])
        if not items:
            return "No nutrition data found for that query."

        lines = []
        total_cal = 0
        for item in items:
            name = item.get("name", "item")
            cal = item.get("calories", 0)
            serving = item.get("serving_size", "")
            if serving:
                lines.append(f"{name} ({serving}) — {cal} kcal")
            else:
                lines.append(f"{name} — {cal} kcal")
            total_cal += cal
        lines.append("----")
        lines.append(f"Estimated total: {total_cal} kcal")
        return "\n".join(lines)
    except requests.exceptions.RequestException as e:
        return f"Error calling CalorieNinjas: {e}"
    except Exception as e:
        return f"Unexpected error in calorie lookup: {e}"

# --- UI ---
st.set_page_config(page_title="Nutrition Analyzer", layout="wide")
st.title("🍽️ Nutrition Analyzer — single input (text + optional image)")

st.markdown(
    "Use the single textbox below for either: dish name, short ingredient list, or extra context for image analysis. "
    "Upload an image optionally. Then click **Analyze**."
)

# Unified single text input (used for both text lookup and Gemini context)
unified_input = st.text_input(
    "Type a dish name, short ingredients, or extra context (e.g. 'lunch: rice, chicken curry, salad')",
    key="unified_input"
)

# Optional image uploader
uploaded_file = st.file_uploader("Upload an image of the meal (optional)", type=["jpg", "jpeg", "png"])
if uploaded_file:
    try:
        display_image = Image.open(uploaded_file)
        st.image(display_image, caption="Uploaded image", use_container_width=True)
    except Exception:
        st.warning("Unable to open the uploaded image for preview.")

# One analyze button
analyze = st.button("Analyze")

# Prompt used by Gemini (image analysis). You can edit this wording.
input_prompt = """You are an expert nutritionist. Look at the image and identify each food item,
estimate its calories, and list results in this format:

1. Item 1 - number of calories
2. Item 2 - number of calories
----
Also provide short notes about portion size assumptions you used.
"""

# Handle Analyze click
if analyze:
    if uploaded_file is None and (not unified_input or not unified_input.strip()):
        st.error("Please upload an image or type a dish/ingredients (or both).")
    else:
        # Side-by-side columns for results
        col_img, col_text = st.columns(2)

        # GEMINI IMAGE ANALYSIS
        with col_img:
            st.subheader("Image analysis (Gemini)")
            if uploaded_file is None:
                st.info("No image provided. Upload an image to run Gemini-based analysis.")
            else:
                image_parts = input_image_setup(uploaded_file)
                if image_parts is None:
                    st.warning("Could not prepare the image for analysis.")
                else:
                    with st.spinner("Analyzing image with Gemini…"):
                        # Pass unified_input as user_text (extra context) to Gemini
                        gemini_result = get_gemini_response(input_prompt, image_parts, unified_input or "")
                    st.write(gemini_result)

        # TEXT LOOKUP (CalorieNinjas)
        with col_text:
            st.subheader("Quick text lookup (CalorieNinjas)")
            if not unified_input or not unified_input.strip():
                if not CALORIE_NINJAS_KEY:
                    st.info("CalorieNinjas key not set. Add CALORIE_NINJAS_KEY to secrets or .env to enable text lookup.")
                else:
                    st.info("Type a dish or short ingredient list above to run a quick text lookup.")
            else:
                with st.spinner("Fetching quick text lookup..."):
                    text_lookup = lookup_calories_calorieninjas(unified_input)
                st.text(text_lookup)

# Footer tips
st.markdown("---")
st.markdown(
    "- Tip: Give both an image and a short text (e.g., 'lunch: rice, chicken curry') for best cross-check accuracy.\n"
    "- The single textbox is used for both the quick text lookup and as optional context for the image analysis.\n"
)
