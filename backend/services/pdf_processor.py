"""PDF 텍스트 추출(PyMuPDF) + Document Chunking."""
import re

import pymupdf
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from backend.config import settings


class PDFProcessingError(Exception):
    """PDF를 읽거나 텍스트를 추출할 수 없을 때 발생."""


def _clean(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_pages(file_bytes: bytes, filename: str) -> tuple[list[Document], int]:
    """PDF를 페이지 단위 Document 리스트로 변환합니다. (텍스트가 있는 페이지만)"""
    try:
        doc = pymupdf.open(stream=file_bytes, filetype="pdf")
    except Exception as e:  # 손상 파일 등
        raise PDFProcessingError(f"PDF 파일을 열 수 없습니다: {e}") from e

    with doc:
        if doc.needs_pass and not doc.authenticate(""):
            raise PDFProcessingError("암호가 걸린 PDF는 지원하지 않습니다.")

        pages: list[Document] = []
        for page_no, page in enumerate(doc, start=1):
            # sort=True: 다단 레이아웃에서도 읽는 순서(위→아래, 왼→오른)대로 정렬
            text = _clean(page.get_text("text", sort=True) or "")
            if text:
                pages.append(Document(page_content=text, metadata={"source": filename, "page": page_no}))
        num_pages = doc.page_count

    if not pages:
        raise PDFProcessingError(
            "PDF에서 텍스트를 추출하지 못했습니다. 스캔(이미지) PDF라면 텍스트가 포함된 PDF로 올려주세요."
        )
    return pages, num_pages


def chunk_documents(pages: list[Document]) -> list[Document]:
    """페이지 문서를 검색/출제용 청크로 분할합니다. metadata에 chunk_id(=리스트 인덱스)를 부여합니다."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        separators=["\n\n", "\n", ". ", "다. ", " ", ""],
    )
    chunks = splitter.split_documents(pages)
    for i, chunk in enumerate(chunks):
        chunk.metadata["chunk_id"] = i
    return chunks
