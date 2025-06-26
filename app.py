# app.py – Legal Doc Analyzer (improved party detection)
# -----------------------------------------------------------------------------
# Key fix: Detect real party names instead of generic “Party A / Party B”.
# Strategy:
#   • Ask the LLM *not* to return placeholders and include every distinct entity
#     (companies + individuals) exactly as written.
#   • Post‑process to drop placeholders like “Party A/B/1/2” if they sneak in.
#   • If nothing useful remains, ask the LLM a second time with stronger phrasing.
# -----------------------------------------------------------------------------

import os
import io
import json
import re
from typing import List

import streamlit as st
import openai
from PyPDF2 import PdfReader
from docx import Document as DocxDocument

# --------------------------------------------------
# Config
# --------------------------------------------------
openai.api_key = os.getenv("OPENAI_API_KEY", st.secrets.get("OPENAI_API_KEY", ""))
MODEL = "gpt-4o-mini"
MAX_CHARS = 30_000

# --------------------------------------------------
# Helper – load file text
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
# OpenAI wrapper
# --------------------------------------------------

def chat(prompt: str, temperature: float = 0.1) -> str:
    resp = openai.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
    )
    return resp.choices[0].message.content.strip()

# --------------------------------------------------
# Party detection
# --------------------------------------------------

PLACEHOLDER_RE = re.compile(r"party\s*[ab12]|plaintiff|defendant", re.IGNORECASE)

def _clean_parties(raw_list: List[str]) -> List[str]:
    clean = []
    for p in raw_list:
        if not p or PLACEHOLDER_RE.fullmatch(p.strip()):
            continue
        clean.append(p.strip())
    # Deduplicate (case‑insensitive)
    seen = set()
    uniq = []
    for p in clean:
        key = p.lower()
        if key not in seen:
            uniq.append(p)
            seen.add(key)
    return uniq

def detect_parties(doc_text: str) -> List[str]:
    """Return real party names (companies / individuals) or empty list if none."""
    base_prompt = """You are a neutral legal analyst. Identify **all** primary contracting parties in the agreement *exactly* as they appear (company names and individuals). **Do not** invent placeholders like \"Party A\" or \"Party B\". Respond only as valid JSON {{\"parties\": ["Name1", "Name2", …]}}."""

    def ask(prompt_extra: str = "") -> List[str]:
        raw = chat(f"{base_prompt}\n{prompt_extra}\n---\n{doc_text}\n")
        try:
            parties = json.loads(raw).get("parties", [])
        except json.JSONDecodeError:
            parties = []
        return _clean_parties(parties)

    parties = ask()
    # If nothing useful, try one more time with stronger instruction.
    if not parties:
        parties = ask("Remember: return the *actual names*—no placeholders or generic labels.")
    return parties

# --------------------------------------------------
# Deep‑dive analysis
# --------------------------------------------------

def analyze_for_party(party: str, doc_text: str) -> str:
    prompt = f"""
You are legal counsel for **{party}**. Analyze the agreement below and respond in clear, plain English.

Structure your answer:
## Executive Summary (≤3 sentences)
## My Key Obligations & Responsibilities (bullets)
## Key Risks & Red Flags (bullets + why they matter)
## Key Benefits & Protections (bullets)
## Jargon Buster (explain 3–5 key terms)
## Questions to Ask (3–5)
---\n{doc_text}
"""
    return chat(prompt, temperature=0.2)

# --------------------------------------------------
# Streamlit UI
# --------------------------------------------------

st.set_page_config(page_title="Legal Doc Analyzer", layout="wide")
st.title("📄 Legal Document Analyzer – Pick Your Side")

if "stage" not in st.session_state:
    st.session_state.update({"stage": 0, "doc": "", "parties": [], "analysis": ""})

upload = st.file_uploader("Upload PDF, DOCX, or TXT", type=["pdf", "docx", "txt"])

# Stage 0 – upload and detect
if upload and st.session_state.stage == 0:
    st.session_state.doc = load_text(upload)
    with st.spinner("Detecting parties …"):
        st.session_state.parties = detect_parties(st.session_state.doc)
    if st.session_state.parties:
        st.session_state.stage = 1
    else:
        st.error("Could not reliably detect parties. Please review the document text.")
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
