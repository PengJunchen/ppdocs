from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field, computed_field


class OutlineNode(BaseModel):
    id: str = ""
    title: str = ""
    level: int = 1
    page_start: int = 0
    page_end: Optional[int] = None
    parent_id: Optional[str] = None
    children: list[OutlineNode] = Field(default_factory=list)

    element_indices: list[int] = Field(default_factory=list)
    markdown: str = ""
    image_count: int = 0
    table_count: int = 0
    equation_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)

    def get_all_descendants(self) -> list[OutlineNode]:
        result: list[OutlineNode] = []
        for child in self.children:
            result.append(child)
            result.extend(child.get_all_descendants())
        return result

    def is_leaf(self) -> bool:
        return len(self.children) == 0


class DocumentOutline(BaseModel):
    document_id: str = ""
    title: str = ""
    nodes: list[OutlineNode] = Field(default_factory=list)

    @computed_field
    @property
    def total_chapters(self) -> int:
        return len(self.get_all_chapters())

    def get_all_chapters(self) -> list[OutlineNode]:
        result: list[OutlineNode] = []

        def _flatten(node_list: list[OutlineNode]) -> None:
            for node in node_list:
                result.append(node)
                _flatten(node.children)

        _flatten(self.nodes)
        return result

    def get_chapter_by_page(self, page_num: int) -> Optional[OutlineNode]:
        for chapter in self.get_all_chapters():
            end = chapter.page_end if chapter.page_end is not None else page_num
            if chapter.page_start <= page_num <= end:
                return chapter
        return None

    def get_leaf_chapters(self) -> list[OutlineNode]:
        return [ch for ch in self.get_all_chapters() if ch.is_leaf()]

    def to_tree_dict(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)
