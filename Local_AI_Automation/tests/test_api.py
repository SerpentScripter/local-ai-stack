"""
API Endpoint Tests
Tests for core API functionality
"""
import pytest
from fastapi.testclient import TestClient


class TestHealthEndpoints:
    """Test health and info endpoints"""

    def test_health_check(self, client):
        """Test health endpoint returns healthy status"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "database" in data

    def test_api_info(self, client):
        """Test API info endpoint"""
        response = client.get("/api/info")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Local AI Hub API"
        assert "version" in data
        assert "modules" in data
        assert isinstance(data["modules"], list)

    def test_root_endpoint(self, client):
        """Test root endpoint"""
        response = client.get("/")
        # Either serves HTML or returns JSON
        assert response.status_code == 200


class TestBacklogEndpoints:
    """Test backlog CRUD operations"""

    def test_create_task(self, client, sample_task):
        """Test creating a new task"""
        response = client.post("/items", json=sample_task)
        assert response.status_code in (200, 201)
        data = response.json()
        assert "external_id" in data
        assert data["status"] == "created"

    def test_list_tasks(self, client):
        """Test listing tasks"""
        response = client.get("/items")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_filter_tasks_by_status(self, client):
        """Test filtering tasks by status"""
        response = client.get("/items?status=backlog")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        for task in data:
            assert task.get("status") == "backlog"

    def test_filter_tasks_by_priority(self, client):
        """Test filtering tasks by priority"""
        response = client.get("/items?priority=P0")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_get_task_by_id(self, client, sample_task):
        """Test getting a specific task"""
        # First create a task
        create_response = client.post("/items", json=sample_task)
        task_id = create_response.json()["external_id"]

        # Then retrieve it
        response = client.get(f"/items/{task_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["external_id"] == task_id

    def test_update_task(self, client, sample_task):
        """Test updating a task"""
        # Create task
        create_response = client.post("/items", json=sample_task)
        task_id = create_response.json()["external_id"]

        # Update task using PATCH
        update_data = {"title": "Updated Title", "priority": "P1"}
        response = client.patch(f"/items/{task_id}", json=update_data)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "updated"

    def test_mark_task_done(self, client, sample_task):
        """Test marking a task as done"""
        # Create task
        create_response = client.post("/items", json=sample_task)
        task_id = create_response.json()["external_id"]

        # Mark task as done via POST /items/{id}/done
        response = client.post(f"/items/{task_id}/done")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "done"

    def test_get_nonexistent_task(self, client):
        """Test getting a task that doesn't exist"""
        response = client.get("/items/nonexistent_id_12345")
        assert response.status_code == 404


class TestStatsEndpoints:
    """Test statistics endpoints"""

    def test_get_stats(self, client):
        """Test getting backlog statistics"""
        response = client.get("/stats")
        assert response.status_code == 200
        data = response.json()
        assert "by_status" in data
        assert "by_priority" in data
        assert "by_category" in data

    def test_get_categories(self, client):
        """Test getting categories"""
        response = client.get("/categories")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestServicesEndpoints:
    """Test service management endpoints"""

    def test_list_services(self, client):
        """Test listing services"""
        response = client.get("/services")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_get_service_status(self, client):
        """Test getting a specific service status"""
        # First get list of services
        list_response = client.get("/services")
        services = list_response.json()

        if services:
            service_id = services[0].get("id")
            if service_id:
                response = client.get(f"/services/{service_id}")
                assert response.status_code in (200, 404)


class TestMetricsEndpoints:
    """Test metrics endpoints"""

    def test_get_system_metrics(self, client):
        """Test getting system metrics"""
        response = client.get("/system/metrics")
        assert response.status_code == 200
        data = response.json()
        # Should have CPU and memory at minimum
        assert "cpu" in data or "cpu_percent" in data


class TestPrioritizationEndpoints:
    """Test prioritization engine endpoints"""

    def test_get_recommendations(self, client):
        """Test getting task recommendations"""
        response = client.get("/prioritize/recommend")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_what_next(self, client):
        """Test what should I do next endpoint"""
        response = client.get("/prioritize/next")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data

    def test_scope_creep_detection(self, client):
        """Test scope creep detection"""
        response = client.get("/prioritize/scope-creep")
        assert response.status_code == 200
        data = response.json()
        assert "alert_count" in data
        assert "alerts" in data


