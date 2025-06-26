# app.py – Legal Doc Analyzer (detect‑parties only, no generic labels)
# -----------------------------------------------------------------------------
# Workflow
#   1. User uploads a legal doc.
#   2. App does a *quick scan* to detect the contracting parties only (no 200‑word
#      summary, no preview).
#   3. Presents an exact dropdown list of those parties so the user can declare
#      which side they represent.
#   4. Runs a plain‑English deep‑dive analysis from that party’s perspective.
# -----------------------------------------------------------------------------
# Run: streamlit run app.py
# -----------------------------------------------------------------------------

import os
import io
import json
from typing import List

import streamlit as st
import openai
from PyPDF2 import PdfReader
from docx import Document as DocxDocument

# --------------------------------------------------
# Config
# --------------------------------------------------
openai.api_key = os.getenv("OPENAI_API_KEY", st.secrets.get("OPENAI_API_KEY", ""))
MODEL = "gpt-4o-mini"  # swap if desired
MAX_CHARS = 30_000      # truncate very large docs

# --------------------------------------------------
# Helpers – file loader
# --------------------------------------------------

def load_text(upload) -> str:
    name = upload.name.lower()
    data = upload.read()
    if name.endswith(".pdf"):
        reader = PdfReader(io.BytesIO(data))
        text = "\n".join(p.extract_text() or "" for p in reader.pages)
    elif name.endswith(".docx"):
        doc = DocxDocument(io.BytesIO(data))
        text = "\n".join(p.text for p in doc.paragraphs)
    else:
        text = data.decode("utf-8", errors="ignore")
    return text[:MAX_CHARS]

# --------------------------------------------------
# OpenAI wrappers
# --------------------------------------------------

def chat(prompt: str) -> str:
    resp = openai.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
    )
    return resp.choices[0].message.content.strip()


def detect_parties(doc_text: str) -> List[str]:
    """Return a list of parties exactly as in document (best effort)."""
    prompt = f"""
You are a neutral legal analyst. Identify ALL primary contracting parties mentioned in the agreement exactly as they appear (company names, individuals, etc.).
Respond ONLY in JSON: {{"parties": ["Party 1", "Party 2", …]}}.
---
{doc_text}
"""
    raw = chat(prompt)
    try:
        parties = json.loads(raw).get("parties", [])
        parties = [p.strip() for p in parties if p.strip()]
        return parties or ["Could‑not‑detect"]
    except json.JSONDecodeError:
        return ["Could‑not‑detect"]

# --------------------------------------------------
# Deep‑dive analysis for chosen party
# --------------------------------------------------

def analyze_for_party(party: str, doc_text: str) -> str:
    prompt = f"""
Please analyze the attached document **strictly from the perspective of {party}** and answer in clear, plain English.

Structure your response exactly as follows:

## Executive Summary (≤3 sentences)

## My Key Obligations & Responsibilities (bullets)

## Key Risks & Red Flags (bullets + simple explanation of why)

## Key Benefits & Protections (bullets)

## Jargon Buster (explain 3–5 key legal terms)

## Questions to Ask (3–5 questions)

Respond in markdown.
---
{doc_text}
"""
    return chat(prompt)

# --------------------------------------------------
# Streamlit UI
# --------------------------------------------------

st.set_page_config(page_title="Legal Doc Analyzer", layout="wide")
st.title("📄 Legal Document Analyzer – Pick Your Side")

if "stage" not in st.session_state:
    st.session_state.update({"stage": 0, "doc": "", "parties": [], "analysis": ""})

upload = st.file_uploader("Upload PDF, DOCX, or TXT", type=["pdf", "docx", "txt"])

if upload and st.session_state.stage == 0:
    st.session_state.doc = load_text(upload)
    with st.spinner("Detecting parties …"):
        st.session_state.parties = detect_parties(st.session_state.doc)
    st.session_state.stage = 1
    st.rerun()

# Stage 1 – choose party
if st.session_state.stage == 1:
    st.markdown("### Select the party you represent")
    party = st.selectbox("I represent", st.session_state.parties, key="party_choice")
    if st.button("⚖️ Analyze for My Side"):
        with st.spinner("Generating analysis …"):
            st.session_state.analysis = analyze_for_party(party, st.session_state.doc)
        st.session_state.stage = 2
        st.rerun()

# Stage 2 – show analysis
if st.session_state.stage == 2:
    st.markdown(st.session_state.analysis)
    if st.button("🔄 New Document"):
        st.session_state.clear()
        st.rerun()

if st.session_state.stage == 0 and not upload:
    st.info("⬆️ Upload a legal document to begin.")

st.markdown("---")
st.caption("_Automated analysis – not legal advice. Consult qualified counsel._")
