from __future__ import annotations

import pytest

from doc_parser.core.image.enhancer import ImageEnhancer, ImageEnhancerConfig
from doc_parser.core.image.models import EnhancedImage, OCRResult, VLMDescriptionResult
from doc_parser.core.image.ocr_enhance import BaseOCREngine, DummyOCREngine, OCREnhancer
from doc_parser.core.image.vlm_describe import BaseVLMClient, DummyVLMClient, VLMDescriber
from doc_parser.pipeline.base import ContentItem, ElementType, PipelineResult


def _img(path="img1.png", page=1, caption=None, **kw):
    return ContentItem(
        type=ElementType.IMAGE, text="", img_path=path, page_idx=page,
        image_caption=caption or [], **kw,
    )


def _txt(text="hello", page=0, level=0, order=0):
    return ContentItem(
        type=ElementType.TEXT, text=text, text_level=level, page_idx=page, reading_order=order,
    )


def _result(items=None):
    return PipelineResult(
        document_id="test-doc",
        engine="test",
        content_list=items or [],
        markdown="",
    )


class _FakeOCR(BaseOCREngine):
    def __init__(self, text="OCR text", confidence=0.9):
        self._text = text
        self._conf = confidence

    async def extract_text(self, image_path: str) -> OCRResult:
        return OCRResult(text=self._text, confidence=self._conf, word_count=len(self._text.split()))

    async def health_check(self) -> bool:
        return True


class _FakeVLM(BaseVLMClient):
    def __init__(self, desc="A test image", img_type="screenshot"):
        self._desc = desc
        self._type = img_type

    async def describe_image(self, image_path: str, prompt: str = "") -> VLMDescriptionResult:
        return VLMDescriptionResult(
            description=self._desc, image_type=self._type,
            key_info=["info1"], confidence=0.8, model="fake-vlm",
        )

    async def health_check(self) -> bool:
        return True


class TestOCRResult:
    def test_default(self):
        r = OCRResult()
        assert r.text == ""
        assert r.confidence == 0.0
        assert r.word_count == 0

    def test_with_values(self):
        r = OCRResult(text="hello world", confidence=0.95, word_count=2)
        assert r.text == "hello world"
        assert r.confidence == 0.95


class TestVLMDescriptionResult:
    def test_default(self):
        r = VLMDescriptionResult()
        assert r.description == ""
        assert r.image_type == ""

    def test_with_values(self):
        r = VLMDescriptionResult(description="desc", image_type="chart", key_info=["a"], confidence=0.9, model="qwen")
        assert r.description == "desc"
        assert r.key_info == ["a"]


class TestEnhancedImage:
    def test_has_ocr_true(self):
        ei = EnhancedImage(path="x.png", ocr=OCRResult(text="hello"))
        assert ei.has_ocr is True

    def test_has_ocr_false_empty(self):
        ei = EnhancedImage(path="x.png", ocr=OCRResult(text=""))
        assert ei.has_ocr is False

    def test_has_ocr_false_none(self):
        ei = EnhancedImage(path="x.png")
        assert ei.has_ocr is False

    def test_has_vlm_description_true(self):
        ei = EnhancedImage(path="x.png", vlm_description=VLMDescriptionResult(description="desc"))
        assert ei.has_vlm_description is True

    def test_has_vlm_description_false(self):
        ei = EnhancedImage(path="x.png")
        assert ei.has_vlm_description is False


class TestDummyOCREngine:
    @pytest.mark.asyncio
    async def test_returns_empty(self):
        engine = DummyOCREngine()
        r = await engine.extract_text("any.png")
        assert r.text == ""

    @pytest.mark.asyncio
    async def test_health(self):
        engine = DummyOCREngine()
        assert await engine.health_check() is True


class TestOCREnhancer:
    @pytest.mark.asyncio
    async def test_enhance_no_images(self):
        enhancer = OCREnhancer(engine=_FakeOCR())
        result = _result([_txt("hello")])
        enhanced = await enhancer.enhance_images(result)
        assert len(enhanced) == 0

    @pytest.mark.asyncio
    async def test_enhance_with_images(self):
        enhancer = OCREnhancer(engine=_FakeOCR(text="OCR output", confidence=0.9))
        result = _result([_img("a.png", page=1), _txt("body text", page=1)])
        enhanced = await enhancer.enhance_images(result)
        assert len(enhanced) == 1
        assert enhanced[0].ocr.text == "OCR output"
        assert enhanced[0].ocr.confidence == 0.9

    @pytest.mark.asyncio
    async def test_deduplicate_ocr(self):
        fake_ocr = _FakeOCR(text="existing text\nnew text", confidence=0.9)
        enhancer = OCREnhancer(engine=fake_ocr)
        result = _result([
            _img("a.png", page=0),
            _txt("existing text", page=0),
        ])
        enhanced = await enhancer.enhance_images(result)
        assert len(enhanced) == 1
        assert "existing text" not in enhanced[0].ocr.text.lower()
        assert "new text" in enhanced[0].ocr.text.lower()

    @pytest.mark.asyncio
    async def test_image_without_path_skipped(self):
        enhancer = OCREnhancer(engine=_FakeOCR())
        item = ContentItem(type=ElementType.IMAGE, text="", page_idx=0)
        result = _result([item])
        enhanced = await enhancer.enhance_images(result)
        assert len(enhanced) == 0

    @pytest.mark.asyncio
    async def test_extra_path_field(self):
        enhancer = OCREnhancer(engine=_FakeOCR(text="from extra", confidence=0.8))
        item = ContentItem(type=ElementType.IMAGE, text="", page_idx=0, extra={"path": "extra.png"})
        result = _result([item])
        enhanced = await enhancer.enhance_images(result)
        assert len(enhanced) == 1
        assert enhanced[0].path == "extra.png"


