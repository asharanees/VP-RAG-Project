import hashlib
import io
from typing import List, Tuple

from pypdf import PdfReader


def read_pdf_pages(file_bytes: bytes) -> List[Tuple[int, str]]:
    reader = PdfReader(io.BytesIO(file_bytes))
    pages: List[Tuple[int, str]] = []
    for idx, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        if text.strip():
            pages.append((idx + 1, text))
    return pages


def sha256_hex(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
