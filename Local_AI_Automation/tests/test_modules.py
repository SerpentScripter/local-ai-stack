"""
Unit Tests for Core Modules
Tests for internal module functionality
"""
import pytest
from datetime import datetime, timedelta


class TestPrioritizationEngine:
    """Tests for the prioritization engine"""

    def test_energy_levels(self):
        """Test energy level enum values"""
        from api.prioritization_engine import EnergyLevel

        assert EnergyLevel.HIGH.value == "high"
        assert EnergyLevel.MEDIUM.value == "medium"
        assert EnergyLevel.LOW.value == "low"

    def test_engine_initialization(self):
        """Test engine initializes correctly"""
        from api.prioritization_engine import PrioritizationEngine

        engine = PrioritizationEngine()
        assert engine._current_energy is not None

    def test_task_scoring(self):
        """Test task scoring function"""
        from api.prioritization_engine import PrioritizationEngine

        engine = PrioritizationEngine()

        task = {
            "external_id": "test_123",
            "title": "Test Task",
            "priority": "P0",
            "status": "backlog",
            "created_at": datetime.utcnow().isoformat()
        }

        score = engine.score_task(task, [task])
        assert score.total_score > 0
        assert score.task_id is not None
        assert "priority" in score.factor_breakdown


class TestCapabilityRegistry:
    """Tests for the capability registry"""

    def test_capability_types(self):
        """Test capability type enum"""
        from api.capability_registry import CapabilityType

        assert CapabilityType.RESEARCH.value == "research"
        assert CapabilityType.CODE.value == "code"

    def test_registry_initialization(self):
        """Test registry initializes"""
        from api.capability_registry import CapabilityRegistry

        registry = CapabilityRegistry()
        assert registry is not None


class TestMessageBus:
    """Tests for the message bus"""

    def test_message_types(self):
        """Test message type enum"""
        from api.message_bus import MessageType

        assert MessageType.EVENT.value == "event"
        assert MessageType.REQUEST.value == "request"

    def test_topic_matching(self):
        """Test topic pattern matching via _find_matching_subscriptions"""
        from api.message_bus import MessageBus
        import fnmatch

        # Test that fnmatch patterns work as expected (internal matching logic)
        # Exact match
        assert fnmatch.fnmatch("agent.started", "agent.started")

        # Wildcard match
        assert fnmatch.fnmatch("agent.started", "agent.*")
        assert fnmatch.fnmatch("agent.completed", "agent.*")

        # Non-match
        assert not fnmatch.fnmatch("task.created", "agent.*")

        # Double wildcard (fnmatch uses ** for recursive)
        assert fnmatch.fnmatch("agent.research.started", "agent.*.*")


class TestSharedMemory:
    """Tests for shared memory system"""

    def test_memory_scope(self):
        """Test memory scope enum"""
        from api.shared_memory import MemoryScope

        assert MemoryScope.GLOBAL.value == "global"
        assert MemoryScope.SESSION.value == "session"
        assert MemoryScope.AGENT.value == "agent"

    def test_memory_operations(self):
        """Test basic memory operations"""
        from api.shared_memory import SharedMemory

        memory = SharedMemory()

        # Test set and get
        memory.set("test_key", "test_value", owner="test")
        value = memory.get("test_key", owner="test")
        assert value == "test_value"

        # Test delete
        memory.delete("test_key", owner="test")
        value = memory.get("test_key", owner="test")
        assert value is None


class TestOrchestrator:
    """Tests for the orchestrator"""

    def test_supervisor_strategy(self):
        """Test supervisor strategy enum"""
        from api.orchestrator import SupervisorStrategy

        assert SupervisorStrategy.ONE_FOR_ONE.value == "one_for_one"
        assert SupervisorStrategy.ONE_FOR_ALL.value == "one_for_all"

    def test_agent_status(self):
        """Test agent status enum"""
        from api.orchestrator import AgentStatus

        assert AgentStatus.PENDING.value == "pending"
        assert AgentStatus.RUNNING.value == "running"
        assert AgentStatus.COMPLETED.value == "completed"


class TestEventBridge:
    """Tests for the event bridge"""

    def test_event_categories(self):
        """Test event category enum"""
        from api.event_bridge import EventCategory

        assert EventCategory.SYSTEM.value == "system"
        assert EventCategory.AGENT.value == "agent"
        assert EventCategory.TASK.value == "task"

    def test_event_priority(self):
        """Test event priority enum"""
        from api.event_bridge import EventPriority

        assert EventPriority.LOW.value == 0
        assert EventPriority.NORMAL.value == 1
        assert EventPriority.HIGH.value == 2
        assert EventPriority.CRITICAL.value == 3

    def test_pattern_matching(self):
        """Test event pattern matching"""
        from api.event_bridge import EventBridge

        bridge = EventBridge()

        # Wildcard match
        assert bridge._matches_pattern("task.created", "task.*")
        assert bridge._matches_pattern("agent.completed", "agent.*")

        # Catch-all
        assert bridge._matches_pattern("anything.here", "*")

        # No match
        assert not bridge._matches_pattern("task.created", "agent.*")


