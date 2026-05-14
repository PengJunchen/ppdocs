
#!/usr/bin/env python3
"""
演示 TOC 提取如何直接分析标题文本
"""

import json
import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from doc_parser.core.chapter.toc import StrategyA_TitleAggregation
from doc_parser.pipeline.base import PipelineResult, ContentItem, ElementType


def load_mineru_data(filepath):
    """加载 MinerU 原始数据"""
    with open(filepath, encoding="utf-8") as f:
        data = json.load(f)
    
    results = data.get("results", {})
    file_name = list(results.keys())[0]
    file_data = results[file_name]
    
    # content_list 可能是 JSON 字符串
    content_list_str = file_data.get("content_list", "")
    if isinstance(content_list_str, str):
        content_list_raw = json.loads(content_list_str)
    else:
        content_list_raw = content_list_str
    
    return content_list_raw


def create_pipeline_result(content_list_raw):
    """创建 PipelineResult 对象"""
    content_items = []
    for item in content_list_raw:
        content_items.append(ContentItem(
            type=ElementType(item.get("type", "text")),
            text=item.get("text", ""),
            text_level=item.get("text_level", 0),
            page_idx=item.get("page_idx", 0),
            reading_order=item.get("reading_order", 0),
        ))
    
    return PipelineResult(
        document_id="deepseek-v4",
        content_list=content_items,
    )


def analyze_title_patterns(content_list_raw):
    """分析标题文本模式"""
    print("=" * 80)
    print("【步骤1】分析原始标题数据")
    print("=" * 80)
    
    headings = []
    for item in content_list_raw:
        text_level = item.get("text_level", 0)
        if text_level > 0:
            headings.append({
                "text": item.get("text", ""),
                "text_level": text_level,
                "page_idx": item.get("page_idx", 0),
            })
    
    print(f"发现 {len(headings)} 个标题元素")
    print("\n原始标题示例（前10个）:")
    print("-" * 60)
    for i, h in enumerate(headings[:10]):
        print(f"[{i:2d}] text_level={h['text_level']} page={h['page_idx']}")
        print(f"    标题: {h['text']}")
    
    return headings


def demonstrate_level_inference(headings):
    """演示层级推断过程"""
    print("\n" + "=" * 80)
    print("【步骤2】演示标题层级推断")
    print("=" * 80)
    
    # 导入用于演示的函数
    import re
    
    def extract_level(title):
        """从标题文本推断层级"""
        # 模式1: 数字编号 "1.", "2.3.", "2.3.1."
        number_pattern = re.compile(r'^(\d+)(?:\.\d+)*\.\s*')
        match = number_pattern.match(title)
        if match:
            num_str = match.group(0).rstrip('. ')
            level = num_str.count('.') + 1
            return level, "数字编号"
        
        # 模式2: 字母编号 "A.", "A.1."
        letter_pattern = re.compile(r'^([A-Za-z])(?:\.\d+)*\.\s*')
        letter_match = letter_pattern.match(title)
        if letter_match:
            num_str = letter_match.group(0).rstrip('. ')
            level = num_str.count('.') + 1
            return level, "字母编号"
        
        # 模式3: 特殊标题
        lower_title = title.lower()
        level1_patterns = [r'^abstract', r'^introduction', r'^conclusion', 
                            r'^references', r'^appendix', r'^contents?']
        for pattern in level1_patterns:
            if re.match(pattern, lower_title):
                return 1, "特殊标题"
        
        # 默认级别
        return 2, "其他标题"
    
    print("层级推断示例:")
    print("-" * 60)
    print(f"{'标题':<50} {'推断层级':<10} {'识别模式'}")
    print("-" * 80)
    
    sample_titles = [
        "1. Introduction",
        "2.3. Hybrid Attention with CSA and HCA",
        "2.3.1. Compressed Sparse Attention",
        "Abstract",
        "References",
        "A. Author List",
        "A.1. Author List",
        "Summary of Core Evaluation Results",
    ]
    
    for title in sample_titles:
        level, pattern = extract_level(title)
        print(f"{title:<50} {level:<10} {pattern}")


def run_toc_extraction(result):
    """运行完整的 TOC 提取"""
    print("\n" + "=" * 80)
    print("【步骤3】运行 TOC 提取")
    print("=" * 80)
    
    strategy = StrategyA_TitleAggregation()
    import asyncio
    outline = asyncio.run(strategy.extract(result))
    
    print(f"提取完成！共 {len(outline.nodes)} 个根节点")
    print(f"总章节数: {outline.total_chapters}")
    
    return outline


def print_toc_tree(outline):
    """打印 TOC 树形结构"""
    print("\n" + "=" * 80)
    print("【步骤4】输出最终 TOC 结构")
    print("=" * 80)
    
    def print_tree(nodes, indent=0):
        for node in nodes:
            prefix = "  " * indent
            level_marker = "├─" if indent > 0 else ""
            print(f"{prefix}{level_marker}[L{node.level}] {node.title}")
            if node.children:
                print_tree(node.children, indent + 1)
    
    print_tree(outline.nodes)
    
    # 输出统计信息
    all_chapters = outline.get_all_chapters()
    level_counts = {}
    for ch in all_chapters:
        level_counts[ch.level] = level_counts.get(ch.level, 0) + 1
    
    print("\n章节层级分布:")
    for level in sorted(level_counts.keys()):
        print(f"  Level {level}: {level_counts[level]} 个章节")


def main():
    # 加载测试数据
    mineru_path = Path(r"e:\Work\PJC\Github\ppdocs\PDFTest\DeepSeek_V4_pdf_mineru_3.json")
    
    if not mineru_path.exists():
        print(f"错误: 测试数据文件不存在: {mineru_path}")
        sys.exit(1)
    
    print("=" * 80)
    print("TOC 提取演示 - DeepSeek-V4 论文")
    print("=" * 80)
    print(f"数据源: {mineru_path.name}")
    print("\n")
    
    # 步骤1: 分析原始数据
    content_list_raw = load_mineru_data(mineru_path)
    headings = analyze_title_patterns(content_list_raw)
    
    # 步骤2: 演示层级推断
    demonstrate_level_inference(headings)
    
    # 步骤3: 创建 PipelineResult 并提取 TOC
    result = create_pipeline_result(content_list_raw)
    outline = run_toc_extraction(result)
    
    # 步骤4: 输出结果
    print_toc_tree(outline)
    
    print("\n" + "=" * 80)
    print("✅ TOC 提取演示完成")
    print("=" * 80)


if __name__ == "__main__":
    main()
