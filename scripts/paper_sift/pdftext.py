"""Paper text for Jev: extract with pypdf, cut at the references, cap the length."""
import re

MAX_CHARS = 90_000  # about 25k tokens, inside Jev's 32k state limit
MIN_CHARS = 2_000   # less usually means a scanned PDF or a failed extraction
_REFERENCES = re.compile(r"\n\s*(?:References|REFERENCES|Bibliography|BIBLIOGRAPHY)\s*\n")


def cut_references(text):
    """Cut at the first references heading after 30% of the text (drops appendices too)."""
    for match in _REFERENCES.finditer(text):
        if match.start() > 0.3 * len(text):
            return text[:match.start()], True
    return text, False


def prepare(text, max_chars=MAX_CHARS):
    body, was_cut = cut_references(text)
    return body[:max_chars], was_cut, len(text)


def extract(pdf_path):
    from pypdf import PdfReader  # installed on demand by deps.ensure_pypdf
    reader = PdfReader(str(pdf_path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)
