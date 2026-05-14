from __future__ import annotations

import logging
from typing import Any, Optional

from doc_parser.core.chapter.models import DocumentOutline, OutlineNode
from doc_parser.storage.vector_store import ChunkMetadata, VectorChunk

logger = logging.getLogger(__name__)


class ChunkerConfig:
    def __init__(
        self,
        chunk_size: int = 1200,
        chunk_overlap: int = 200,
        include_document_chunk: bool = True,
        document_chunk_size: int = 3000,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.include_document_chunk = include_document_chunk
        self.document_chunk_size = document_chunk_size


class DocumentChunker:
    def __init__(self, config: Optional[ChunkerConfig] = None):
        self._config = config or ChunkerConfig()

    def chunk_chapter(
        self,
        chapter: OutlineNode,
        document_id: str = "",
    ) -> list[VectorChunk]:
        content = chapter.markdown
        if not content or not content.strip():
            return []

        chunks = self._split_text(content, self._config.chunk_size, self._config.chunk_overlap)
        vector_chunks: list[VectorChunk] = []

        images_data = chapter.metadata.get("images", [])
        image_descriptions: list[str] = []
        for img in images_data:
            if isinstance(img, dict):
                parts: list[str] = []
                vlm = img.get("vlm_description", {})
                if isinstance(vlm, dict) and vlm.get("description"):
                    parts.append(vlm["description"][:200])
                ocr = img.get("ocr", {})
                if isinstance(ocr, dict) and ocr.get("text"):
                    parts.append(f"[OCR: {ocr['text'][:100]}]")
                if parts:
                    image_descriptions.append("[Image: " + "; ".join(parts) + "]")

        for i, chunk_text in enumerate(chunks):
            metadata = ChunkMetadata(
                document_id=document_id,
                chapter_id=chapter.id,
                chapter_title=chapter.title,
                chunk_index=i,
                page_start=chapter.page_start,
                page_end=chapter.page_end or chapter.page_start,
                chunk_type="chapter",
            )
            vector_chunks.append(VectorChunk(text=chunk_text, metadata=metadata))

        if image_descriptions and vector_chunks:
            last_chunk = vector_chunks[-1]
            img_text = "\n".join(image_descriptions)
            if len(last_chunk.text) + len(img_text) + 2 <= self._config.chunk_size * 1.5:
                last_chunk.text += "\n\n" + img_text
            else:
                meta = ChunkMetadata(
                    document_id=document_id,
                    chapter_id=chapter.id,
                    chapter_title=chapter.title,
                    chunk_index=len(vector_chunks),
                    page_start=chapter.page_start,
                    page_end=chapter.page_end or chapter.page_start,
                    chunk_type="chapter_images",
                )
                vector_chunks.append(VectorChunk(text=img_text, metadata=meta))

        return vector_chunks

    def chunk_document(
        self,
        outline: DocumentOutline,
    ) -> list[VectorChunk]:
        all_chunks: list[VectorChunk] = []
        chapters = outline.get_all_chapters()

        for chapter in chapters:
            chapter_chunks = self.chunk_chapter(chapter, outline.document_id)
            all_chunks.extend(chapter_chunks)

        if self._config.include_document_chunk:
            doc_chunks = self._build_document_chunks(outline)
            all_chunks.extend(doc_chunks)

        return all_chunks

    def _build_document_chunks(self, outline: DocumentOutline) -> list[VectorChunk]:
        chapters = outline.get_all_chapters()
        full_parts: list[str] = []

        for chapter in chapters:
            if not chapter.markdown:
                continue
            header = f"# {chapter.title}\n\n"
            full_parts.append(header + chapter.markdown)

        full_text = "\n\n---\n\n".join(full_parts)
        if not full_text.strip():
            return []

        chunks = self._split_text(
            full_text, self._config.document_chunk_size, self._config.chunk_overlap
        )
        vector_chunks: list[VectorChunk] = []

        for i, chunk_text in enumerate(chunks):
            metadata = ChunkMetadata(
                document_id=outline.document_id,
                chapter_id="",
                chapter_title=outline.title,
                chunk_index=i,
                page_start=0,
                page_end=0,
                chunk_type="document",
            )
            vector_chunks.append(VectorChunk(text=chunk_text, metadata=metadata))

        return vector_chunks

    def _split_text(
        self, text: str, chunk_size: int, chunk_overlap: int
    ) -> list[str]:
        if len(text) <= chunk_size:
            return [text]

        paragraphs = text.split("\n\n")
        chunks: list[str] = []
        current: list[str] = []
        current_len = 0

        for para in paragraphs:
            para_len = len(para)

            if current_len + para_len + 2 > chunk_size and current:
                chunks.append("\n\n".join(current))

                overlap_parts: list[str] = []
                overlap_len = 0
                for prev in reversed(current):
                    if overlap_len + len(prev) + 2 > chunk_overlap:
                        break
                    overlap_parts.insert(0, prev)
                    overlap_len += len(prev) + 2

                current = overlap_parts
                current_len = sum(len(p) for p in current) + 2 * max(0, len(current) - 1)

            current.append(para)
            current_len += para_len + 2

        if current:
            chunks.append("\n\n".join(current))

        return chunks