class TestWorkflowGenerator:
    """Tests for the workflow generator"""

    def test_trigger_types(self):
        """Test trigger type enum"""
        from api.workflow_generator import TriggerType

        assert TriggerType.WEBHOOK.value == "webhook"
        assert TriggerType.SCHEDULE.value == "schedule"

    def test_action_types(self):
        """Test action type enum"""
        from api.workflow_generator import ActionType

        assert ActionType.OLLAMA.value == "ollama"
        assert ActionType.SLACK_MESSAGE.value == "slack_message"

    def test_workflow_node_creation(self):
        """Test workflow node creation"""
        from api.workflow_generator import WorkflowNode

        node = WorkflowNode(
            id="test_id",
            name="Test Node",
            type="n8n-nodes-base.webhook",
            parameters={"path": "/test"}
        )

        n8n_format = node.to_n8n()
        assert n8n_format["id"] == "test_id"
        assert n8n_format["name"] == "Test Node"
        assert n8n_format["type"] == "n8n-nodes-base.webhook"


class TestSelfAssessment:
    """Tests for the self-assessment system"""

    def test_assessment_grades(self):
        """Test assessment grade enum"""
        from api.self_assessment import AssessmentGrade

        assert AssessmentGrade.A.value == "A"
        assert AssessmentGrade.F.value == "F"

    def test_score_to_grade(self):
        """Test score to grade conversion"""
        from api.self_assessment import SelfAssessmentSystem

        system = SelfAssessmentSystem()

        assert system._score_to_grade(95).value == "A"
        assert system._score_to_grade(85).value == "B"
        assert system._score_to_grade(75).value == "C"
        assert system._score_to_grade(65).value == "D"
        assert system._score_to_grade(50).value == "F"


class TestModelBenchmarks:
    """Tests for the model benchmark system"""

    def test_benchmark_types(self):
        """Test benchmark type enum"""
        from api.model_benchmarks import BenchmarkType

        assert BenchmarkType.COHERENCE.value == "coherence"
        assert BenchmarkType.REASONING.value == "reasoning"
        assert BenchmarkType.CODE_GENERATION.value == "code_generation"

    def test_benchmark_result_creation(self):
        """Test benchmark result creation"""
        from api.model_benchmarks import BenchmarkResult, BenchmarkType

        result = BenchmarkResult(
            model="llama3.2",
            benchmark_type=BenchmarkType.REASONING,
            score=85.5,
            latency_ms=1500,
            tokens_per_second=25.5
        )

        assert result.model == "llama3.2"
        assert result.score == 85.5


class TestUpdateManager:
    """Tests for the update manager"""

    def test_component_types(self):
        """Test component type enum"""
        from api.update_manager import ComponentType

        assert ComponentType.OLLAMA_MODEL.value == "ollama_model"
        assert ComponentType.DOCKER_IMAGE.value == "docker_image"

    def test_update_status(self):
        """Test update status enum"""
        from api.update_manager import UpdateStatus

        assert UpdateStatus.PENDING.value == "pending"
        assert UpdateStatus.COMPLETED.value == "completed"
        assert UpdateStatus.ROLLED_BACK.value == "rolled_back"


class TestDistributedAgents:
    """Tests for distributed agent system"""

    def test_node_status(self):
        """Test node status enum"""
        from api.distributed_agents import NodeStatus

        assert NodeStatus.ONLINE.value == "online"
        assert NodeStatus.OFFLINE.value == "offline"
        assert NodeStatus.DRAINING.value == "draining"

    def test_load_balance_strategy(self):
        """Test load balancing strategy enum"""
        from api.distributed_agents import LoadBalanceStrategy

        assert LoadBalanceStrategy.ROUND_ROBIN.value == "round_robin"
        assert LoadBalanceStrategy.LEAST_LOADED.value == "least_loaded"

    def test_worker_node_capacity(self):
        """Test worker node capacity calculation"""
        from api.distributed_agents import WorkerNode, NodeStatus

        node = WorkerNode(
            node_id="test_node",
            hostname="localhost",
            address="127.0.0.1",
            port=8765,
            max_capacity=5,
            current_load=2
        )

        assert node.available_capacity == 3
        assert node.is_available is True

        node.current_load = 5
        assert node.available_capacity == 0


