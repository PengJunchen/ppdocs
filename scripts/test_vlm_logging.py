"""测试 VLM 日志输出"""
import asyncio
import os
import sys
import logging

# 设置日志级别
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from doc_parser.core.image.vlm_describe import OpenAICompatibleVLM, _VLM_PROMPT

async def test_vlm_logging():
    """测试 VLM 日志输出"""
    print("=" * 60)
    print("测试 VLM 日志输出")
    print("=" * 60)
    
    # 创建 VLM 客户端（使用无效的 URL 来测试日志）
    vlm = OpenAICompatibleVLM(
        base_url="http://localhost:8080/v1",
        api_key="test-key",
        model="qwen-vl-max"
    )
    
    # 创建一个简单的测试图片（空的 base64 数据）
    test_image_path = "tests/fixtures/test_image.png"
    
    # 检查测试图片是否存在
    if not os.path.exists(test_image_path):
        # 创建一个临时的测试文件
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            # 写入一些测试数据（不是有效的 PNG）
            f.write(b"test")
            test_image_path = f.name
    
    print(f"\n测试图片路径: {test_image_path}")
    print(f"提示词内容:\n{_VLM_PROMPT}")
    
    # 测试 describe_image
    print("\n" + "=" * 60)
    print("开始调用 VLM describe_image...")
    print("=" * 60)
    
    result = await vlm.describe_image(test_image_path)
    
    print("\n" + "=" * 60)
    print(f"VLM 返回结果:")
    print(f"  model: {result.model}")
    print(f"  description: {result.description[:200]}..." if len(result.description) > 200 else f"  description: {result.description}")
    print(f"  image_type: {result.image_type}")
    print(f"  key_info: {result.key_info}")
    print("=" * 60)
    
    # 清理临时文件
    if "tmp" in test_image_path:
        os.unlink(test_image_path)

if __name__ == "__main__":
    asyncio.run(test_vlm_logging())