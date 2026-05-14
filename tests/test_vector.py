from __future__ import annotations

import math

import pytest

from doc_parser.core.chapter.models import DocumentOutline, OutlineNode
from doc_parser.storage.chunker import ChunkerConfig, DocumentChunker
from doc_parser.storage.graph_store import (
    GraphEdge,
    GraphNode,
    GraphQueryResult,
    InMemoryGraphStore,
)
from doc_parser.storage.vector_store import (
    ChunkMetadata,
    InMemoryVectorStore,
    SearchResult,
    VectorChunk,
    VectorStoreResult,
)


def _outline_for_chunking():
    c1 = OutlineNode(id="ch_0", title="Chapter 1", level=1, page_start=0, page_end=2)
    c1.markdown = "A" * 500 + "\n\n" + "B" * 500
    c2 = OutlineNode(id="ch_1", title="Chapter 2", level=1, page_start=3, page_end=5)
    c2.markdown = "C" * 300
    return DocumentOutline(document_id="doc1", title="Test Doc", nodes=[c1, c2])


class TestVectorChunk:
    def test_defaults(self):
        chunk = VectorChunk()
        assert chunk.id == ""
        assert chunk.text == ""
        assert chunk.embedding == []

    def test_generate_id(self):
        id1 = VectorChunk.generate_id()
        id2 = VectorChunk.generate_id()
        assert id1 != id2
        assert len(id1) == 36

    def test_with_metadata(self):
        meta = ChunkMetadata(document_id="doc1", chapter_id="ch1", chunk_index=0)
        chunk = VectorChunk(text="hello", metadata=meta)
        assert chunk.metadata.document_id == "doc1"
        assert chunk.metadata.chunk_index == 0


class TestChunkMetadata:
    def test_defaults(self):
        meta = ChunkMetadata()
        assert meta.document_id == ""
        assert meta.chunk_type == "chapter"
        assert meta.entities == []

    def test_with_values(self):
        meta = ChunkMetadata(
            document_id="doc1",
            chapter_id="ch1",
            chapter_title="Intro",
            chunk_index=2,
            page_start=5,
            page_end=10,
            chunk_type="document",
            entities=["entity1", "entity2"],
        )
        assert meta.document_id == "doc1"
        assert meta.chunk_type == "document"
        assert len(meta.entities) == 2


class TestInMemoryVectorStore:
    @pytest.mark.asyncio
    async def test_add_and_search(self):
        store = InMemoryVectorStore()
        chunks = [
            VectorChunk(
                id="c1",
                text="neural network",
                embedding=[1.0, 0.0, 0.0],
                metadata=ChunkMetadata(document_id="doc1"),
            ),
            VectorChunk(
                id="c2",
                text="deep learning",
                embedding=[0.0, 1.0, 0.0],
                metadata=ChunkMetadata(document_id="doc1"),
            ),
        ]
        result = await store.add_chunks(chunks, document_id="doc1")
        assert result.total_chunks == 2
        assert result.chunk_ids == ["c1", "c2"]

        results = await store.search([1.0, 0.0, 0.0], top_k=2)
        assert len(results) == 2
        assert results[0].chunk_id == "c1"
        assert results[0].score > 0

    @pytest.mark.asyncio
    async def test_search_with_document_filter(self):
        store = InMemoryVectorStore()
        chunks = [
            VectorChunk(id="c1", text="text1", embedding=[1.0, 0.0], metadata=ChunkMetadata(document_id="doc1")),
            VectorChunk(id="c2", text="text2", embedding=[0.0, 1.0], metadata=ChunkMetadata(document_id="doc2")),
        ]
        await store.add_chunks(chunks)

        results = await store.search([1.0, 0.0], document_id="doc1")
        assert len(results) == 1
        assert results[0].chunk_id == "c1"

    @pytest.mark.asyncio
    async def test_search_with_chapter_filter(self):
        store = InMemoryVectorStore()
        chunks = [
            VectorChunk(id="c1", text="text1", embedding=[1.0, 0.0], metadata=ChunkMetadata(document_id="doc1", chapter_id="ch1")),
            VectorChunk(id="c2", text="text2", embedding=[0.9, 0.1], metadata=ChunkMetadata(document_id="doc1", chapter_id="ch2")),
        ]
        await store.add_chunks(chunks)

        results = await store.search([1.0, 0.0], chapter_id="ch1")
        assert len(results) == 1
        assert results[0].chunk_id == "c1"

    @pytest.mark.asyncio
    async def test_search_with_score_threshold(self):
        store = InMemoryVectorStore()
        chunks = [
            VectorChunk(id="c1", text="text1", embedding=[1.0, 0.0], metadata=ChunkMetadata(document_id="doc1")),
            VectorChunk(id="c2", text="text2", embedding=[0.0, 1.0], metadata=ChunkMetadata(document_id="doc1")),
        ]
        await store.add_chunks(chunks)

        results = await store.search([1.0, 0.0], score_threshold=0.5)
        assert all(r.score >= 0.5 for r in results)

    @pytest.mark.asyncio
    async def test_delete_document(self):
        store = InMemoryVectorStore()
        chunks = [
            VectorChunk(id="c1", text="text1", embedding=[1.0], metadata=ChunkMetadata(document_id="doc1")),
            VectorChunk(id="c2", text="text2", embedding=[0.5], metadata=ChunkMetadata(document_id="doc2")),
        ]
        await store.add_chunks(chunks)

        deleted = await store.delete_document("doc1")
        assert deleted is True

        results = await store.search([1.0], document_id="doc1")
        assert len(results) == 0

        results = await store.search([0.5], document_id="doc2")
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_get_document_chunks(self):
        store = InMemoryVectorStore()
        chunks = [
            VectorChunk(id="c1", text="text1", embedding=[], metadata=ChunkMetadata(document_id="doc1")),
            VectorChunk(id="c2", text="text2", embedding=[], metadata=ChunkMetadata(document_id="doc2")),
        ]
        await store.add_chunks(chunks)

        doc_chunks = await store.get_document_chunks("doc1")
        assert len(doc_chunks) == 1
        assert doc_chunks[0].text == "text1"

    @pytest.mark.asyncio
    async def test_health_check(self):
        store = InMemoryVectorStore()
        assert await store.health_check() is True

    @pytest.mark.asyncio
    async def test_auto_generate_id(self):
        store = InMemoryVectorStore()
        chunk = VectorChunk(text="hello", embedding=[])
        result = await store.add_chunks([chunk])
        assert len(result.chunk_ids) == 1
        assert result.chunk_ids[0] != ""

    @pytest.mark.asyncio
    async def test_cosine_similarity(self):
        assert InMemoryVectorStore._cosine_similarity([1, 0], [1, 0]) == pytest.approx(1.0)
        assert InMemoryVectorStore._cosine_similarity([1, 0], [0, 1]) == pytest.approx(0.0)
        assert InMemoryVectorStore._cosine_similarity([], []) == 0.0
        assert InMemoryVectorStore._cosine_similarity([1, 1], [1, 1]) == pytest.approx(1.0)


