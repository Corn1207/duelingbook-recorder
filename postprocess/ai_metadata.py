"""
ai_metadata.py

Generates YouTube metadata (title, description, tags) for a duelingbook replay
using the Gemini API.
"""

import logging
import os
import re

from google import genai
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

MODEL = "gemini-2.5-flash"


def _get_client():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set in .env")
    return genai.Client(api_key=api_key)


def generate_metadata(
    deck1: str,
    deck2: str,
    label_left: str = "DUELINGBOOK",
    label_right: str = "HIGH RATED",
    notes: str = "",
) -> dict:
    """
    Generates title, description and tags for a Yu-Gi-Oh replay video.

    Returns:
        {
            "title": str,
            "description": str,
            "tags": str,   # comma-separated
        }
    """
    notes_section = f"\nAdditional context from the creator:\n{notes.strip()}\n" if notes and notes.strip() else ""

    prompt = f"""
You are a Yu-Gi-Oh! content expert for YouTube targeting a US audience. Generate compelling metadata for a Duelingbook replay video for the channel "Yugioh Pro Games".

Duel: {deck1} vs {deck2}
Context: {label_left} | {label_right}{notes_section}

Generate exactly in this format (no extra text):

TÍTULO:
[title here, max 70 characters, in English, include emojis if they fit, make it catchy and clickable]

DESCRIPCIÓN:
[description here, 3-5 paragraphs, in English. Mention both decks, the context ({label_right}),
hype up the gameplay, invite viewers to subscribe to "Yugioh Pro Games" and comment their thoughts.
Do NOT include any timestamps section. End with a short note about the Yugioh Pro Games channel.]

TAGS:
[comma-separated tags, in English, minimum 15 tags covering yugioh, both decks, duelingbook, current meta]
"""

    client = _get_client()
    logger.info(f"Generating metadata for {deck1} vs {deck2}...")
    response = client.models.generate_content(model=MODEL, contents=prompt)
    text = response.text

    title = _extract_section(text, "TÍTULO")
    description = _extract_section(text, "DESCRIPCIÓN")
    tags = _extract_section(text, "TAGS")

    return {
        "title": title,
        "description": description,
        "tags": tags,
    }


def _extract_section(text: str, section: str) -> str:
    pattern = rf"{section}:\s*\n(.*?)(?=\n[A-ZÁÉÍÓÚ]+:|$)"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return ""
