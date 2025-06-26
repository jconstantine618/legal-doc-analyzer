# app.py – Legal Doc Analyzer (updated prompt)
# -----------------------------------------------------------------------------
# Streamlit agent workflow:
#   1. Upload legal doc (PDF, DOCX, TXT)
#   2. First‑pass neutral summary → detect contract parties
#   3. User selects the side they represent
#   4. Second analysis uses **plain‑English structured prompt** (Executive Summary,
#      Obligations, Risks, Benefits, Jargon Buster, Questions)
# -----------------------------------------------------------------------------
# Run with:  streamlit run app.py
# -----------------------------------------------------------------------------

import os
import io
import json
from typing import Dict, Any

import streamlit as st
import openai
from PyPDF2 import PdfReader
from docx import Document as DocxDocument

# --------------------------------------------------
# Configuration
# --------------------------------------------------
openai.api_key = os.getenv("OPENAI_API_KEY", st.secrets.get("OPENAI_API_KEY", ""))
MODEL_NAME = "gpt-4o-mini"  # change if desired
MAX_CHARS = 30_000           # truncate very large docs for safety

# --------------------------------------------------
# Helpers – load file text
# --------------------------------------------------

def load_file_text(upload) -> str:
    """Return raw text (first MAX_CHARS) from uploaded PDF/DOCX/TXT."""
    name = upload.name.lower()
    data = upload.read()
    if name.endswith(".pdf"):
        reader = PdfReader(io.BytesIO(data))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    elif name.endswith(".docx"):
        doc = DocxDocument(io.BytesIO(data))
        text = "\n".join(p.text for p in doc.paragraphs)
    else:
        text = data.decode("utf-8", errors="ignore")
    return text[:MAX_CHARS]

# --------------------------------------------------
# Helpers – OpenAI chat wrappers
# --------------------------------------------------

def _chat(prompt: str) -> str:
    """One‑shot chat completion wrapper."""
    response = openai.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    return response.choices[0].message.content.strip()


def first_pass_analysis(doc_text: str) -> Dict[str, Any]:
    """Return {summary, parties} after a neutral scan."""
    prompt = f"""
You are a neutral legal analyst. Review the contract below and:
1. Give an executive summary (≤200 words).
2. List the primary parties exactly as they appear.
Return **valid JSON only** with keys `summary` and `parties`.
---
CONTRACT:\n\n{doc_text}
"""
    raw = _chat(prompt)
    try:
        data = json.loads(raw)
        parties = [p.strip() for p in data.get("parties", []) if p.strip()]
        if not parties:
            parties = ["Party A", "Party B"]
        return {"summary": data.get("summary", ""), "parties": parties}
    except json.JSONDecodeError:
        return {"summary": raw, "parties": ["Party A", "Party B"]}


def side_focused_analysis(party: str, doc_text: str) -> str:
    """Plain‑English, structured analysis from the chosen party's perspective."""
    prompt = f"""
Please analyze the attached document from the perspective of **{party}** and provide a detailed breakdown. **Use simple, clear, plain English**—assume I have no legal background.

Structure your response with the following markdown sections:

## Executive Summary  
*(≤3 sentences)* – What is the main goal of this document and its primary impact on me?

## My Key Obligations & Responsibilities  
• Bulleted list of all actions I must take, promises I'm making, responsibilities I'm accepting – note any deadlines.

## Key Risks & Red Flags  
• Bulleted list of the most significant risks for me. Highlight any unusual, one‑sided, ambiguous, or problematic clauses and explain *why* each is risky.

## Key Benefits & Protections  
• Bulleted list of clauses that clearly protect my interests or provide benefits.

## Jargon Buster  
Explain the 3–5 most important or confusing legal terms (e.g., "Indemnification", "Governing Law", "Limitation of Liability") in very practical, simple language.

## Questions to Ask  
List 3–5 critical questions I should ask the other party for clarification or negotiation before signing.

Respond in markdown using bullet points where called for.
---
CONTRACT TEXT:\n\n{doc_text}
"""
    return _chat(prompt)

# --------------------------------------------------
# Streamlit UI
# --------------------------------------------------

st.set_page_config(page_title="Legal Doc Analyzer", layout="wide")
st.title("📄 Legal Document Analyzer (Plain‑English Edition)")

if "stage" not in st.session_state:
    st.session_state.stage = 0  # 0: need upload, 1: first pass, 2: side analysis

upload = st.file_uploader("Upload PDF, DOCX, or TXT", type=["pdf", "docx", "txt"])

if upload:
    text = load_file_text(upload)
    st.success(f"Loaded **{upload.name}**")
    st.write("Preview (first 1 000 chars):")
    st.code(text[:1000] + ("…" if len(text) > 1000 else ""), language="text")

    if st.session_state.stage == 0:
        if st.button("🔍 First‑Pass Analysis" , disabled=(openai.api_key == "")):
            with st.spinner("Running first pass…"):
                data = first_pass_analysis(text)
            st.session_state.summary = data["summary"]
            st.session_state.parties = data["parties"]
            st.session_state.doc_text = text
            st.session_state.stage = 1
            st.experimental_rerun()

    elif st.session_state.stage == 1:
        st.markdown("## 📝 Executive Summary (Neutral)")
        st.markdown(st.session_state.summary)
        side = st.selectbox("Pick the side you represent", st.session_state.parties)
        if st.button("⚖️ Deep Dive for My Side"):
            with st.spinner("Analyzing from your side…"):
                md = side_focused_analysis(side, st.session_state.doc_text)
            st.session_state.side_md = md
            st.session_state.stage = 2
            st.experimental_rerun()

    elif st.session_state.stage == 2:
        st.markdown(st.session_state.side_md)
        if st.button("🔁 Analyze New Document"):
            st.session_state.clear()
            st.session_state.stage = 0
            st.experimental_rerun()
else:
    st.info("⬆️ Upload a legal document to get started.")

st.markdown("---")
st.caption("_Automated analysis – not legal advice. Always consult qualified counsel._")