class TestDocumentChunker:
    def test_chunk_chapter_basic(self):
        chunker = DocumentChunker(ChunkerConfig(chunk_size=300, chunk_overlap=50))
        chapter = OutlineNode(id="ch1", title="Test Chapter", level=1, page_start=0, page_end=2)
        chapter.markdown = "Short content here."
        chunks = chunker.chunk_chapter(chapter, document_id="doc1")
        assert len(chunks) == 1
        assert chunks[0].metadata.document_id == "doc1"
        assert chunks[0].metadata.chapter_id == "ch1"
        assert chunks[0].metadata.chunk_type == "chapter"

    def test_chunk_chapter_long_text(self):
        chunker = DocumentChunker(ChunkerConfig(chunk_size=200, chunk_overlap=50))
        chapter = OutlineNode(id="ch1", title="Long Chapter", level=1, page_start=0, page_end=5)
        chapter.markdown = "\n\n".join([f"Paragraph {i} with some text content here." for i in range(20)])
        chunks = chunker.chunk_chapter(chapter, document_id="doc1")
        assert len(chunks) > 1
        for i, chunk in enumerate(chunks):
            assert chunk.metadata.chunk_index == i

    def test_chunk_chapter_empty(self):
        chunker = DocumentChunker()
        chapter = OutlineNode(id="ch1", title="Empty", level=1, page_start=0)
        chunks = chunker.chunk_chapter(chapter, document_id="doc1")
        assert len(chunks) == 0

    def test_chunk_chapter_with_images(self):
        chunker = DocumentChunker(ChunkerConfig(chunk_size=500))
        chapter = OutlineNode(id="ch1", title="With Images", level=1, page_start=0, page_end=2)
        chapter.markdown = "Some text content."
        chapter.metadata = {
            "images": [
                {
                    "path": "fig1.png",
                    "vlm_description": {"description": "Architecture diagram"},
                    "ocr": {"text": "Figure 1: Neural Network"},
                }
            ]
        }
        chunks = chunker.chunk_chapter(chapter, document_id="doc1")
        assert len(chunks) >= 1
        all_text = " ".join(c.text for c in chunks)
        assert "Architecture diagram" in all_text

    def test_chunk_document(self):
        chunker = DocumentChunker(ChunkerConfig(chunk_size=500, include_document_chunk=True))
        outline = _outline_for_chunking()
        chunks = chunker.chunk_document(outline)
        chapter_chunks = [c for c in chunks if c.metadata.chunk_type == "chapter"]
        doc_chunks = [c for c in chunks if c.metadata.chunk_type == "document"]
        assert len(chapter_chunks) > 0
        assert len(doc_chunks) > 0

    def test_chunk_document_no_doc_chunk(self):
        chunker = DocumentChunker(ChunkerConfig(include_document_chunk=False))
        outline = _outline_for_chunking()
        chunks = chunker.chunk_document(outline)
        doc_chunks = [c for c in chunks if c.metadata.chunk_type == "document"]
        assert len(doc_chunks) == 0

    def test_chunk_document_empty_outline(self):
        chunker = DocumentChunker()
        outline = DocumentOutline(document_id="empty")
        chunks = chunker.chunk_document(outline)
        assert len(chunks) == 0

    def test_split_text_basic(self):
        chunker = DocumentChunker(ChunkerConfig(chunk_size=100, chunk_overlap=20))
        text = "A" * 50 + "\n\n" + "B" * 50 + "\n\n" + "C" * 50
        chunks = chunker._split_text(text, 100, 20)
        assert len(chunks) >= 2

    def test_split_text_short_text(self):
        chunker = DocumentChunker()
        text = "Short text"
        chunks = chunker._split_text(text, 1000, 200)
        assert len(chunks) == 1
        assert chunks[0] == text


