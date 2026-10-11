"""
Phase 3: Neo4j In-Memory & Live Graph Processing Staging Engine.
Acts as the platform's high-speed topological staging and structural computational memory.
"""

from __future__ import annotations
from typing import List, Dict, Any, Optional, Tuple
import networkx as nx
from savi.graph.triplet_extractor import Triplet
from savi.graph.louvain import LouvainCommunityDetector
from savi.ingestion.schema import ScrapedPayload


class Neo4jStagingGraph:
    """
    Topological Staging and In-Memory Graph Processing Engine.
    Handles entity nodes, triplet relationships, citation networks,
    and topological betweenness centrality metrics.
    """
    def __init__(self):
        self.graph = nx.Graph()
        self.payload_nodes: Dict[str, ScrapedPayload] = {}
        self.triplets: List[Triplet] = []
        self.community_detector = LouvainCommunityDetector()

    def add_payload(self, payload: ScrapedPayload, triplets: List[Triplet]) -> None:
        """Stages content payload and its SPO triplets in the topological graph."""
        content_id = payload.content_id
        self.payload_nodes[content_id] = payload

        # Add content node
        self.graph.add_node(
            content_id,
            node_type="Content",
            platform=payload.origin_platform,
            title=payload.headline_or_title,
        )

        # Add author node and edge
        author_id = payload.author.author_id
        self.graph.add_node(author_id, node_type="Author", username=payload.author.username)
        self.graph.add_edge(author_id, content_id, relation="AUTHORED", weight=1.0)

        # Add platform node and edge
        platform_id = f"platform_{payload.origin_platform}"
        self.graph.add_node(platform_id, node_type="Platform", name=payload.origin_platform)
        self.graph.add_edge(content_id, platform_id, relation="PUBLISHED_ON", weight=1.0)

        # Add citations as edges
        for cit in payload.citations:
            cit_id = f"citation_{cit}"
            self.graph.add_node(cit_id, node_type="Citation", url=cit)
            self.graph.add_edge(content_id, cit_id, relation="CITES", weight=1.5)

        # Add SPO triplets
        for trip in triplets:
            self.triplets.append(trip)
            s_node = f"entity_{trip.subject.lower()}"
            o_node = f"entity_{trip.object.lower()}"

            self.graph.add_node(s_node, node_type="Entity", label=trip.subject)
            self.graph.add_node(o_node, node_type="Entity", label=trip.object)

            # Edge between subject and object with predicate label
            self.graph.add_edge(s_node, o_node, relation=trip.predicate, weight=trip.confidence)
            # Connect content node to subject entity
            self.graph.add_edge(content_id, s_node, relation="MENTIONS", weight=1.0)

    def compute_betweenness_centrality(self) -> Dict[str, float]:
        """
        Computes betweenness centrality C_B for all nodes in the topology:
        C_B(v) = sum_{s != v != t} (sigma_{st}(v) / sigma_{st})
        """
        if self.graph.number_of_nodes() <= 2:
            return {node: 1.0 for node in self.graph.nodes()}
        return nx.betweenness_centrality(self.graph, weight="weight")

    def run_louvain_communities(self) -> Tuple[Dict[str, int], float]:
        """Runs Louvain modularity optimization across current topology."""
        return self.community_detector.detect_communities(self.graph)

    def find_evidence_triplets_for_claim(self, claim: Triplet) -> List[Triplet]:
        """Discovers supporting or contradicting evidence triplets in graph staging."""
        evidence = []
        subj_clean = claim.subject.lower()
        obj_clean = claim.object.lower()

        for trip in self.triplets:
            if trip == claim:
                continue
            # Overlap in subject or object
            if (trip.subject.lower() == subj_clean) or (trip.object.lower() == obj_clean):
                evidence.append(trip)

        return evidence[:5]
