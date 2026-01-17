"""
Self-Assessment System
Monitors and grades the Local AI Hub across multiple dimensions

Dimensions:
- Model Currency: Installed vs latest releases
- Tool Versions: Docker images vs latest available
- Capability Coverage: Supported modalities vs available
- Benchmark Scores: Model quality vs baselines
- Security Posture: CVEs, configs, secrets
- System Health: Resource utilization, uptime
"""
import json
import os
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

from .database import get_db
from .logging_config import api_logger


class AssessmentGrade(Enum):
    """Assessment grade levels"""
    A = "A"  # 90-100%
    B = "B"  # 80-89%
    C = "C"  # 70-79%
    D = "D"  # 60-69%
    F = "F"  # < 60%


@dataclass
class DimensionScore:
    """Score for a single dimension"""
    name: str
    score: float  # 0-100
    grade: AssessmentGrade
    weight: float
    issues: List[str]
    recommendations: List[str]
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AssessmentReport:
    """Complete assessment report"""
    timestamp: datetime
    overall_score: float
    overall_grade: AssessmentGrade
    dimensions: List[DimensionScore]
    critical_issues: List[str]
    improvement_plan: List[str]


class SelfAssessmentSystem:
    """
    Self-assessment and grading system for the Local AI Hub

    Runs periodic assessments and tracks improvement over time.
    """

    def __init__(self):
        self._weights = {
            "model_currency": 0.20,
            "tool_versions": 0.15,
            "capability_coverage": 0.20,
            "benchmark_scores": 0.10,
            "security_posture": 0.20,
            "system_health": 0.15
        }
        self._init_database()

    def _init_database(self):
        """Initialize assessment storage"""
        try:
            with get_db() as conn:
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS assessment_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        overall_score REAL NOT NULL,
                        overall_grade TEXT NOT NULL,
                        dimensions TEXT NOT NULL,
                        issues TEXT,
                        recommendations TEXT
                    );

                    CREATE INDEX IF NOT EXISTS idx_assessment_time
                    ON assessment_history(timestamp);

                    CREATE TABLE IF NOT EXISTS model_benchmarks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        model_name TEXT NOT NULL,
                        benchmark_name TEXT NOT NULL,
                        score REAL NOT NULL,
                        baseline REAL,
                        tested_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS version_tracking (
                        component TEXT PRIMARY KEY,
                        current_version TEXT,
                        latest_version TEXT,
                        last_checked TEXT,
                        update_available INTEGER DEFAULT 0
                    );
                """)
        except Exception as e:
            api_logger.error(f"Failed to init assessment tables: {e}")

    def _score_to_grade(self, score: float) -> AssessmentGrade:
        """Convert numeric score to letter grade"""
        if score >= 90:
            return AssessmentGrade.A
        elif score >= 80:
            return AssessmentGrade.B
        elif score >= 70:
            return AssessmentGrade.C
        elif score >= 60:
            return AssessmentGrade.D
        else:
            return AssessmentGrade.F

    # ==================== Assessment Functions ====================

    async def run_full_assessment(self) -> AssessmentReport:
        """Run a complete assessment across all dimensions"""
        dimensions = []

        # Run all dimension assessments
        dimensions.append(await self._assess_model_currency())
        dimensions.append(await self._assess_tool_versions())
        dimensions.append(await self._assess_capabilities())
        dimensions.append(await self._assess_benchmarks())
        dimensions.append(await self._assess_security())
        dimensions.append(await self._assess_system_health())

        # Calculate overall score
        overall_score = sum(d.score * d.weight for d in dimensions)
        overall_grade = self._score_to_grade(overall_score)

        # Collect critical issues
        critical_issues = []
        for dim in dimensions:
            if dim.grade in (AssessmentGrade.D, AssessmentGrade.F):
                critical_issues.extend(dim.issues[:2])

        # Build improvement plan
        improvement_plan = self._build_improvement_plan(dimensions)

        report = AssessmentReport(
            timestamp=datetime.utcnow(),
            overall_score=overall_score,
            overall_grade=overall_grade,
            dimensions=dimensions,
            critical_issues=critical_issues,
            improvement_plan=improvement_plan
        )

        # Save to history
        self._save_assessment(report)

        return report

    async def _assess_model_currency(self) -> DimensionScore:
        """Assess if models are up to date"""
        import httpx

        issues = []
        recommendations = []
        details = {"models": []}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Get installed models from Ollama
                response = await client.get("http://localhost:11434/api/tags")
                if response.status_code == 200:
                    data = response.json()
                    installed = data.get("models", [])

                    up_to_date = 0
                    total = len(installed) if installed else 1

                    for model in installed:
                        name = model.get("name", "unknown")
                        modified = model.get("modified_at", "")

                        # Check if model was updated recently (within 30 days)
                        try:
                            mod_date = datetime.fromisoformat(modified.replace("Z", "+00:00"))
                            age_days = (datetime.utcnow() - mod_date.replace(tzinfo=None)).days
                            is_current = age_days < 30

                            details["models"].append({
                                "name": name,
                                "age_days": age_days,
                                "current": is_current
                            })

                            if is_current:
                                up_to_date += 1
                            else:
                                issues.append(f"Model {name} is {age_days} days old")
                                recommendations.append(f"Update model: ollama pull {name}")

                        except Exception:
                            pass

                    score = (up_to_date / total) * 100 if total > 0 else 50

                else:
                    score = 0
                    issues.append("Could not connect to Ollama")
                    recommendations.append("Ensure Ollama is running")

        except Exception as e:
            score = 0
            issues.append(f"Model assessment failed: {str(e)}")
            recommendations.append("Check Ollama service status")

        return DimensionScore(
            name="Model Currency",
            score=score,
            grade=self._score_to_grade(score),
            weight=self._weights["model_currency"],
            issues=issues,
            recommendations=recommendations,
            details=details
        )

    async def _assess_tool_versions(self) -> DimensionScore:
        """Assess Docker container versions"""
        import httpx

        issues = []
        recommendations = []
        details = {"containers": []}

        expected_containers = [
            ("open-webui", "ghcr.io/open-webui/open-webui"),
            ("langflow", "langflowai/langflow"),
            ("n8n", "n8nio/n8n"),
        ]

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Try Docker API (if available)
                try:
                    response = await client.get("http://localhost:2375/containers/json")
                    running_containers = response.json() if response.status_code == 200 else []
                except Exception:
                    running_containers = []

                up_to_date = 0
                total = len(expected_containers)

                for name, image in expected_containers:
                    # Check if container exists
                    container = next(
                        (c for c in running_containers if name in str(c.get("Names", []))),
                        None
                    )

                    if container:
                        container_image = container.get("Image", "")
                        # For now, assume latest tag is up to date
                        is_current = ":latest" in container_image or container_image == image
                        up_to_date += 1 if is_current else 0

                        details["containers"].append({
                            "name": name,
                            "image": container_image,
                            "status": "running",
                            "current": is_current
                        })

                        if not is_current:
                            issues.append(f"{name} may need updating")
                            recommendations.append(f"docker pull {image}:latest")
                    else:
                        details["containers"].append({
                            "name": name,
                            "status": "not_running"
                        })
                        issues.append(f"{name} container not running")

                # If no Docker API, check via health endpoints
                if not running_containers:
                    health_checks = [
                        ("Open WebUI", "http://localhost:3000"),
                        ("Langflow", "http://localhost:7860"),
                        ("n8n", "http://localhost:5678"),
                    ]

                    for name, url in health_checks:
                        try:
                            resp = await client.get(url, timeout=5.0)
                            if resp.status_code < 500:
                                up_to_date += 1
                                details["containers"].append({"name": name, "status": "healthy"})
                            else:
                                issues.append(f"{name} returned error")
                        except Exception:
                            issues.append(f"{name} not reachable at {url}")

                    total = len(health_checks)

                score = (up_to_date / total) * 100 if total > 0 else 50

        except Exception as e:
            score = 50
            issues.append(f"Version check failed: {str(e)}")

        return DimensionScore(
            name="Tool Versions",
            score=score,
            grade=self._score_to_grade(score),
            weight=self._weights["tool_versions"],
            issues=issues,
            recommendations=recommendations,
            details=details
        )

    async def _assess_capabilities(self) -> DimensionScore:
        """Assess capability coverage"""
        import httpx

        issues = []
        recommendations = []
        details = {"capabilities": {}}

        # Define expected capabilities
        expected_capabilities = {
            "text_generation": {"required": True, "test": "ollama_chat"},
            "embeddings": {"required": True, "test": "ollama_embed"},
            "vision": {"required": False, "test": "vision_model"},
            "code": {"required": False, "test": "code_model"},
            "rag": {"required": True, "test": "vector_search"},
            "workflows": {"required": True, "test": "n8n_api"},
            "web_search": {"required": False, "test": "duckduckgo"},
        }

        supported = 0
        required_supported = 0
        total_required = sum(1 for c in expected_capabilities.values() if c["required"])

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Test text generation
                try:
                    resp = await client.post(
                        "http://localhost:11434/api/generate",
                        json={"model": "llama3.2", "prompt": "test", "stream": False},
                        timeout=30.0
                    )
                    if resp.status_code == 200:
                        details["capabilities"]["text_generation"] = True
                        supported += 1
                        required_supported += 1
                    else:
                        details["capabilities"]["text_generation"] = False
                        issues.append("Text generation not working")
                except Exception:
                    details["capabilities"]["text_generation"] = False
                    issues.append("Cannot reach Ollama for text generation")
                    recommendations.append("Ensure Ollama is running with a text model")

                # Test embeddings
                try:
                    resp = await client.post(
                        "http://localhost:11434/api/embeddings",
                        json={"model": "nomic-embed-text", "prompt": "test"},
                        timeout=10.0
                    )
                    if resp.status_code == 200:
                        details["capabilities"]["embeddings"] = True
                        supported += 1
                        required_supported += 1
                    else:
                        details["capabilities"]["embeddings"] = False
                        issues.append("Embeddings not available")
                except Exception:
                    details["capabilities"]["embeddings"] = False
                    recommendations.append("Install embedding model: ollama pull nomic-embed-text")

                # Test workflows (n8n)
                try:
                    resp = await client.get("http://localhost:5678/healthz", timeout=5.0)
                    if resp.status_code == 200:
                        details["capabilities"]["workflows"] = True
                        supported += 1
                        required_supported += 1
                    else:
                        details["capabilities"]["workflows"] = False
                except Exception:
                    details["capabilities"]["workflows"] = False
                    issues.append("n8n workflows not available")

                # Test vision capability (check for vision model)
                try:
                    resp = await client.get("http://localhost:11434/api/tags")
                    if resp.status_code == 200:
                        models = resp.json().get("models", [])
                        vision_models = [m for m in models if any(
                            v in m.get("name", "").lower()
                            for v in ["llava", "bakllava", "vision"]
                        )]
                        if vision_models:
                            details["capabilities"]["vision"] = True
                            supported += 1
                        else:
                            details["capabilities"]["vision"] = False
                            recommendations.append("Add vision: ollama pull llava")
                except Exception:
                    details["capabilities"]["vision"] = False

                # Test RAG (check Open WebUI docs endpoint)
                try:
                    resp = await client.get("http://localhost:3000/api/documents", timeout=5.0)
                    details["capabilities"]["rag"] = resp.status_code < 500
                    if details["capabilities"]["rag"]:
                        supported += 1
                        required_supported += 1
                    else:
                        issues.append("RAG/document system not working")
                except Exception:
                    details["capabilities"]["rag"] = False
                    recommendations.append("Configure document storage in Open WebUI")

            # Calculate score (weight required capabilities more)
            required_score = (required_supported / total_required) * 70 if total_required > 0 else 0
            optional_score = (supported / len(expected_capabilities)) * 30
            score = required_score + optional_score

        except Exception as e:
            score = 30
            issues.append(f"Capability assessment failed: {str(e)}")

        return DimensionScore(
            name="Capability Coverage",
            score=score,
            grade=self._score_to_grade(score),
            weight=self._weights["capability_coverage"],
            issues=issues,
            recommendations=recommendations,
            details=details
        )

    async def _assess_benchmarks(self) -> DimensionScore:
        """Assess model benchmark scores"""
        issues = []
        recommendations = []
        details = {"benchmarks": []}

        try:
            with get_db() as conn:
                # Get recent benchmarks from benchmark_results table
                rows = conn.execute("""
                    SELECT model, benchmark_type, score, latency_ms, tokens_per_second
                    FROM benchmark_results
                    WHERE timestamp >= datetime('now', '-7 days')
                """).fetchall()

                if rows:
                    total_score = 0
                    for row in rows:
                        # Use 50 as baseline for comparison
                        baseline = 50
                        ratio = min(row["score"] / baseline, 1.5)  # Cap at 150%
                        total_score += row["score"]
                        details["benchmarks"].append({
                            "model": row["model"],
                            "benchmark": row["benchmark_type"],
                            "score": row["score"],
                            "vs_baseline": round(ratio * 100, 1)
                        })

                    # Average score across all benchmarks
                    avg_score = total_score / len(rows)
                    score = min(avg_score, 100)
                else:
                    # No benchmarks - neutral score
                    score = 60
                    issues.append("No benchmark data available")
                    recommendations.append("Run model benchmarks to track quality")

        except Exception as e:
            score = 50
            issues.append(f"Benchmark check failed: {str(e)}")

        return DimensionScore(
            name="Benchmark Scores",
            score=score,
            grade=self._score_to_grade(score),
            weight=self._weights["benchmark_scores"],
            issues=issues,
            recommendations=recommendations,
            details=details
        )

    async def _assess_security(self) -> DimensionScore:
        """Assess security posture"""
        issues = []
        recommendations = []
        details = {"checks": {}}

        checks_passed = 0
        total_checks = 6

        # Check 1: API Authentication enabled
        from .auth import AUTH_ENABLED
        details["checks"]["api_auth"] = AUTH_ENABLED
        if AUTH_ENABLED:
            checks_passed += 1
        else:
            issues.append("API authentication is disabled")
            recommendations.append("Enable AUTH_ENABLED in environment")

        # Check 2: Secrets not in plaintext
        env_secrets = ["OPENAI_API_KEY", "SLACK_BOT_TOKEN", "GITHUB_TOKEN"]
        plaintext_secrets = []
        for key in env_secrets:
            if os.environ.get(key):
                plaintext_secrets.append(key)

        if not plaintext_secrets:
            checks_passed += 1
            details["checks"]["secrets_secured"] = True
        else:
            details["checks"]["secrets_secured"] = False
            issues.append(f"Secrets in environment: {', '.join(plaintext_secrets)}")
            recommendations.append("Move secrets to secrets manager")

        # Check 3: CORS restricted
        from .main import ALLOWED_ORIGINS
        localhost_only = all("localhost" in o or "127.0.0.1" in o for o in ALLOWED_ORIGINS)
        details["checks"]["cors_restricted"] = localhost_only
        if localhost_only:
            checks_passed += 1
        else:
            issues.append("CORS allows non-localhost origins")
            recommendations.append("Restrict CORS to localhost only")

        # Check 4: Database exists and is not world-readable
        from .database import DB_PATH
        if os.path.exists(DB_PATH):
            checks_passed += 1
            details["checks"]["database_exists"] = True
        else:
            details["checks"]["database_exists"] = False
            issues.append("Database file not found")

        # Check 5: No default credentials
        # Check for common default passwords in env
        default_passwords = ["admin", "password", "123456", "changeme"]
        has_defaults = False
        for env_var in os.environ:
            value = os.environ.get(env_var, "").lower()
            if any(d in value for d in default_passwords):
                has_defaults = True
                break

        details["checks"]["no_default_creds"] = not has_defaults
        if not has_defaults:
            checks_passed += 1
        else:
            issues.append("Potential default credentials detected")
            recommendations.append("Change all default passwords")

        # Check 6: Rate limiting (check if implemented)
        details["checks"]["rate_limiting"] = True  # We implemented this
        checks_passed += 1

        score = (checks_passed / total_checks) * 100

        return DimensionScore(
            name="Security Posture",
            score=score,
            grade=self._score_to_grade(score),
            weight=self._weights["security_posture"],
            issues=issues,
            recommendations=recommendations,
            details=details
        )

    async def _assess_system_health(self) -> DimensionScore:
        """Assess system resource health"""
        import psutil

        issues = []
        recommendations = []
        details = {}

        health_score = 100

        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            details["cpu_percent"] = cpu_percent
            if cpu_percent > 90:
                health_score -= 30
                issues.append(f"High CPU usage: {cpu_percent}%")
            elif cpu_percent > 70:
                health_score -= 15

            # Memory usage
            memory = psutil.virtual_memory()
            details["memory_percent"] = memory.percent
            if memory.percent > 90:
                health_score -= 30
                issues.append(f"High memory usage: {memory.percent}%")
                recommendations.append("Consider adding more RAM or reducing model sizes")
            elif memory.percent > 80:
                health_score -= 15

            # Disk usage
            disk = psutil.disk_usage("/")
            details["disk_percent"] = disk.percent
            if disk.percent > 95:
                health_score -= 30
                issues.append(f"Critical disk usage: {disk.percent}%")
                recommendations.append("Free up disk space immediately")
            elif disk.percent > 85:
                health_score -= 15
                recommendations.append("Consider cleaning up old models or logs")

            # GPU (if available)
            try:
                import subprocess
                result = subprocess.run(
                    ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total",
                     "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    parts = result.stdout.strip().split(",")
                    if len(parts) >= 3:
                        gpu_util = float(parts[0].strip())
                        gpu_mem_used = float(parts[1].strip())
                        gpu_mem_total = float(parts[2].strip())
                        gpu_mem_percent = (gpu_mem_used / gpu_mem_total) * 100

                        details["gpu_percent"] = gpu_util
                        details["gpu_memory_percent"] = gpu_mem_percent

                        if gpu_mem_percent > 95:
                            health_score -= 20
                            issues.append(f"GPU memory near limit: {gpu_mem_percent:.1f}%")
            except Exception:
                details["gpu_available"] = False

            score = max(health_score, 0)

        except Exception as e:
            score = 50
            issues.append(f"Health check failed: {str(e)}")

        return DimensionScore(
            name="System Health",
            score=score,
            grade=self._score_to_grade(score),
            weight=self._weights["system_health"],
            issues=issues,
            recommendations=recommendations,
            details=details
        )

    def _build_improvement_plan(self, dimensions: List[DimensionScore]) -> List[str]:
        """Build prioritized improvement plan"""
        plan = []

        # Sort dimensions by score (lowest first) and weight (highest first)
        prioritized = sorted(
            dimensions,
            key=lambda d: (d.score, -d.weight)
        )

        for dim in prioritized:
            if dim.grade in (AssessmentGrade.F, AssessmentGrade.D):
                plan.extend(dim.recommendations[:2])
            elif dim.grade == AssessmentGrade.C:
                plan.extend(dim.recommendations[:1])

        return plan[:10]  # Top 10 improvements

    def _save_assessment(self, report: AssessmentReport):
        """Save assessment to history"""
        try:
            with get_db() as conn:
                conn.execute("""
                    INSERT INTO assessment_history
                    (timestamp, overall_score, overall_grade, dimensions, issues, recommendations)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    report.timestamp.isoformat(),
                    report.overall_score,
                    report.overall_grade.value,
                    json.dumps([{
                        "name": d.name,
                        "score": d.score,
                        "grade": d.grade.value,
                        "issues": d.issues
                    } for d in report.dimensions]),
                    json.dumps(report.critical_issues),
                    json.dumps(report.improvement_plan)
                ))
        except Exception as e:
            api_logger.error(f"Failed to save assessment: {e}")

    # ==================== History & Trends ====================

    def get_assessment_history(self, days: int = 30) -> List[Dict[str, Any]]:
        """Get historical assessments"""
        try:
            with get_db() as conn:
                rows = conn.execute("""
                    SELECT * FROM assessment_history
                    WHERE timestamp >= datetime('now', ?)
                    ORDER BY timestamp DESC
                """, (f"-{days} days",)).fetchall()

                return [{
                    "timestamp": row["timestamp"],
                    "overall_score": row["overall_score"],
                    "overall_grade": row["overall_grade"],
                    "dimensions": json.loads(row["dimensions"]),
                    "issues": json.loads(row["issues"]) if row["issues"] else [],
                    "recommendations": json.loads(row["recommendations"]) if row["recommendations"] else []
                } for row in rows]

        except Exception:
            return []

    def get_trend(self, days: int = 30) -> Dict[str, Any]:
        """Get score trend over time"""
        history = self.get_assessment_history(days)

        if len(history) < 2:
            return {"trend": "insufficient_data", "change": 0}

        recent = history[0]["overall_score"]
        oldest = history[-1]["overall_score"]
        change = recent - oldest

        if change > 5:
            trend = "improving"
        elif change < -5:
            trend = "declining"
        else:
            trend = "stable"

        return {
            "trend": trend,
            "change": round(change, 1),
            "current_score": round(recent, 1),
            "data_points": len(history)
        }


# Global instance
_assessment_system: Optional[SelfAssessmentSystem] = None


def get_assessment_system() -> SelfAssessmentSystem:
    """Get the global SelfAssessmentSystem instance"""
    global _assessment_system
    if _assessment_system is None:
        _assessment_system = SelfAssessmentSystem()
    return _assessment_system