class TestInMemoryGraphStore:
    @pytest.mark.asyncio
    async def test_add_and_get_node(self):
        store = InMemoryGraphStore()
        node = GraphNode(id="n1", label="concept", properties={"name": "Neural Network"})
        added = await store.add_node(node)
        assert added is True

        retrieved = await store.get_node("n1")
        assert retrieved is not None
        assert retrieved.label == "concept"
        assert retrieved.properties["name"] == "Neural Network"

    @pytest.mark.asyncio
    async def test_get_node_not_found(self):
        store = InMemoryGraphStore()
        result = await store.get_node("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_add_edge_and_neighbors(self):
        store = InMemoryGraphStore()
        n1 = GraphNode(id="n1", label="concept", properties={"name": "A"})
        n2 = GraphNode(id="n2", label="concept", properties={"name": "B"})
        await store.add_node(n1)
        await store.add_node(n2)

        edge = GraphEdge(id="e1", source="n1", target="n2", label="depends_on")
        added = await store.add_edge(edge)
        assert added is True

        neighbors = await store.get_neighbors("n1")
        assert len(neighbors) == 1
        assert neighbors[0].id == "n2"

    @pytest.mark.asyncio
    async def test_neighbors_direction(self):
        store = InMemoryGraphStore()
        n1 = GraphNode(id="n1", label="A")
        n2 = GraphNode(id="n2", label="B")
        await store.add_node(n1)
        await store.add_node(n2)
        await store.add_edge(GraphEdge(id="e1", source="n1", target="n2", label="rel"))

        outgoing = await store.get_neighbors("n1", direction="outgoing")
        assert len(outgoing) == 1
        assert outgoing[0].id == "n2"

        incoming = await store.get_neighbors("n1", direction="incoming")
        assert len(incoming) == 0

        incoming_b = await store.get_neighbors("n2", direction="incoming")
        assert len(incoming_b) == 1

    @pytest.mark.asyncio
    async def test_query_by_keyword(self):
        store = InMemoryGraphStore()
        await store.add_node(GraphNode(id="n1", label="concept", properties={"name": "neural network"}))
        await store.add_node(GraphNode(id="n2", label="concept", properties={"name": "decision tree"}))

        result = await store.query("neural")
        assert len(result.nodes) == 1
        assert result.nodes[0].id == "n1"

    @pytest.mark.asyncio
    async def test_query_empty_returns_all(self):
        store = InMemoryGraphStore()
        await store.add_node(GraphNode(id="n1", label="A"))
        await store.add_node(GraphNode(id="n2", label="B"))

        result = await store.query("")
        assert len(result.nodes) == 2

    @pytest.mark.asyncio
    async def test_delete_document(self):
        store = InMemoryGraphStore()
        n1 = GraphNode(id="n1", label="A", properties={"document_id": "doc1"})
        n2 = GraphNode(id="n2", label="B", properties={"document_id": "doc2"})
        await store.add_node(n1)
        await store.add_node(n2)
        await store.add_edge(GraphEdge(id="e1", source="n1", target="n2", label="rel"))

        deleted = await store.delete_document("doc1")
        assert deleted is True
        assert await store.get_node("n1") is None
        assert await store.get_node("n2") is not None

    @pytest.mark.asyncio
    async def test_health_check(self):
        store = InMemoryGraphStore()
        assert await store.health_check() is True

    @pytest.mark.asyncio
    async def test_query_includes_edges(self):
        store = InMemoryGraphStore()
        await store.add_node(GraphNode(id="n1", label="concept", properties={"name": "neural"}))
        await store.add_node(GraphNode(id="n2", label="concept", properties={"name": "network"}))
        await store.add_edge(GraphEdge(id="e1", source="n1", target="n2", label="relates_to"))

        result = await store.query("neural")
        assert len(result.edges) == 1
        assert result.edges[0].source == "n1"


class TestSearchResult:
    def test_defaults(self):
        r = SearchResult()
        assert r.chunk_id == ""
        assert r.score == 0.0
        assert r.text == ""

    def test_with_values(self):
        meta = ChunkMetadata(document_id="doc1")
        r = SearchResult(chunk_id="c1", text="hello", score=0.95, metadata=meta)
        assert r.chunk_id == "c1"
        assert r.score == 0.95
