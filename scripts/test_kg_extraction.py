import asyncio
from doc_parser.core.kg import LLMKGBridge

class MockLLM:
    async def chat(self, messages, **kwargs):
        return '{\"entities\": [{\"name\": \"张三\", \"type\": \"人物\", \"description\": \"项目经理\"}, {\"name\": \"AI系统\", \"type\": \"技术\", \"description\": \"智能文档处理系统\"}], \"relations\": [{\"source\": \"张三\", \"target\": \"AI系统\", \"relation_type\": \"开发了\", \"description\": \"张三开发了AI系统\"}]}'

async def test_kg_extraction():
    bridge = LLMKGBridge(llm_client=MockLLM())
    result = await bridge.insert('张三开发了AI系统')
    print(f'实体数: {result.total_entities}')
    print(f'关系数: {result.total_relations}')
    print(f'存储的实体: {[e["name"] for e in bridge.entities]}')
    print(f'存储的关系: {[(r["source"], r["relation_type"], r["target"]) for r in bridge.relations]}')

if __name__ == '__main__':
    asyncio.run(test_kg_extraction())