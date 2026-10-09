"""
Topology Graph Engine using NetworkX.
Maintains dependencies between microservices to trace cascade failure blast radiuses.
"""

from typing import Dict, List, Set
import networkx as nx

from src.models.topology import ServiceNode, TopologyEdge, ServiceTopology


class TopologyEngine:
    def __init__(self):
        self.graph = nx.DiGraph()
        self.service_metadata: Dict[str, ServiceNode] = {}
        self._initialize_enterprise_topology()

    def _initialize_enterprise_topology(self):
        """Build standard simulated enterprise e-commerce microservice graph."""
        nodes = [
            ServiceNode(
                id="auth-service",
                name="Auth Service",
                tier="security",
                description="Token issuance, authentication & authorization",
                dependencies=[],
                icon="shield",
            ),
            ServiceNode(
                id="inventory-service",
                name="Inventory Service",
                tier="catalog",
                description="Stock levels, product reservation, warehouse sync",
                dependencies=[],
                icon="archive",
            ),
            ServiceNode(
                id="payment-service",
                name="Payment Service",
                tier="financial",
                description="Credit card processing, gateway settlements, refunds",
                dependencies=[],
                icon="credit-card",
            ),
            ServiceNode(
                id="order-service",
                name="Order Service",
                tier="orchestrator",
                description="Core order lifecycle. Depends on Auth, Inventory, and Payment",
                dependencies=["auth-service", "inventory-service", "payment-service"],
                icon="shopping-cart",
            ),
            ServiceNode(
                id="notification-service",
                name="Notification Service",
                tier="messaging",
                description="SMS, emails, dispatch tracking. Consumes Order updates",
                dependencies=["order-service"],
                icon="bell",
            ),
        ]

        for node in nodes:
            self.service_metadata[node.id] = node
            self.graph.add_node(node.id, **node.model_dump())

        # Directed edge: Source CALLS Target (Target is dependency of Source)
        edges = [
            ("order-service", "auth-service"),
            ("order-service", "inventory-service"),
            ("order-service", "payment-service"),
            ("notification-service", "order-service"),
        ]

        for src, target in edges:
            self.graph.add_edge(src, target)

    def get_topology(self) -> ServiceTopology:
        """Returns serializable topology representation."""
        nodes = list(self.service_metadata.values())
        edges = [
            TopologyEdge(source=u, target=v, relation="calls")
            for u, v in self.graph.edges()
        ]
        return ServiceTopology(nodes=nodes, edges=edges)

    def get_downstream_dependencies(self, service_id: str) -> List[str]:
        """Services that `service_id` depends on (calls directly or transitively)."""
        if service_id not in self.graph:
            return []
        # Successors in calls graph are the dependencies
        return list(self.graph.successors(service_id))

    def get_affected_dependents(self, service_id: str) -> List[str]:
        """
        Services that depend on `service_id` (upstream callers).
        If `service_id` fails, these callers will experience cascading degradation.
        """
        if service_id not in self.graph:
            return []
        # Predecessors in calls graph are callers that depend on this service
        direct_callers = list(self.graph.predecessors(service_id))
        all_affected: Set[str] = set()
        
        # Traverse reverse graph to find all upstream affected nodes
        rev_graph = self.graph.reverse()
        if service_id in rev_graph:
            descendants = nx.descendants(rev_graph, service_id)
            all_affected.update(descendants)
            
        return list(all_affected)

    def is_service_registered(self, service_id: str) -> bool:
        return service_id in self.graph


topology_engine = TopologyEngine()
