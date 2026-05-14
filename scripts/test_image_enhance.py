#!/usr/bin/env python3
"""
测试图片增强功能 - 支持 PNG/JPG 直接上传
"""

import asyncio
import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from doc_parser.core.image import ImageEnhancer, ImageEnhancerConfig
from doc_parser.core.image.ocr_enhance import MinerUOCREngine, DummyOCREngine
from doc_parser.core.image.vlm_describe import OpenAICompatibleVLM, DummyVLMClient
from doc_parser.pipeline.base import PipelineResult, ContentItem, ElementType


async def test_image_enhancer_init():
    """测试 ImageEnhancer 初始化"""
    print(f"\n{'='*60}")
    print("测试 ImageEnhancer 初始化")
    print(f"{'='*60}")
    
    # 测试1: 仅 OCR
    config1 = ImageEnhancerConfig(enable_ocr=True, enable_vlm=False)
    enhancer1 = ImageEnhancer(config=config1)
    print(f"✓ 仅 OCR 模式: ocr_enhancer={enhancer1._ocr_enhancer is not None}, vlm_describer={enhancer1._vlm_describer is not None}")
    
    # 测试2: 仅 VLM
    config2 = ImageEnhancerConfig(enable_ocr=False, enable_vlm=True)
    enhancer2 = ImageEnhancer(config=config2)
    print(f"✓ 仅 VLM 模式: ocr_enhancer={enhancer2._ocr_enhancer is not None}, vlm_describer={enhancer2._vlm_describer is not None}")
    
    # 测试3: OCR + VLM
    config3 = ImageEnhancerConfig(enable_ocr=True, enable_vlm=True)
    enhancer3 = ImageEnhancer(config=config3)
    print(f"✓ OCR+VLM 模式: ocr_enhancer={enhancer3._ocr_enhancer is not None}, vlm_describer={enhancer3._vlm_describer is not None}")
    
    # 测试4: 无增强
    config4 = ImageEnhancerConfig(enable_ocr=False, enable_vlm=False)
    enhancer4 = ImageEnhancer(config=config4)
    print(f"✓ 无增强模式: ocr_enhancer={enhancer4._ocr_enhancer is not None}, vlm_describer={enhancer4._vlm_describer is not None}")


async def test_pipeline_result_creation():
    """测试 PipelineResult 创建（模拟图片上传）"""
    print(f"\n{'='*60}")
    print("测试 PipelineResult 创建（模拟图片上传）")
    print(f"{'='*60}")
    
    # 模拟 PNG 文件上传
    content_item = ContentItem(
        type=ElementType.IMAGE,
        text="",
        img_path="/tmp/test.png",
        page_idx=0,
        reading_order=0,
    )
    result = PipelineResult(
        document_id="test-image.png",
        content_list=[content_item],
    )
    
    print(f"✓ 创建 PipelineResult: document_id={result.document_id}")
    print(f"✓ 内容数量: {len(result.content_list)}")
    print(f"✓ 图片类型: {result.content_list[0].type}")


async def test_enhance_with_dummy():
    """使用 Dummy 引擎测试增强流程"""
    print(f"\n{'='*60}")
    print("测试增强流程（使用 Dummy 引擎）")
    print(f"{'='*60}")
    
    # 创建模拟的 PipelineResult
    content_item = ContentItem(
        type=ElementType.IMAGE,
        text="",
        img_path="/tmp/test.png",
        page_idx=0,
        reading_order=0,
    )
    result = PipelineResult(
        document_id="test-image",
        content_list=[content_item],
    )
    
    # 使用 Dummy 引擎测试
    config = ImageEnhancerConfig(enable_ocr=True, enable_vlm=True)
    ocr_engine = DummyOCREngine()
    vlm_client = DummyVLMClient()
    enhancer = ImageEnhancer(config=config, ocr_engine=ocr_engine, vlm_client=vlm_client)
    
    enhanced = await enhancer.enhance(result)
    
    print(f"✓ 增强完成！共 {len(enhanced)} 张图片")
    for ei in enhanced:
        print(f"  路径: {ei.path}")
        print(f"  页码: {ei.page}")
        print(f"  有 OCR: {ei.has_ocr}")
        print(f"  有 VLM 描述: {ei.has_vlm_description}")


async def test_file_type_detection():
    """测试文件类型检测逻辑"""
    print(f"\n{'='*60}")
    print("测试文件类型检测")
    print(f"{'='*60}")
    
    image_extensions = {"png", "jpg", "jpeg", "gif", "bmp", "webp"}
    
    test_files = [
        "test.pdf",
        "image.png",
        "photo.jpg",
        "picture.jpeg",
        "chart.gif",
        "diagram.bmp",
        "graph.webp",
        "document.docx",
    ]
    
    for filename in test_files:
        file_ext = filename.split(".")[-1].lower()
        is_image = file_ext in image_extensions
        print(f"  {'✓' if is_image else '✗'} {filename}: {'图片文件' if is_image else '非图片文件'}")


async def main():
    print(f"{'='*60}")
    print("图片增强功能测试")
    print(f"{'='*60}")
    
    await test_image_enhancer_init()
    await test_pipeline_result_creation()
    await test_enhance_with_dummy()
    await test_file_type_detection()
    
    print(f"\n{'='*60}")
    print("✅ 图片增强测试全部完成")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
