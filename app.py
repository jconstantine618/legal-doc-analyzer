# app.py – Legal Doc Analyzer (no preview, party‑selector flow)
# -----------------------------------------------------------------------------
# Streamlit workflow
#   1. User uploads a legal doc (PDF, DOCX, TXT)
#   2. App performs a *quick first‑pass scan* to detect contracting parties and give a
#      neutral executive summary (no raw text preview shown to the user).
#   3. User selects which party they represent from a dropdown list.
#   4. App runs a plain‑English deep‑dive analysis from that party’s perspective.
# -----------------------------------------------------------------------------
# Run: streamlit run app.py
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
MAX_CHARS = 30_000           # truncate huge docs for safety

# --------------------------------------------------
# Helpers – load file text
# --------------------------------------------------

def load_file_text(upload) -> str:
    """Return raw text (first MAX_CHARS) from an uploaded PDF/DOCX/TXT."""
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
# OpenAI chat wrappers
# --------------------------------------------------

def _chat(prompt: str) -> str:
    resp = openai.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    return resp.choices[0].message.content.strip()


def first_pass_analysis(doc_text: str) -> Dict[str, Any]:
    """Return exec summary + detected parties list."""
    prompt = f"""
You are a neutral legal analyst. Read the contract below and:
1. Produce an executive summary (≤200 words).
2. List the primary contracting parties exactly as written.
Respond ONLY in valid JSON: {{"summary": "…", "parties": ["…", …]}}.
---
CONTRACT:\n\n{doc_text}
"""
    raw = _chat(prompt)
    try:
        data = json.loads(raw)
        parties = [p.strip() for p in data.get("parties", []) if p.strip()] or ["Party A", "Party B"]
        return {"summary": data.get("summary", ""), "parties": parties}
    except json.JSONDecodeError:
        return {"summary": raw, "parties": ["Party A", "Party B"]}


def side_focused_analysis(party: str, doc_text: str) -> str:
    """Return plain‑English analysis for the chosen party."""
    prompt = f"""
Please analyze the attached document from the perspective of **{party}** and provide a detailed breakdown in **simple, clear, plain English**.

Structure your response exactly as follows:

## Executive Summary  
*(≤3 sentences)* – Briefly explain the document’s main goal and its primary impact on me.

## My Key Obligations & Responsibilities  
• Bullet every action I must take, promises I make, responsibilities I accept. Include any deadlines.

## Key Risks & Red Flags  
• Bullet the most significant risks for me. Highlight unusual, one‑sided, ambiguous, or problematic clauses and explain **why** they are risky in simple terms.

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
# Streamlit UI
# --------------------------------------------------

st.set_page_config(page_title="Legal Doc Analyzer", layout="wide")
st.title("📄 Legal Document Analyzer – Party‑Specific")

# Session state defaults
if "stage" not in st.session_state:
    st.session_state.update({
        "stage": 0,            # 0 upload → 1 choose party → 2 analysis
        "summary": "",
        "parties": [],
        "doc_text": "",
        "side_md": "",
    })

upload = st.file_uploader("Upload PDF, DOCX, or TXT", type=["pdf", "docx", "txt"])

if upload:
    st.success(f"Loaded **{upload.name}**")
    # Store the full text once so we don’t reload after reruns
    if st.session_state.stage == 0:
        st.session_state.doc_text = load_file_text(upload)

    # --- Stage 0: run first pass ---
    if st.session_state.stage == 0:
        if st.button("🔍 Detect Parties & Summarize", disabled=(openai.api_key == "")):
            with st.spinner("Scanning document …"):
                data = first_pass_analysis(st.session_state.doc_text)
            st.session_state.summary = data["summary"]
            st.session_state.parties = data["parties"]
            st.session_state.stage = 1
            st.rerun()

    # --- Stage 1: show summary + party selector ---
    elif st.session_state.stage == 1:
        st.markdown("## 📝 Executive Summary (Neutral)")
        st.markdown(st.session_state.summary or "_No summary returned_")
        party_choice = st.selectbox("Select the party you represent", st.session_state.parties)
        if st.button("⚖️ Analyze from My Perspective"):
            with st.spinner("Deep‑diving …"):
                md = side_focused_analysis(party_choice, st.session_state.doc_text)
            st.session_state.side_md = md
            st.session_state.stage = 2
            st.rerun()

    # --- Stage 2: show party‑specific analysis ---
    elif st.session_state.stage == 2:
        st.markdown(st.session_state.side_md)
        if st.button("🔁 Start Over"):
            st.session_state.clear()
            st.rerun()
else:
    st.info("⬆️ Upload a legal document to begin.")

st.markdown("---")
st.caption("_Automated analysis – not legal advice. Consult qualified counsel._")
