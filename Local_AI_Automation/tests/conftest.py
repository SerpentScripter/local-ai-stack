"""
Pytest Configuration and Fixtures
"""
import os
import sys
import tempfile
import pytest
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set test environment
os.environ["TESTING"] = "1"
os.environ["AUTH_ENABLED"] = "false"


@pytest.fixture(scope="session")
def test_db():
    """Create a temporary database for testing"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    os.environ["DB_PATH"] = db_path

    yield db_path

    # Cleanup
    try:
        os.unlink(db_path)
    except Exception:
        pass


@pytest.fixture
def app(test_db):
    """Create test FastAPI application"""
    from api.main import create_app
    return create_app()


@pytest.fixture
def client(app):
    """Create test client"""
    from fastapi.testclient import TestClient
    return TestClient(app)


@pytest.fixture
def async_client(app):
    """Create async test client"""
    import httpx
    from asgi_lifespan import LifespanManager
    import asyncio

    async def get_client():
        async with LifespanManager(app):
            async with httpx.AsyncClient(app=app, base_url="http://test") as client:
                yield client

    return get_client


@pytest.fixture
def sample_task():
    """Sample task data"""
    return {
        "title": "Test Task",
        "description": "This is a test task",
        "priority": "P2",
        "category": "feature"
    }


@pytest.fixture
def sample_agent_config():
    """Sample agent configuration"""
    return {
        "agent_type": "research",
        "goal": "Research testing frameworks",
        "max_iterations": 5
    }


@pytest.fixture
def mock_ollama(monkeypatch):
    """Mock Ollama API responses"""
    import httpx

    class MockResponse:
        status_code = 200

        def json(self):
            return {
                "response": "This is a test response from the AI model.",
                "model": "llama3.2",
                "done": True
            }

    async def mock_post(*args, **kwargs):
        return MockResponse()

    async def mock_get(*args, **kwargs):
        class ModelsResponse:
            status_code = 200
            def json(self):
                return {"models": [{"name": "llama3.2"}, {"name": "codellama"}]}
        return ModelsResponse()

    # This would be properly mocked in actual tests
    return mock_post, mock_get
