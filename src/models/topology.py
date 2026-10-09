"""
Topology graph models for interconnected enterprise services.
Captures upstream and downstream dependencies for cascade tracking.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class ServiceTier(str):
    FRONTEND = "frontend"
    BUSINESS_LOGIC = "business_logic"
    INTEGRATION = "integration"
    DATA_STORE = "data_store"


class ServiceNode(BaseModel):
    id: str = Field(..., min_length=2, max_length=64)
    name: str = Field(..., min_length=2, max_length=64)
    tier: str = Field(default="business_logic")
    description: str = Field(default="")
    dependencies: List[str] = Field(default_factory=list, description="Downstream services this service calls")
    icon: Optional[str] = "server"


class TopologyEdge(BaseModel):
    source: str
    target: str
    relation: str = "calls"


class ServiceTopology(BaseModel):
    nodes: List[ServiceNode]
    edges: List[TopologyEdge]