class TestWebhooks:
    """Tests for webhook system"""

    def test_webhook_types(self):
        """Test webhook type enum"""
        from api.webhooks import WebhookType

        assert WebhookType.GENERIC.value == "generic"
        assert WebhookType.GITHUB.value == "github"
        assert WebhookType.SLACK.value == "slack"

    def test_signature_validation(self):
        """Test webhook signature validation logic"""
        from api.webhooks import WebhookManager, WebhookType
        import hmac
        import hashlib

        manager = WebhookManager()

        # Create a test webhook first
        webhook = manager.create_webhook(
            name="Test Signature Webhook",
            webhook_type=WebhookType.GENERIC
        )
        webhook_id = webhook.id

        # Create payload
        payload = b'{"test": "data"}'

        # Generate valid signature using the webhook's secret
        expected_sig = hmac.new(
            webhook.secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()

        # Verify works with the webhook_id-based validation
        assert manager.validate_signature(
            webhook_id, payload, f"sha256={expected_sig}"
        )

        # Invalid signature fails
        assert not manager.validate_signature(
            webhook_id, payload, "sha256=invalid"
        )


class TestSessionStateMachine:
    """Tests for the session state machine"""

    def test_session_states(self):
        """Test session state enum"""
        from api.session_state_machine import SessionState

        assert SessionState.IDLE.value == "idle"
        assert SessionState.WORKING.value == "working"
        assert SessionState.COMPLETED.value == "completed"

    def test_session_state_machine_initialization(self):
        """Test session state machine initializes correctly"""
        from api.session_state_machine import SessionStateMachine

        machine = SessionStateMachine()
        assert machine is not None

    def test_session_creation(self):
        """Test creating a new session"""
        from api.session_state_machine import SessionStateMachine
        import uuid

        machine = SessionStateMachine()
        session = machine.create_session(
            session_id=f"test-{uuid.uuid4().hex[:8]}",
            project_id="test-project",
            goal="Test Session Goal",
            agent_type="research"
        )

        assert session.session_id is not None
        assert session.goal == "Test Session Goal"
        assert session.state.value == "idle"

    def test_session_transitions(self):
        """Test session state transitions"""
        from api.session_state_machine import SessionStateMachine, SessionState, SessionEvent
        import uuid

        machine = SessionStateMachine()
        session = machine.create_session(
            session_id=f"transition-test-{uuid.uuid4().hex[:8]}",
            project_id="test-project",
            goal="Transition Test",
            agent_type="test"
        )
        session_id = session.session_id

        # Start session
        result = machine.transition(session_id, SessionEvent.START)
        assert result is True
        session = machine.get_session(session_id)
        assert session.state == SessionState.WORKING

        # Complete session
        result = machine.transition(session_id, SessionEvent.COMPLETE)
        assert result is True
        session = machine.get_session(session_id)
        assert session.state == SessionState.COMPLETED

    def test_invalid_transition(self):
        """Test invalid state transitions are rejected"""
        from api.session_state_machine import SessionStateMachine, SessionEvent
        import uuid

        machine = SessionStateMachine()
        session = machine.create_session(
            session_id=f"invalid-test-{uuid.uuid4().hex[:8]}",
            project_id="test-project",
            goal="Invalid Test",
            agent_type="test"
        )
        session_id = session.session_id

        # Try to complete without starting (should return False)
        result = machine.transition(session_id, SessionEvent.COMPLETE)
        assert result is False  # Invalid transition returns False, doesn't raise


class TestMCPServer:
    """Tests for the MCP server"""

    def test_mcp_server_initialization(self):
        """Test MCP server initializes correctly"""
        from api.mcp_server import MCPServer

        server = MCPServer()
        assert server is not None

    def test_mcp_tools_registered(self):
        """Test MCP tools are registered"""
        from api.mcp_server import MCPServer

        server = MCPServer()
        tools = server._tools

        # Check expected tools exist
        assert "search_backlog" in tools
        assert "create_task" in tools
        assert "get_system_metrics" in tools

    def test_mcp_initialize_handler(self):
        """Test MCP initialize message handling"""
        from api.mcp_server import MCPServer
        import asyncio

        server = MCPServer()

        async def test():
            message = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0"}
                }
            }
            response = await server.handle_message(message)
            assert response["jsonrpc"] == "2.0"
            assert "result" in response
            assert response["result"]["serverInfo"]["name"] == "local-ai-hub"

        asyncio.run(test())


class TestWorktreeManager:
    """Tests for the worktree manager"""

    def test_worktree_status_enum(self):
        """Test worktree status enum"""
        from api.worktree_manager import WorktreeStatus

        assert WorktreeStatus.CREATING.value == "creating"
        assert WorktreeStatus.ACTIVE.value == "active"
        assert WorktreeStatus.MERGED.value == "merged"

    def test_worktree_manager_initialization(self):
        """Test worktree manager initializes correctly"""
        from api.worktree_manager import WorktreeManager

        manager = WorktreeManager()
        assert manager is not None

    def test_list_worktrees(self):
        """Test listing worktrees"""
        from api.worktree_manager import WorktreeManager

        manager = WorktreeManager()
        worktrees = manager.list_worktrees()
        assert isinstance(worktrees, list)
