"""
Text chunker that splits long documents into overlapping chunks
suitable for LLM context windows.

Uses a simple word-based approximation: ~1 token ≈ 0.75 words.
"""

import logging
import config

logger = logging.getLogger(__name__)

WORDS_PER_TOKEN = 0.75  # rough approximation


def estimate_tokens(text: str) -> int:
    """Rough token count estimation based on word count."""
    return int(len(text.split()) / WORDS_PER_TOKEN)


def chunk_text(
    text: str,
    max_tokens: int | None = None,
    overlap_tokens: int | None = None,
) -> list[str]:
    """
    Split text into overlapping chunks.

    If the text fits within max_tokens, returns it as a single chunk.
    Otherwise, splits on paragraph boundaries with overlap.

    Returns list of text chunks.
    """
    max_tokens = max_tokens or config.CHUNK_MAX_TOKENS
    overlap_tokens = overlap_tokens or config.CHUNK_OVERLAP_TOKENS

    if estimate_tokens(text) <= max_tokens:
        return [text]

    max_words = int(max_tokens * WORDS_PER_TOKEN)
    overlap_words = int(overlap_tokens * WORDS_PER_TOKEN)

    # Split into paragraphs first for cleaner boundaries
    paragraphs = text.split("\n\n")

    chunks = []
    current_words = []
    current_count = 0

    for para in paragraphs:
        para_words = para.split()
        para_len = len(para_words)

        # If a single paragraph exceeds max, split it by sentences
        if para_len > max_words:
            sentences = para.replace(". ", ".\n").split("\n")
            for sent in sentences:
                sent_words = sent.split()
                if current_count + len(sent_words) > max_words and current_words:
                    chunks.append(" ".join(current_words))
                    # Keep overlap
                    overlap_start = max(0, len(current_words) - overlap_words)
                    current_words = current_words[overlap_start:]
                    current_count = len(current_words)
                current_words.extend(sent_words)
                current_count += len(sent_words)
            continue

        if current_count + para_len > max_words and current_words:
            chunks.append(" ".join(current_words))
            overlap_start = max(0, len(current_words) - overlap_words)
            current_words = current_words[overlap_start:]
            current_count = len(current_words)

        current_words.extend(para_words)
        current_count += para_len

    # Don't forget the last chunk
    if current_words:
        chunks.append(" ".join(current_words))

    logger.debug(f"Split text into {len(chunks)} chunks (est. {estimate_tokens(text)} tokens total)")
    return chunks
