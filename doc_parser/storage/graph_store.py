from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class GraphNode(BaseModel):
    id: str = ""
    label: str = ""
    properties: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    id: str = ""
    source: str = ""
    target: str = ""
    label: str = ""
    properties: dict[str, Any] = Field(default_factory=dict)


class GraphQueryResult(BaseModel):
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    raw_result: Any = None


class BaseGraphStore(ABC):
    @abstractmethod
    async def add_node(self, node: GraphNode) -> bool:
        ...

    @abstractmethod
    async def add_edge(self, edge: GraphEdge) -> bool:
        ...

    @abstractmethod
    async def query(
        self,
        query_text: str,
        params: Optional[dict[str, Any]] = None,
    ) -> GraphQueryResult:
        ...

    @abstractmethod
    async def get_node(self, node_id: str) -> Optional[GraphNode]:
        ...

    @abstractmethod
    async def get_neighbors(
        self, node_id: str, direction: str = "both"
    ) -> list[GraphNode]:
        ...

    @abstractmethod
    async def delete_document(self, document_id: str) -> bool:
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        ...


class InMemoryGraphStore(BaseGraphStore):
    def __init__(self) -> None:
        self._nodes: dict[str, GraphNode] = {}
        self._edges: dict[str, GraphEdge] = {}
        self._adjacency: dict[str, list[str]] = {}

    async def add_node(self, node: GraphNode) -> bool:
        self._nodes[node.id] = node
        if node.id not in self._adjacency:
            self._adjacency[node.id] = []
        return True

    async def add_edge(self, edge: GraphEdge) -> bool:
        self._edges[edge.id] = edge
        if edge.source not in self._adjacency:
            self._adjacency[edge.source] = []
        if edge.target not in self._adjacency:
            self._adjacency[edge.target] = []
        self._adjacency[edge.source].append(edge.target)
        self._adjacency[edge.target].append(edge.source)
        return True

    async def query(
        self,
        query_text: str,
        params: Optional[dict[str, Any]] = None,
    ) -> GraphQueryResult:
        keyword = query_text.lower().strip()
        if not keyword:
            return GraphQueryResult(
                nodes=list(self._nodes.values()),
                edges=list(self._edges.values()),
            )

        matched_nodes: list[GraphNode] = []
        for node in self._nodes.values():
            if keyword in node.id.lower() or keyword in node.label.lower():
                matched_nodes.append(node)
                continue
            for v in node.properties.values():
                if isinstance(v, str) and keyword in v.lower():
                    matched_nodes.append(node)
                    break

        matched_node_ids = {n.id for n in matched_nodes}
        matched_edges: list[GraphEdge] = []
        for edge in self._edges.values():
            if edge.source in matched_node_ids or edge.target in matched_node_ids:
                matched_edges.append(edge)

        return GraphQueryResult(nodes=matched_nodes, edges=matched_edges)

    async def get_node(self, node_id: str) -> Optional[GraphNode]:
        return self._nodes.get(node_id)

    async def get_neighbors(
        self, node_id: str, direction: str = "both"
    ) -> list[GraphNode]:
        neighbor_ids = set(self._adjacency.get(node_id, []))
        if direction == "outgoing":
            neighbor_ids = set()
            for edge in self._edges.values():
                if edge.source == node_id:
                    neighbor_ids.add(edge.target)
        elif direction == "incoming":
            neighbor_ids = set()
            for edge in self._edges.values():
                if edge.target == node_id:
                    neighbor_ids.add(edge.source)

        return [
            self._nodes[nid]
            for nid in neighbor_ids
            if nid in self._nodes
        ]

    async def delete_document(self, document_id: str) -> bool:
        node_ids_to_delete = set()
        edge_ids_to_delete = set()

        for nid, node in self._nodes.items():
            if node.properties.get("document_id") == document_id:
                node_ids_to_delete.add(nid)

        for eid, edge in self._edges.items():
            if edge.source in node_ids_to_delete or edge.target in node_ids_to_delete:
                edge_ids_to_delete.add(eid)

        for eid in edge_ids_to_delete:
            del self._edges[eid]

        for nid in node_ids_to_delete:
            del self._nodes[nid]
            self._adjacency.pop(nid, None)

        for nid, neighbors in self._adjacency.items():
            self._adjacency[nid] = [
                n for n in neighbors if n not in node_ids_to_delete
            ]

        return len(node_ids_to_delete) > 0 or len(edge_ids_to_delete) > 0

    async def health_check(self) -> bool:
        return True


