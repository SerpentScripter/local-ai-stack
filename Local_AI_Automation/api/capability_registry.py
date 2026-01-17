"""
Agent Capability Registry
Dynamic registration and matching of agent capabilities

Provides:
- Capability declaration and registration
- Task-to-agent matching
- Capability versioning
- Dependency resolution
"""
import re
from datetime import datetime
from typing import Optional, Dict, Any, List, Set, Type, Callable
from dataclasses import dataclass, field
from enum import Enum

from .agent_base import BaseAgent
from .logging_config import api_logger


class CapabilityType(Enum):
    """Types of capabilities agents can have"""
    RESEARCH = "research"           # Information gathering
    ANALYSIS = "analysis"           # Data analysis
    GENERATION = "generation"       # Content generation
    CODE = "code"                   # Code operations
    COMMUNICATION = "communication" # Messaging, notifications
    FILE = "file"                   # File operations
    WEB = "web"                     # Web interactions
    DATABASE = "database"           # Database operations
    CUSTOM = "custom"               # Custom capabilities


@dataclass
class Capability:
    """Definition of a single capability"""
    name: str
    type: CapabilityType
    description: str
    version: str = "1.0.0"
    input_schema: Optional[Dict[str, Any]] = None
    output_schema: Optional[Dict[str, Any]] = None
    dependencies: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    cost: float = 1.0  # Relative cost (for optimization)
    reliability: float = 1.0  # Success rate (0-1)


@dataclass
class AgentCapabilities:
    """Collection of capabilities for an agent"""
    agent_class: Type[BaseAgent]
    agent_type: str
    capabilities: List[Capability]
    registered_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskRequirement:
    """Requirements for a task to match capabilities"""
    capability_name: Optional[str] = None
    capability_type: Optional[CapabilityType] = None
    tags: List[str] = field(default_factory=list)
    min_reliability: float = 0.0
    max_cost: float = float('inf')
    required_input: Optional[Dict[str, Any]] = None


@dataclass
class MatchResult:
    """Result of capability matching"""
    agent_type: str
    agent_class: Type[BaseAgent]
    capability: Capability
    score: float  # Match quality (0-1)
    reasons: List[str] = field(default_factory=list)


