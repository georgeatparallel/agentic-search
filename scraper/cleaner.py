"""
Content cleaning pipeline: raw HTML → clean markdown text.
Uses trafilatura for main content extraction and html2text for markdown conversion.
"""

import logging
import trafilatura
import html2text

logger = logging.getLogger(__name__)

# Configure html2text converter
_h2t = html2text.HTML2Text()
_h2t.ignore_links = False
_h2t.ignore_images = True
_h2t.ignore_emphasis = False
_h2t.body_width = 0  # Don't wrap lines


def clean_html(html: str, url: str = "") -> dict:
    """
    Extract and clean main content from raw HTML.

    Returns dict with:
      - text: cleaned markdown text
      - title: page title if found
      - metadata: any metadata trafilatura extracted
    """
    if not html:
        return {"text": "", "title": "", "metadata": {}}

    # Step 1: Use trafilatura for main content extraction
    # This removes navigation, footers, ads, sidebars, etc.
    extracted = trafilatura.extract(
        html,
        include_comments=False,
        include_tables=True,
        include_links=True,
        output_format="txt",
        url=url,
    )

    # Step 2: Also extract metadata
    metadata_obj = trafilatura.extract(
        html,
        output_format="xml",
        include_comments=False,
        url=url,
    )

    # Get the title from trafilatura's bare extraction or fallback to html2text
    title = ""
    try:
        bare = trafilatura.bare_extraction(html, url=url)
        if bare:
            title = bare.get("title", "")
    except Exception:
        pass

    # If trafilatura fails, fall back to html2text
    if not extracted or len(extracted.strip()) < 100:
        logger.debug(f"Trafilatura extracted too little from {url}, using html2text fallback")
        try:
            extracted = _h2t.handle(html)
        except Exception as e:
            logger.warning(f"html2text also failed for {url}: {e}")
            extracted = ""

    # Basic post-processing
    if extracted:
        # Remove excessive blank lines
        lines = extracted.split("\n")
        cleaned_lines = []
        prev_blank = False
        for line in lines:
            is_blank = line.strip() == ""
            if is_blank and prev_blank:
                continue
            cleaned_lines.append(line)
            prev_blank = is_blank
        extracted = "\n".join(cleaned_lines).strip()

    return {
        "text": extracted or "",
        "title": title,
        "metadata": {},
    }