class TestAssessmentEndpoints:
    """Test self-assessment endpoints"""

    def test_get_grade(self, client):
        """Test getting current grade"""
        response = client.get("/assessment/grade")
        assert response.status_code == 200
        data = response.json()
        assert "grade" in data
        assert "score" in data

    def test_get_trend(self, client):
        """Test getting assessment trend"""
        response = client.get("/assessment/trend")
        assert response.status_code == 200
        data = response.json()
        assert "trend" in data

    def test_get_history(self, client):
        """Test getting assessment history"""
        response = client.get("/assessment/history")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestWorkflowGeneratorEndpoints:
    """Test workflow generator endpoints"""

    def test_list_templates(self, client):
        """Test listing workflow templates"""
        response = client.get("/workflow-gen/templates/list")
        assert response.status_code == 200
        data = response.json()
        assert "templates" in data

    def test_get_pending_workflows(self, client):
        """Test getting pending workflows"""
        response = client.get("/workflow-gen/pending")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestBenchmarkEndpoints:
    """Test benchmark endpoints"""

    def test_list_benchmark_types(self, client):
        """Test listing benchmark types"""
        response = client.get("/benchmarks/types")
        assert response.status_code == 200
        data = response.json()
        assert "benchmark_types" in data

    def test_get_leaderboard(self, client):
        """Test getting model leaderboard"""
        response = client.get("/benchmarks/leaderboard")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestUpdateEndpoints:
    """Test update management endpoints"""

    def test_get_components(self, client):
        """Test listing tracked components"""
        response = client.get("/updates/components")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_get_pending_updates(self, client):
        """Test getting pending updates"""
        response = client.get("/updates/pending")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_get_update_history(self, client):
        """Test getting update history"""
        response = client.get("/updates/history")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestDistributedEndpoints:
    """Test distributed agent endpoints"""

    def test_get_distributed_stats(self, client):
        """Test getting distributed system stats"""
        response = client.get("/distributed/stats")
        assert response.status_code == 200
        data = response.json()
        assert "nodes" in data
        assert "tasks" in data

    def test_list_nodes(self, client):
        """Test listing distributed nodes"""
        response = client.get("/distributed/nodes")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_list_tasks(self, client):
        """Test listing distributed tasks"""
        response = client.get("/distributed/tasks")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestWebhookEndpoints:
    """Test webhook management endpoints"""

    def test_list_webhooks(self, client):
        """Test listing webhooks"""
        response = client.get("/webhooks/")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_create_webhook(self, client):
        """Test creating a webhook"""
        webhook_data = {
            "name": "Test Webhook",
            "type": "generic"
        }
        response = client.post("/webhooks/", json=webhook_data)
        assert response.status_code in (200, 201)
        data = response.json()
        assert "id" in data


class TestSlackEndpoints:
    """Test Slack integration endpoints"""

    def test_get_slack_status(self, client):
        """Test getting Slack integration status"""
        response = client.get("/slack/status")
        assert response.status_code == 200
        data = response.json()
        assert "configured" in data
        assert "features" in data


class TestKanbanEndpoints:
    """Test Kanban board endpoints"""

    def test_get_board(self, client):
        """Test getting the Kanban board"""
        response = client.get("/kanban/board")
        assert response.status_code == 200
        data = response.json()
        # Board returns columns directly at root level
        assert "working" in data
        assert "completed" in data
        assert "idle" in data
        assert isinstance(data["working"], list)

    def test_get_states(self, client):
        """Test getting valid session states"""
        response = client.get("/kanban/states")
        assert response.status_code == 200
        data = response.json()
        assert "states" in data
        assert "idle" in data["states"]
        assert "working" in data["states"]

    def test_get_stats(self, client):
        """Test getting Kanban statistics"""
        response = client.get("/kanban/stats")
        assert response.status_code == 200
        data = response.json()
        assert "total_sessions" in data
        assert "by_state" in data

    def test_create_session(self, client):
        """Test creating a new Kanban session"""
        import uuid
        session_data = {
            "session_id": f"test-session-{uuid.uuid4().hex[:8]}",
            "project_id": "test-project",
            "goal": "Test task for Kanban",
            "agent_type": "research"
        }
        response = client.post("/kanban/sessions", json=session_data)
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert data["state"] == "idle"

    def test_session_lifecycle(self, client):
        """Test session state transitions"""
        import uuid
        # Create session with correct schema
        session_data = {
            "session_id": f"lifecycle-test-{uuid.uuid4().hex[:8]}",
            "project_id": "test-project",
            "goal": "Testing lifecycle",
            "agent_type": "test"
        }
        create_response = client.post("/kanban/sessions", json=session_data)
        assert create_response.status_code == 200
        session_id = create_response.json()["session_id"]

        # Start session
        start_response = client.post(f"/kanban/sessions/{session_id}/start")
        assert start_response.status_code == 200
        assert start_response.json()["state"] == "working"

        # Complete session
        complete_response = client.post(f"/kanban/sessions/{session_id}/complete")
        assert complete_response.status_code == 200
        assert complete_response.json()["state"] == "completed"

    def test_get_session(self, client):
        """Test getting a specific session"""
        import uuid
        # Create session first with correct schema
        session_id = f"get-test-{uuid.uuid4().hex[:8]}"
        session_data = {
            "session_id": session_id,
            "project_id": "test-project",
            "goal": "Get test goal",
            "agent_type": "test"
        }
        create_response = client.post("/kanban/sessions", json=session_data)
        assert create_response.status_code == 200

        # Get session
        response = client.get(f"/kanban/sessions/{session_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == session_id
        assert data["goal"] == "Get test goal"

    def test_get_nonexistent_session(self, client):
        """Test getting a session that doesn't exist"""
        response = client.get("/kanban/sessions/nonexistent_session_id")
        assert response.status_code == 404


class TestWorktreeEndpoints:
    """Test Git worktree management endpoints"""

    def test_list_worktrees(self, client):
        """Test listing worktrees"""
        response = client.get("/worktree/")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_get_statuses(self, client):
        """Test getting valid worktree statuses"""
        response = client.get("/worktree/statuses")
        assert response.status_code == 200
        data = response.json()
        assert "statuses" in data
        assert "descriptions" in data
        assert "active" in data["statuses"]

    def test_cleanup_endpoint(self, client):
        """Test cleanup stale worktrees endpoint"""
        response = client.post("/worktree/cleanup?max_age_hours=24")
        assert response.status_code == 200
        data = response.json()
        assert "cleaned" in data
        assert "message" in data

    def test_get_nonexistent_worktree(self, client):
        """Test getting a worktree that doesn't exist"""
        response = client.get("/worktree/nonexistent_worktree_id")
        assert response.status_code == 404
