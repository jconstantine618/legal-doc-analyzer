# app.py – Legal Doc Analyzer (plain-English, party selector fixed)
# -----------------------------------------------------------------------------
# Streamlit workflow
#   1. Upload legal doc (PDF, DOCX, TXT)
#   2. First-pass neutral summary + detect parties
#   3. User chooses the side they represent from a dropdown
#   4. Deep-dive analysis tailored to that side (plain English)
# -----------------------------------------------------------------------------
# Run:  streamlit run app.py
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
# Helper – file loader
# --------------------------------------------------

def load_file_text(upload) -> str:
    """Extract raw text (first MAX_CHARS) from uploaded PDF/DOCX/TXT."""
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
# OpenAI chat helpers
# --------------------------------------------------

def _chat(prompt: str) -> str:
    """Light wrapper around a single chat completion."""
    response = openai.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    return response.choices[0].message.content.strip()


def first_pass_analysis(doc_text: str) -> Dict[str, Any]:
    """Return neutral exec summary + detected parties."""
    prompt = f"""
You are a neutral legal analyst. Read the contract below and:
1. Give an executive summary (≤200 words).
2. List the primary parties exactly as they appear.
Respond ONLY in valid JSON of the form {{"summary": "…", "parties": ["…", …]}}.
---
CONTRACT:\n\n{doc_text}
"""
    raw = _chat(prompt)
    try:
        data = json.loads(raw)
        parties = [p.strip() for p in data.get("parties", []) if p.strip()] or ["Party A", "Party B"]
        return {"summary": data.get("summary", ""), "parties": parties}
    except json.JSONDecodeError:
        # If the LLM failed JSON format, fall back gracefully
        return {"summary": raw, "parties": ["Party A", "Party B"]}


def side_focused_analysis(party: str, doc_text: str) -> str:
    """Return structured markdown analysis from *party* perspective."""
    prompt = f"""
Please analyze the attached document from the perspective of **{party}** and provide a detailed breakdown in **simple, clear, plain English**.

Structure your response exactly as follows:

## Executive Summary  
*(≤3 sentences)* – Briefly explain the document’s main goal and its primary impact on me.

## My Key Obligations & Responsibilities  
• Bullet every action I must take, promises I make, responsibilities I accept. Include any deadlines.

## Key Risks & Red Flags  
• Bullet the most significant risks for me. Highlight unusual, one-sided, ambiguous, or problematic clauses and explain **why** they are risky in simple terms.

## Key Benefits & Protections  
• Bullet clauses that clearly protect my interests or benefit me.

## Jargon Buster  
Explain the 3–5 most confusing or important legal terms in plain language.

## Questions to Ask  
List 3–5 critical questions I should ask the other party before signing.

Respond in markdown with bullets where specified.
---
CONTRACT TEXT:\n\n{doc_text}
"""
    return _chat(prompt)

# --------------------------------------------------
# Streamlit UI logic
# --------------------------------------------------

st.set_page_config(page_title="Legal Doc Analyzer", layout="wide")
st.title("📄 Legal Document Analyzer (Plain-English Edition)")

if "stage" not in st.session_state:
    st.session_state.stage = 0            # 0 = upload, 1 = parties select, 2 = side analysis
    st.session_state.summary = ""
    st.session_state.parties = []
    st.session_state.doc_text = ""

upload = st.file_uploader("Upload PDF, DOCX, or TXT", type=["pdf", "docx", "txt"])

if upload:
    text = load_file_text(upload)
    st.session_state.doc_text = text   # store for later reuse
    st.success(f"Loaded **{upload.name}**")
    st.write("Preview (first 1 000 chars):")
    st.code(text[:1000] + ("…" if len(text) > 1000 else ""), language="text")

    if st.session_state.stage == 0:
        if st.button("🔍 First-Pass Analysis", disabled=(openai.api_key == "")):
            with st.spinner("Running first pass …"):
                data = first_pass_analysis(text)
            st.session_state.summary = data["summary"]
            st.session_state.parties = data["parties"]
            st.session_state.stage = 1
            st.rerun()

    elif st.session_state.stage == 1:
        st.markdown("## 📝 Executive Summary (Neutral)")
        st.markdown(st.session_state.summary or "_No summary returned_")
        selected_party = st.selectbox("Select the side you represent", st.session_state.parties)
        if st.button("⚖️ Deep Dive for My Side"):
            with st.spinner("Analyzing from your side …"):
                analysis_md = side_focused_analysis(selected_party, st.session_state.doc_text)
            st.session_state.side_md = analysis_md
            st.session_state.stage = 2
            st.rerun()

    elif st.session_state.stage == 2:
        st.markdown(st.session_state.side_md)
        if st.button("🔁 Analyze New Document"):
            st.session_state.clear()
            st.session_state.stage = 0
            st.rerun()
else:
    st.info("⬆️ Upload a legal document to get started.")

st.markdown("---")
st.caption("_Automated analysis – not legal advice. Always consult qualified counsel._")
