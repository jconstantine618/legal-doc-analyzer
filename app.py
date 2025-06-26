# app.py – Legal Doc Analyzer (party‑detect + manual fallback)
# -----------------------------------------------------------------------------
# Flow
#   1. Upload legal doc (PDF, DOCX, TXT)
#   2. Try to auto‑detect all parties *exactly* as named in the agreement. If at
#      least two parties are found → show a dropdown so the user can pick their
#      side.
#   3. If detection fails or finds <2 parties → prompt the user to manually enter
#      party names (comma‑separated) to proceed.
#   4. Perform plain‑English deep‑dive analysis for the selected party.
# -----------------------------------------------------------------------------
# Run: streamlit run app.py
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
# Helper – load text from uploaded file
# --------------------------------------------------

def load_text(upload) -> str:
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
# Party detection util
# --------------------------------------------------

PLACEHOLDER_RE = re.compile(r"party\s*[ab12]|plaintiff|defendant", re.IGNORECASE)


def _clean_parties(raw: List[str]) -> List[str]:
    out = []
    seen = set()
    for p in raw:
        if not p:
            continue
        if PLACEHOLDER_RE.fullmatch(p.strip()):  # skip placeholders
            continue
        key = p.strip().lower()
        if key not in seen:
            out.append(p.strip())
            seen.add(key)
    return out


def detect_parties(text: str) -> List[str]:
    """Best‑effort party extraction via LLM; returns deduped list or []."""
    base_prompt = (
        "You are a neutral legal analyst. Identify **every** primary contracting "
        "party (companies and individuals) *exactly* as they appear in the "
        "agreement. Respond ONLY as valid JSON: {\"parties\": ["Party 1", "Party 2", …]} "
        "and do NOT use placeholders like Party A/B."
    )

    def ask(extra: str = "") -> List[str]:
        raw = chat(f"{base_prompt}\n{extra}\n---\n{text}\n")
        try:
            plist = json.loads(raw).get("parties", [])
        except json.JSONDecodeError:
            plist = []
        return _clean_parties(plist)

    parties = ask()
    if len(parties) < 2:
        # one more attempt with a reminder
        parties = ask("Return at least the two primary names – no placeholders.")
    return parties

# --------------------------------------------------
# Deep dive analysis
# --------------------------------------------------

def analyze_for_party(party: str, text: str) -> str:
    prompt = f"""
You are legal counsel for **{party}**. Analyze the agreement below and respond in clear, plain English.

Structure your answer:
## Executive Summary (≤3 sentences)
## My Key Obligations & Responsibilities (bullets)
## Key Risks & Red Flags (bullets + why they matter)
## Key Benefits & Protections (bullets)
## Jargon Buster (explain 3–5 key terms)
## Questions to Ask (3–5)
---\n{text}
"""
    return chat(prompt, temperature=0.2)

# --------------------------------------------------
# Streamlit UI
# --------------------------------------------------

st.set_page_config(page_title="Legal Doc Analyzer", layout="wide")
st.title("📄 Legal Document Analyzer – Pick Your Side")

if "stage" not in st.session_state:
    st.session_state.update({
        "stage": 0,      # 0=upload  1=select/enter party  2=analysis
        "doc": "",
        "parties": [],
        "analysis": "",
    })

upload = st.file_uploader("Upload PDF, DOCX, or TXT", type=["pdf", "docx", "txt"])

# Stage 0 – upload and auto‑detect
if upload and st.session_state.stage == 0:
    st.session_state.doc = load_text(upload)
    with st.spinner("Detecting parties …"):
        st.session_state.parties = detect_parties(st.session_state.doc)
    st.session_state.stage = 1  # go to party selection (even if empty)
    st.rerun()

# Stage 1 – party selection or manual entry
if st.session_state.stage == 1:
    if len(st.session_state.parties) >= 2:
        st.markdown("### Select the party you represent")
        party = st.selectbox("I represent", st.session_state.parties, key="party_choice")
    else:
        st.warning("Could not confidently detect at least two parties. Please enter them manually (comma‑separated). Example: Company A, Company B")
        manual = st.text_input("Parties (comma‑separated)")
        # Parse manual entry into list when user types
        party_list = [p.strip() for p in manual.split(",") if p.strip()]
        if len(party_list) >= 2:
            st.session_state.parties = party_list
            party = st.selectbox("I represent", st.session_state.parties, key="party_choice_manual")
        else:
            party = None

    if party and st.button("⚖️ Analyze for My Side"):
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
