from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePath

from pypdf import PdfReader

from app.config import Settings


@dataclass
class Chunk:
    text: str
    page: int | None
    index: int


def parse_and_chunk(data: bytes, filename: str, settings: Settings) -> list[Chunk]:
    if not data or len(data) > settings.max_file_bytes:
        raise ValueError("File is empty or exceeds MAX_FILE_BYTES")
    extension = PurePath(filename).suffix.lower()
    pages: list[tuple[int | None, str]] = []
    if extension in {".txt", ".md"}:
        try:
            pages = [(None, data.decode("utf-8"))]
        except UnicodeDecodeError as exc:
            raise ValueError("Text files must be saved as UTF-8") from exc
    elif extension == ".pdf":
        if not data.startswith(b"%PDF-"):
            raise ValueError("File is not a valid PDF")
        try:
            reader = PdfReader(BytesIO(data))
            if reader.is_encrypted:
                raise ValueError("Password-protected PDFs are not supported")
            if len(reader.pages) > settings.max_pdf_pages:
                raise ValueError("PDF exceeds MAX_PDF_PAGES")
            # Bound each content stream before invoking the text extractor.
            total = 0
            for number, page in enumerate(reader.pages, 1):
                stream = page.get_contents()
                if stream and len(stream.get_data()) > 10_000_000:
                    raise ValueError("PDF page is too complex; export a simpler PDF")
                value = page.extract_text() or ""
                total += len(value)
                if total > settings.max_document_chars:
                    raise ValueError("Document exceeds MAX_DOCUMENT_CHARS")
                pages.append((number, value))
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("Unable to read PDF; export it again as a text PDF") from exc
    else:
        raise ValueError("Supported files: .txt, .md and text-based .pdf")
    if sum(len(text) for _, text in pages) > settings.max_document_chars:
        raise ValueError("Document exceeds MAX_DOCUMENT_CHARS")
    chunks = []
    for page, text in pages:
        text = text.replace("\x00", "").strip()
        for start in range(0, len(text), settings.chunk_size - settings.chunk_overlap):
            part = text[start : start + settings.chunk_size].strip()
            if part:
                chunks.append(Chunk(part, page, len(chunks)))
            if start + settings.chunk_size >= len(text):
                break
    if not chunks:
        raise ValueError("No readable text found. Scanned PDFs need OCR before upload")
    if len(chunks) > settings.max_chunks:
        raise ValueError("Too many chunks; split the document into smaller files")
    return chunks