class Neo4jGraphStore(BaseGraphStore):
    def __init__(
        self,
        uri: str = "bolt://localhost:7687",
        username: str = "neo4j",
        password: str = "",
        database: str = "neo4j",
    ):
        self._uri = uri
        self._username = username
        self._password = password
        self._database = database
        self._driver: Any = None

    def _get_driver(self) -> Any:
        if self._driver is not None:
            return self._driver

        try:
            from neo4j import GraphDatabase

            self._driver = GraphDatabase.driver(
                self._uri, auth=(self._username, self._password)
            )
            return self._driver
        except ImportError:
            raise ImportError(
                "neo4j is not installed. Install with: uv pip install neo4j"
            )

    async def add_node(self, node: GraphNode) -> bool:
        driver = self._get_driver()
        try:
            def _sync():
                with driver.session(database=self._database) as session:
                    props = dict(node.properties)
                    props["label"] = node.label
                    session.run(
                        "MERGE (n {id: $id}) SET n += $props",
                        id=node.id,
                        props=props,
                    )
            await asyncio.to_thread(_sync)
            return True
        except Exception as exc:
            logger.warning("Neo4j add_node failed: %s", exc)
            return False

    async def add_edge(self, edge: GraphEdge) -> bool:
        driver = self._get_driver()
        try:
            def _sync():
                with driver.session(database=self._database) as session:
                    session.run(
                        "MATCH (a {id: $source}), (b {id: $target}) "
                        "MERGE (a)-[r:RELATES {id: $edge_id}]->(b) "
                        "SET r += $props",
                        source=edge.source,
                        target=edge.target,
                        edge_id=edge.id,
                        props=edge.properties,
                    )
            await asyncio.to_thread(_sync)
            return True
        except Exception as exc:
            logger.warning("Neo4j add_edge failed: %s", exc)
            return False

    async def query(
        self,
        query_text: str,
        params: Optional[dict[str, Any]] = None,
    ) -> GraphQueryResult:
        driver = self._get_driver()
        try:
            def _sync():
                with driver.session(database=self._database) as session:
                    result = session.run(query_text, params or {})
                    nodes: list[GraphNode] = []
                    edges: list[GraphEdge] = []
                    for record in result:
                        for value in record.values():
                            if hasattr(value, "items"):
                                node = GraphNode(
                                    id=value.get("id", ""),
                                    label=value.get("label", ""),
                                    properties=dict(value),
                                )
                                nodes.append(node)
                    return GraphQueryResult(nodes=nodes, edges=edges)
            return await asyncio.to_thread(_sync)
        except Exception as exc:
            logger.warning("Neo4j query failed: %s", exc)
            return GraphQueryResult()

    async def get_node(self, node_id: str) -> Optional[GraphNode]:
        driver = self._get_driver()
        try:
            def _sync():
                with driver.session(database=self._database) as session:
                    result = session.run(
                        "MATCH (n {id: $id}) RETURN n LIMIT 1", id=node_id
                    )
                    record = result.single()
                    if record:
                        node_data = dict(record["n"])
                        return GraphNode(
                            id=node_data.pop("id", node_id),
                            label=node_data.pop("label", ""),
                            properties=node_data,
                        )
                    return None
            return await asyncio.to_thread(_sync)
        except Exception as exc:
            logger.warning("Neo4j get_node failed: %s", exc)
            return None

    async def get_neighbors(
        self, node_id: str, direction: str = "both"
    ) -> list[GraphNode]:
        driver = self._get_driver()
        try:
            def _sync():
                with driver.session(database=self._database) as session:
                    if direction == "outgoing":
                        cypher = "MATCH (a {id: $id})-->(b) RETURN b"
                    elif direction == "incoming":
                        cypher = "MATCH (a {id: $id})<--(b) RETURN b"
                    else:
                        cypher = "MATCH (a {id: $id})--(b) RETURN b"

                    result = session.run(cypher, id=node_id)
                    neighbors: list[GraphNode] = []
                    for record in result:
                        node_data = dict(record["b"])
                        neighbors.append(GraphNode(
                            id=node_data.pop("id", ""),
                            label=node_data.pop("label", ""),
                            properties=node_data,
                        ))
                    return neighbors
            return await asyncio.to_thread(_sync)
        except Exception as exc:
            logger.warning("Neo4j get_neighbors failed: %s", exc)
            return []

    async def delete_document(self, document_id: str) -> bool:
        driver = self._get_driver()
        try:
            def _sync():
                with driver.session(database=self._database) as session:
                    session.run(
                        "MATCH (n {document_id: $doc_id}) DETACH DELETE n",
                        doc_id=document_id,
                    )
            await asyncio.to_thread(_sync)
            return True
        except Exception as exc:
            logger.warning("Neo4j delete_document failed: %s", exc)
            return False

    async def health_check(self) -> bool:
        try:
            driver = self._get_driver()
            def _sync():
                with driver.session(database=self._database) as session:
                    session.run("RETURN 1")
            await asyncio.to_thread(_sync)
            return True
        except Exception:
            return False