class CapabilityRegistry:
    """
    Central registry for agent capabilities

    Agents register their capabilities, and the registry
    helps find the best agent for a given task.
    """

    def __init__(self):
        self._agents: Dict[str, AgentCapabilities] = {}
        self._capability_index: Dict[str, Set[str]] = {}  # capability_name -> agent_types
        self._type_index: Dict[CapabilityType, Set[str]] = {}
        self._tag_index: Dict[str, Set[str]] = {}

    # ==================== Registration ====================

    def register_agent(
        self,
        agent_class: Type[BaseAgent],
        capabilities: List[Capability],
        agent_type: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Register an agent with its capabilities

        Args:
            agent_class: The agent class
            capabilities: List of capabilities the agent provides
            agent_type: Optional type identifier (default: class name)
            metadata: Optional additional metadata

        Returns:
            Agent type string
        """
        agent_type = agent_type or agent_class.__name__

        agent_caps = AgentCapabilities(
            agent_class=agent_class,
            agent_type=agent_type,
            capabilities=capabilities,
            metadata=metadata or {}
        )

        self._agents[agent_type] = agent_caps

        # Update indexes
        for cap in capabilities:
            # Name index
            if cap.name not in self._capability_index:
                self._capability_index[cap.name] = set()
            self._capability_index[cap.name].add(agent_type)

            # Type index
            if cap.type not in self._type_index:
                self._type_index[cap.type] = set()
            self._type_index[cap.type].add(agent_type)

            # Tag index
            for tag in cap.tags:
                if tag not in self._tag_index:
                    self._tag_index[tag] = set()
                self._tag_index[tag].add(agent_type)

        api_logger.info(f"Registered agent '{agent_type}' with {len(capabilities)} capabilities")
        return agent_type

    def unregister_agent(self, agent_type: str) -> bool:
        """Remove an agent from the registry"""
        if agent_type not in self._agents:
            return False

        agent_caps = self._agents[agent_type]

        # Remove from indexes
        for cap in agent_caps.capabilities:
            if cap.name in self._capability_index:
                self._capability_index[cap.name].discard(agent_type)
            if cap.type in self._type_index:
                self._type_index[cap.type].discard(agent_type)
            for tag in cap.tags:
                if tag in self._tag_index:
                    self._tag_index[tag].discard(agent_type)

        del self._agents[agent_type]
        return True

    def register_capability(
        self,
        agent_type: str,
        capability: Capability
    ) -> bool:
        """Add a capability to an existing agent"""
        if agent_type not in self._agents:
            return False

        self._agents[agent_type].capabilities.append(capability)

        # Update indexes
        if capability.name not in self._capability_index:
            self._capability_index[capability.name] = set()
        self._capability_index[capability.name].add(agent_type)

        if capability.type not in self._type_index:
            self._type_index[capability.type] = set()
        self._type_index[capability.type].add(agent_type)

        for tag in capability.tags:
            if tag not in self._tag_index:
                self._tag_index[tag] = set()
            self._tag_index[tag].add(agent_type)

        return True

    # ==================== Querying ====================

    def find_agents(
        self,
        requirement: TaskRequirement
    ) -> List[MatchResult]:
        """
        Find agents matching a task requirement

        Args:
            requirement: Task requirements to match

        Returns:
            List of MatchResult sorted by score (best first)
        """
        candidates: Set[str] = set()
        initial_match = False

        # Start with capability name match
        if requirement.capability_name:
            if requirement.capability_name in self._capability_index:
                candidates = self._capability_index[requirement.capability_name].copy()
                initial_match = True

        # Filter/add by capability type
        if requirement.capability_type:
            type_matches = self._type_index.get(requirement.capability_type, set())
            if initial_match:
                candidates &= type_matches
            else:
                candidates |= type_matches
                initial_match = True

        # Filter/add by tags
        if requirement.tags:
            tag_matches = set()
            for tag in requirement.tags:
                tag_matches |= self._tag_index.get(tag, set())
            if initial_match:
                candidates &= tag_matches
            else:
                candidates = tag_matches
                initial_match = True

        # If no filters, consider all agents
        if not initial_match:
            candidates = set(self._agents.keys())

        # Score and filter candidates
        results = []
        for agent_type in candidates:
            agent_caps = self._agents[agent_type]
            for cap in agent_caps.capabilities:
                score, reasons = self._score_match(cap, requirement)
                if score > 0:
                    results.append(MatchResult(
                        agent_type=agent_type,
                        agent_class=agent_caps.agent_class,
                        capability=cap,
                        score=score,
                        reasons=reasons
                    ))

        # Sort by score (descending)
        results.sort(key=lambda r: r.score, reverse=True)
        return results

    def find_best_agent(
        self,
        requirement: TaskRequirement
    ) -> Optional[MatchResult]:
        """Find the single best agent for a requirement"""
        results = self.find_agents(requirement)
        return results[0] if results else None

    def get_agent_capabilities(self, agent_type: str) -> Optional[AgentCapabilities]:
        """Get capabilities for a specific agent"""
        return self._agents.get(agent_type)

    def list_agents(self) -> List[str]:
        """List all registered agent types"""
        return list(self._agents.keys())

    def list_capabilities(self) -> List[str]:
        """List all registered capability names"""
        return list(self._capability_index.keys())

    def get_agents_by_capability(self, capability_name: str) -> List[str]:
        """Get agent types that have a specific capability"""
        return list(self._capability_index.get(capability_name, set()))

    def get_agents_by_type(self, capability_type: CapabilityType) -> List[str]:
        """Get agent types that have capabilities of a specific type"""
        return list(self._type_index.get(capability_type, set()))

    # ==================== Scoring ====================

    def _score_match(
        self,
        capability: Capability,
        requirement: TaskRequirement
    ) -> tuple:
        """
        Score how well a capability matches a requirement

        Returns:
            (score: float, reasons: List[str])
        """
        score = 1.0
        reasons = []

        # Name match
        if requirement.capability_name:
            if capability.name == requirement.capability_name:
                score *= 1.0
                reasons.append("Exact name match")
            elif requirement.capability_name.lower() in capability.name.lower():
                score *= 0.8
                reasons.append("Partial name match")
            else:
                score *= 0.5
                reasons.append("Name mismatch")

        # Type match
        if requirement.capability_type:
            if capability.type == requirement.capability_type:
                score *= 1.0
                reasons.append("Type match")
            else:
                score *= 0.3
                reasons.append("Type mismatch")

        # Tag match
        if requirement.tags:
            matching_tags = set(requirement.tags) & set(capability.tags)
            tag_ratio = len(matching_tags) / len(requirement.tags)
            score *= (0.5 + 0.5 * tag_ratio)
            reasons.append(f"Tag match: {len(matching_tags)}/{len(requirement.tags)}")

        # Reliability filter
        if capability.reliability < requirement.min_reliability:
            score = 0
            reasons.append(f"Below reliability threshold ({capability.reliability} < {requirement.min_reliability})")

        # Cost filter
        if capability.cost > requirement.max_cost:
            score = 0
            reasons.append(f"Exceeds cost limit ({capability.cost} > {requirement.max_cost})")

        # Boost for high reliability
        if capability.reliability > 0.9:
            score *= 1.1
            reasons.append("High reliability bonus")

        # Penalize high cost
        if capability.cost > 2.0:
            score *= 0.9
            reasons.append("High cost penalty")

        return min(score, 1.0), reasons

    # ==================== Dependency Resolution ====================

    def resolve_dependencies(
        self,
        capability_name: str,
        resolved: Optional[Set[str]] = None
    ) -> List[str]:
        """
        Resolve capability dependencies

        Returns ordered list of capabilities needed (dependencies first)
        """
        if resolved is None:
            resolved = set()

        result = []

        # Find capability in any agent
        for agent_caps in self._agents.values():
            for cap in agent_caps.capabilities:
                if cap.name == capability_name:
                    for dep in cap.dependencies:
                        if dep not in resolved:
                            resolved.add(dep)
                            result.extend(self.resolve_dependencies(dep, resolved))

        if capability_name not in resolved:
            resolved.add(capability_name)
            result.append(capability_name)

        return result

    # ==================== Utilities ====================

    def get_stats(self) -> Dict[str, Any]:
        """Get registry statistics"""
        total_capabilities = sum(
            len(ac.capabilities) for ac in self._agents.values()
        )

        type_counts = {
            t.value: len(agents)
            for t, agents in self._type_index.items()
        }

        return {
            "total_agents": len(self._agents),
            "total_capabilities": total_capabilities,
            "unique_capability_names": len(self._capability_index),
            "capabilities_by_type": type_counts,
            "total_tags": len(self._tag_index)
        }

    def export(self) -> Dict[str, Any]:
        """Export registry as a dictionary"""
        return {
            agent_type: {
                "agent_class": ac.agent_class.__name__,
                "capabilities": [
                    {
                        "name": c.name,
                        "type": c.type.value,
                        "description": c.description,
                        "version": c.version,
                        "tags": c.tags,
                        "cost": c.cost,
                        "reliability": c.reliability
                    }
                    for c in ac.capabilities
                ],
                "registered_at": ac.registered_at.isoformat(),
                "metadata": ac.metadata
            }
            for agent_type, ac in self._agents.items()
        }


# Global registry instance
_registry: Optional[CapabilityRegistry] = None


def get_capability_registry() -> CapabilityRegistry:
    """Get the global CapabilityRegistry instance"""
    global _registry
    if _registry is None:
        _registry = CapabilityRegistry()
    return _registry


# Decorator for registering agent capabilities
def capabilities(*caps: Capability):
    """
    Decorator to register an agent's capabilities

    Usage:
        @capabilities(
            Capability("web_search", CapabilityType.RESEARCH, "Search the web"),
            Capability("summarize", CapabilityType.ANALYSIS, "Summarize text")
        )
        class ResearchAgent(BaseAgent):
            ...
    """
    def decorator(cls: Type[BaseAgent]):
        # Register on first import
        registry = get_capability_registry()
        registry.register_agent(cls, list(caps))
        return cls
    return decorator


# Pre-defined common capabilities
class CommonCapabilities:
    """Factory for common capability definitions"""

    @staticmethod
    def web_search(reliability: float = 0.9) -> Capability:
        return Capability(
            name="web_search",
            type=CapabilityType.RESEARCH,
            description="Search the web for information",
            tags=["search", "web", "research"],
            reliability=reliability
        )

    @staticmethod
    def text_generation(reliability: float = 0.95) -> Capability:
        return Capability(
            name="text_generation",
            type=CapabilityType.GENERATION,
            description="Generate text content",
            tags=["text", "content", "writing"],
            reliability=reliability
        )

    @staticmethod
    def code_generation(reliability: float = 0.85) -> Capability:
        return Capability(
            name="code_generation",
            type=CapabilityType.CODE,
            description="Generate source code",
            tags=["code", "programming", "development"],
            reliability=reliability,
            cost=1.5
        )

    @staticmethod
    def code_analysis(reliability: float = 0.9) -> Capability:
        return Capability(
            name="code_analysis",
            type=CapabilityType.CODE,
            description="Analyze and review code",
            tags=["code", "analysis", "review"],
            reliability=reliability
        )

    @staticmethod
    def data_analysis(reliability: float = 0.9) -> Capability:
        return Capability(
            name="data_analysis",
            type=CapabilityType.ANALYSIS,
            description="Analyze structured data",
            tags=["data", "analysis", "statistics"],
            reliability=reliability
        )

    @staticmethod
    def file_operations(reliability: float = 0.95) -> Capability:
        return Capability(
            name="file_operations",
            type=CapabilityType.FILE,
            description="Read and write files",
            tags=["file", "io", "storage"],
            reliability=reliability
        )

    @staticmethod
    def notification(reliability: float = 0.98) -> Capability:
        return Capability(
            name="notification",
            type=CapabilityType.COMMUNICATION,
            description="Send notifications",
            tags=["notification", "alert", "messaging"],
            reliability=reliability,
            cost=0.5
        )
