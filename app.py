# app.py – Legal Doc Analyzer (user‑typed party, no auto‑detect)
# -----------------------------------------------------------------------------
# Workflow
#   1. User uploads a legal document (PDF, DOCX, or TXT).
#   2. User types the exact name of the party they represent (single text input).
#   3. Click “Analyze” → LLM produces a plain‑English deep‑dive from that
#      party’s perspective.
# -----------------------------------------------------------------------------
# Run:  streamlit run app.py
# -----------------------------------------------------------------------------

import os
import io
from typing import Optional

import streamlit as st
import openai
from PyPDF2 import PdfReader
from docx import Document as DocxDocument

# --------------------------------------------------
# Configuration
# --------------------------------------------------
openai.api_key = os.getenv("OPENAI_API_KEY", st.secrets.get("OPENAI_API_KEY", ""))
MODEL = "gpt-4o-mini"   # Change to preferred model id
MAX_CHARS = 30_000       # Safety truncation for very large files

# --------------------------------------------------
# Helpers – file loader and chat wrapper
# --------------------------------------------------

def load_text(uploaded_file) -> str:
    """Extract raw text (first MAX_CHARS) from PDF/DOCX/TXT."""
    name = uploaded_file.name.lower()
    data = uploaded_file.read()
    if name.endswith(".pdf"):
        reader = PdfReader(io.BytesIO(data))
        text = "\n".join(p.extract_text() or "" for p in reader.pages)
    elif name.endswith(".docx"):
        doc = DocxDocument(io.BytesIO(data))
        text = "\n".join(p.text for p in doc.paragraphs)
    else:
        text = data.decode("utf-8", errors="ignore")
    return text[:MAX_CHARS]


def chat(prompt: str, temperature: float = 0.2) -> str:
    response = openai.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
    )
    return response.choices[0].message.content.strip()

# --------------------------------------------------
# Analysis function
# --------------------------------------------------

def analyze_contract(party: str, doc_text: str) -> str:
    """Call LLM for party‑specific analysis in plain English (markdown)."""
    prompt = f"""
You are legal counsel for **{party}**. Analyze the contract below and respond in clear, plain English.

Structure your answer with these sections:
## Executive Summary (≤3 sentences)
## My Key Obligations & Responsibilities (bullets)
## Key Risks & Red Flags (bullets + why they matter)
## Key Benefits & Protections (bullets)
## Jargon Buster (explain 3–5 key legal terms)
## Questions to Ask (3–5)
---
{doc_text}
"""
    return chat(prompt)

# --------------------------------------------------
# Streamlit UI
# --------------------------------------------------

st.set_page_config(page_title="Legal Doc Analyzer", layout="wide")
st.title("📄 Legal Document Analyzer – Your Perspective")

# Session state keys: doc_text, analysis

uploaded_file = st.file_uploader("Upload PDF, DOCX, or TXT", type=["pdf", "docx", "txt"])

if uploaded_file:
    # Store document text once
    if "doc_text" not in st.session_state:
        with st.spinner("Loading document …"):
            st.session_state.doc_text = load_text(uploaded_file)

    # Party input
    party_name: Optional[str] = st.text_input("Enter the exact name of the party you represent")

    # Analyze button
    if party_name and st.button("⚖️ Analyze from My Perspective"):
        with st.spinner("Generating analysis …"):
            st.session_state.analysis = analyze_contract(party_name.strip(), st.session_state.doc_text)

    # Show analysis if available
    if "analysis" in st.session_state:
        st.markdown(st.session_state.analysis)
        if st.button("🔄 New Document"):
            for key in ("doc_text", "analysis"):
                st.session_state.pop(key, None)
            st.experimental_rerun()
else:
    st.info("⬆️ Upload a legal document to begin.")

st.markdown("---")
st.caption("_Automated analysis – not legal advice. Consult qualified counsel._")