class TestDummyVLMClient:
    @pytest.mark.asyncio
    async def test_returns_empty(self):
        client = DummyVLMClient()
        r = await client.describe_image("any.png")
        assert r.description == ""

    @pytest.mark.asyncio
    async def test_health(self):
        client = DummyVLMClient()
        assert await client.health_check() is True


class TestVLMDescriber:
    @pytest.mark.asyncio
    async def test_describe_no_images(self):
        describer = VLMDescriber(client=_FakeVLM())
        result = _result([_txt("hello")])
        enhanced = await describer.describe_images(result)
        assert len(enhanced) == 0

    @pytest.mark.asyncio
    async def test_describe_with_images(self):
        describer = VLMDescriber(client=_FakeVLM(desc="chart desc", img_type="chart"))
        result = _result([_img("a.png", page=1)])
        enhanced = await describer.describe_images(result)
        assert len(enhanced) == 1
        assert enhanced[0].vlm_description.description == "chart desc"
        assert enhanced[0].vlm_description.image_type == "chart"

    @pytest.mark.asyncio
    async def test_describe_merges_existing(self):
        existing = [EnhancedImage(path="a.png", page=1, ocr=OCRResult(text="OCR text"))]
        describer = VLMDescriber(client=_FakeVLM(desc="VLM desc"))
        result = _result([_img("a.png", page=1)])
        enhanced = await describer.describe_images(result, existing_enhanced=existing)
        assert len(enhanced) == 1
        assert enhanced[0].ocr.text == "OCR text"
        assert enhanced[0].vlm_description.description == "VLM desc"

    @pytest.mark.asyncio
    async def test_max_concurrency(self):
        describer = VLMDescriber(client=_FakeVLM(), max_concurrency=2)
        result = _result([_img(f"img{i}.png", page=i) for i in range(5)])
        enhanced = await describer.describe_images(result)
        assert len(enhanced) == 5


class TestImageEnhancer:
    @pytest.mark.asyncio
    async def test_ocr_only(self):
        config = ImageEnhancerConfig(enable_ocr=True, enable_vlm=False)
        enhancer = ImageEnhancer(ocr_engine=_FakeOCR(text="ocr"), config=config)
        result = _result([_img("a.png", page=0)])
        enhanced = await enhancer.enhance(result)
        assert len(enhanced) == 1
        assert enhanced[0].has_ocr is True
        assert enhanced[0].has_vlm_description is False

    @pytest.mark.asyncio
    async def test_vlm_only(self):
        config = ImageEnhancerConfig(enable_ocr=False, enable_vlm=True)
        enhancer = ImageEnhancer(vlm_client=_FakeVLM(desc="vlm"), config=config)
        result = _result([_img("a.png", page=0)])
        enhanced = await enhancer.enhance(result)
        assert len(enhanced) == 1
        assert enhanced[0].has_ocr is False
        assert enhanced[0].has_vlm_description is True

    @pytest.mark.asyncio
    async def test_ocr_and_vlm(self):
        config = ImageEnhancerConfig(enable_ocr=True, enable_vlm=True)
        enhancer = ImageEnhancer(
            ocr_engine=_FakeOCR(text="ocr text"),
            vlm_client=_FakeVLM(desc="vlm desc"),
            config=config,
        )
        result = _result([_img("a.png", page=0)])
        enhanced = await enhancer.enhance(result)
        assert len(enhanced) == 1
        assert enhanced[0].has_ocr is True
        assert enhanced[0].has_vlm_description is True

    @pytest.mark.asyncio
    async def test_neither_enabled_builds_basic(self):
        config = ImageEnhancerConfig(enable_ocr=False, enable_vlm=False)
        enhancer = ImageEnhancer(config=config)
        result = _result([_img("a.png", page=1, caption=["Figure 1"])])
        enhanced = await enhancer.enhance(result)
        assert len(enhanced) == 1
        assert enhanced[0].path == "a.png"
        assert enhanced[0].image_caption == ["Figure 1"]

    @pytest.mark.asyncio
    async def test_enhance_chapter_images(self):
        from doc_parser.core.chapter.models import OutlineNode

        config = ImageEnhancerConfig(enable_ocr=True, enable_vlm=False)
        enhancer = ImageEnhancer(ocr_engine=_FakeOCR(text="ocr"), config=config)
        result = _result([_img("a.png", page=0), _img("b.png", page=5)])
        enhanced = await enhancer.enhance(result)

        chapter = OutlineNode(id="ch_0", title="Ch1", level=1, page_start=0, page_end=1)
        chapter = await enhancer.enhance_chapter_images(chapter, result, enhanced)
        assert "images" in chapter.metadata
        assert len(chapter.metadata["images"]) == 1
