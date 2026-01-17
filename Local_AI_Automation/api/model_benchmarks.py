"""
Model Performance Tracking & Benchmarks
Track, benchmark, and compare model performance

Features:
- Response time tracking
- Quality benchmarks (coherence, accuracy, creativity)
- Model comparison
- Usage pattern analysis
- Performance trends
"""
import json
import time
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict

from .database import get_db
from .logging_config import api_logger


class BenchmarkType(Enum):
    """Types of benchmarks"""
    RESPONSE_TIME = "response_time"
    COHERENCE = "coherence"
    INSTRUCTION_FOLLOWING = "instruction_following"
    CODE_GENERATION = "code_generation"
    REASONING = "reasoning"
    CREATIVITY = "creativity"
    FACTUAL_ACCURACY = "factual_accuracy"


@dataclass
class BenchmarkResult:
    """Result of a single benchmark"""
    model: str
    benchmark_type: BenchmarkType
    score: float
    latency_ms: float
    tokens_per_second: float
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ModelMetrics:
    """Aggregated metrics for a model"""
    model_name: str
    total_requests: int
    avg_latency_ms: float
    p95_latency_ms: float
    tokens_generated: int
    avg_tokens_per_second: float
    error_rate: float
    benchmark_scores: Dict[str, float]


class ModelBenchmarkSystem:
    """
    Model performance tracking and benchmarking system

    Tracks all model interactions and runs periodic benchmarks
    to assess quality and performance.
    """

    def __init__(self):
        self._benchmark_prompts = self._load_benchmark_prompts()
        self._init_database()

    def _init_database(self):
        """Initialize benchmark tables"""
        try:
            with get_db() as conn:
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS model_requests (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        model TEXT NOT NULL,
                        prompt_tokens INTEGER,
                        completion_tokens INTEGER,
                        latency_ms REAL NOT NULL,
                        success INTEGER DEFAULT 1,
                        error_message TEXT,
                        timestamp TEXT NOT NULL
                    );

                    CREATE INDEX IF NOT EXISTS idx_model_requests_model
                    ON model_requests(model);

                    CREATE INDEX IF NOT EXISTS idx_model_requests_time
                    ON model_requests(timestamp);

                    CREATE TABLE IF NOT EXISTS benchmark_results (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        model TEXT NOT NULL,
                        benchmark_type TEXT NOT NULL,
                        score REAL NOT NULL,
                        latency_ms REAL,
                        tokens_per_second REAL,
                        details TEXT,
                        timestamp TEXT NOT NULL
                    );

                    CREATE INDEX IF NOT EXISTS idx_benchmark_model
                    ON benchmark_results(model, benchmark_type);

                    CREATE TABLE IF NOT EXISTS model_comparisons (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        model_a TEXT NOT NULL,
                        model_b TEXT NOT NULL,
                        benchmark_type TEXT NOT NULL,
                        winner TEXT,
                        score_diff REAL,
                        compared_at TEXT NOT NULL
                    );
                """)
        except Exception as e:
            api_logger.error(f"Failed to init benchmark tables: {e}")

    def _load_benchmark_prompts(self) -> Dict[BenchmarkType, List[Dict[str, Any]]]:
        """Load benchmark test prompts"""
        return {
            BenchmarkType.COHERENCE: [
                {
                    "prompt": "Write a short story about a robot learning to paint. Include a beginning, middle, and end.",
                    "criteria": ["has_structure", "makes_sense", "on_topic"]
                },
                {
                    "prompt": "Explain the concept of machine learning to a 10-year-old.",
                    "criteria": ["clarity", "appropriate_level", "accurate"]
                }
            ],
            BenchmarkType.INSTRUCTION_FOLLOWING: [
                {
                    "prompt": "List exactly 5 fruits that are red. Format as a numbered list.",
                    "expected_format": "numbered_list",
                    "expected_count": 5
                },
                {
                    "prompt": "Write a haiku about the ocean. A haiku has 5-7-5 syllables.",
                    "expected_format": "haiku"
                }
            ],
            BenchmarkType.CODE_GENERATION: [
                {
                    "prompt": "Write a Python function that checks if a number is prime.",
                    "test_cases": [(2, True), (4, False), (17, True), (1, False)]
                },
                {
                    "prompt": "Write a Python function to reverse a string without using [::-1].",
                    "test_cases": [("hello", "olleh"), ("", ""), ("a", "a")]
                }
            ],
            BenchmarkType.REASONING: [
                {
                    "prompt": "If all roses are flowers, and some flowers fade quickly, can we conclude that some roses fade quickly?",
                    "expected_keywords": ["cannot", "no", "does not follow"]
                },
                {
                    "prompt": "A farmer has 17 sheep. All but 9 run away. How many sheep does the farmer have left?",
                    "expected_answer": "9"
                }
            ],
            BenchmarkType.CREATIVITY: [
                {
                    "prompt": "Invent a new word and define it. Then use it in a sentence.",
                    "criteria": ["novel_word", "clear_definition", "proper_usage"]
                },
                {
                    "prompt": "Describe a color that doesn't exist yet. What would it look like? What would you name it?",
                    "criteria": ["imagination", "detail", "coherence"]
                }
            ],
            BenchmarkType.FACTUAL_ACCURACY: [
                {
                    "prompt": "What is the capital of France?",
                    "expected": "Paris"
                },
                {
                    "prompt": "Who wrote Romeo and Juliet?",
                    "expected": "Shakespeare"
                },
                {
                    "prompt": "What is the chemical symbol for gold?",
                    "expected": "Au"
                }
            ]
        }

    # ==================== Request Tracking ====================

    def track_request(
        self,
        model: str,
        latency_ms: float,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        success: bool = True,
        error_message: str = None
    ):
        """Track a model request"""
        try:
            with get_db() as conn:
                conn.execute("""
                    INSERT INTO model_requests
                    (model, prompt_tokens, completion_tokens, latency_ms, success, error_message, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    model,
                    prompt_tokens,
                    completion_tokens,
                    latency_ms,
                    1 if success else 0,
                    error_message,
                    datetime.utcnow().isoformat()
                ))
        except Exception as e:
            api_logger.error(f"Failed to track request: {e}")

    def get_model_metrics(
        self,
        model: str,
        days: int = 7
    ) -> Optional[ModelMetrics]:
        """Get aggregated metrics for a model"""
        try:
            with get_db() as conn:
                since = (datetime.utcnow() - timedelta(days=days)).isoformat()

                # Basic stats
                row = conn.execute("""
                    SELECT
                        COUNT(*) as total,
                        AVG(latency_ms) as avg_latency,
                        SUM(completion_tokens) as total_tokens,
                        AVG(CASE WHEN latency_ms > 0 AND completion_tokens > 0
                            THEN completion_tokens * 1000.0 / latency_ms ELSE 0 END) as avg_tps,
                        SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) * 1.0 / COUNT(*) as error_rate
                    FROM model_requests
                    WHERE model = ? AND timestamp >= ?
                """, (model, since)).fetchone()

                if not row or row["total"] == 0:
                    return None

                # P95 latency
                p95_row = conn.execute("""
                    SELECT latency_ms FROM model_requests
                    WHERE model = ? AND timestamp >= ?
                    ORDER BY latency_ms
                    LIMIT 1 OFFSET (
                        SELECT CAST(COUNT(*) * 0.95 AS INTEGER)
                        FROM model_requests
                        WHERE model = ? AND timestamp >= ?
                    )
                """, (model, since, model, since)).fetchone()

                p95 = p95_row["latency_ms"] if p95_row else row["avg_latency"]

                # Get benchmark scores
                benchmark_rows = conn.execute("""
                    SELECT benchmark_type, AVG(score) as avg_score
                    FROM benchmark_results
                    WHERE model = ? AND timestamp >= ?
                    GROUP BY benchmark_type
                """, (model, since)).fetchall()

                benchmark_scores = {row["benchmark_type"]: row["avg_score"] for row in benchmark_rows}

                return ModelMetrics(
                    model_name=model,
                    total_requests=row["total"],
                    avg_latency_ms=round(row["avg_latency"], 2),
                    p95_latency_ms=round(p95, 2),
                    tokens_generated=row["total_tokens"] or 0,
                    avg_tokens_per_second=round(row["avg_tps"] or 0, 2),
                    error_rate=round(row["error_rate"] * 100, 2),
                    benchmark_scores=benchmark_scores
                )

        except Exception as e:
            api_logger.error(f"Failed to get model metrics: {e}")
            return None

    # ==================== Benchmarking ====================

    async def run_benchmark(
        self,
        model: str,
        benchmark_type: BenchmarkType,
        ollama_url: str = "http://localhost:11434"
    ) -> BenchmarkResult:
        """Run a specific benchmark on a model"""
        import httpx

        prompts = self._benchmark_prompts.get(benchmark_type, [])
        if not prompts:
            return BenchmarkResult(
                model=model,
                benchmark_type=benchmark_type,
                score=0,
                latency_ms=0,
                tokens_per_second=0,
                details={"error": "No prompts for benchmark type"}
            )

        scores = []
        total_latency = 0
        total_tokens = 0

        async with httpx.AsyncClient(timeout=120.0) as client:
            for prompt_data in prompts:
                prompt = prompt_data["prompt"]
                start_time = time.time()

                try:
                    response = await client.post(
                        f"{ollama_url}/api/generate",
                        json={
                            "model": model,
                            "prompt": prompt,
                            "stream": False
                        }
                    )

                    latency = (time.time() - start_time) * 1000
                    total_latency += latency

                    if response.status_code == 200:
                        result = response.json()
                        answer = result.get("response", "")
                        tokens = result.get("eval_count", len(answer.split()))
                        total_tokens += tokens

                        # Score the response
                        score = self._score_response(benchmark_type, prompt_data, answer)
                        scores.append(score)

                except Exception as e:
                    api_logger.error(f"Benchmark failed: {e}")
                    scores.append(0)

        avg_score = sum(scores) / len(scores) if scores else 0
        avg_latency = total_latency / len(prompts) if prompts else 0
        tps = (total_tokens / (total_latency / 1000)) if total_latency > 0 else 0

        result = BenchmarkResult(
            model=model,
            benchmark_type=benchmark_type,
            score=avg_score,
            latency_ms=avg_latency,
            tokens_per_second=tps,
            details={
                "prompts_tested": len(prompts),
                "individual_scores": scores
            }
        )

        # Save result
        self._save_benchmark_result(result)

        return result

    def _score_response(
        self,
        benchmark_type: BenchmarkType,
        prompt_data: Dict[str, Any],
        response: str
    ) -> float:
        """Score a benchmark response (0-100)"""
        response_lower = response.lower()

        if benchmark_type == BenchmarkType.FACTUAL_ACCURACY:
            expected = prompt_data.get("expected", "").lower()
            if expected in response_lower:
                return 100
            return 0

        elif benchmark_type == BenchmarkType.REASONING:
            expected_keywords = prompt_data.get("expected_keywords", [])
            expected_answer = prompt_data.get("expected_answer", "")

            if expected_answer and expected_answer.lower() in response_lower:
                return 100
            if expected_keywords:
                matches = sum(1 for kw in expected_keywords if kw.lower() in response_lower)
                return (matches / len(expected_keywords)) * 100
            return 50  # Can't evaluate

        elif benchmark_type == BenchmarkType.INSTRUCTION_FOLLOWING:
            score = 50  # Base score

            expected_format = prompt_data.get("expected_format")
            expected_count = prompt_data.get("expected_count")

            if expected_format == "numbered_list":
                # Check for numbered items
                lines = [l.strip() for l in response.split("\n") if l.strip()]
                numbered = [l for l in lines if l[0].isdigit() if l]
                if numbered:
                    score += 25
                    if expected_count and len(numbered) == expected_count:
                        score += 25

            elif expected_format == "haiku":
                lines = [l.strip() for l in response.split("\n") if l.strip()]
                if len(lines) == 3:
                    score += 50

            return min(score, 100)

        elif benchmark_type == BenchmarkType.CODE_GENERATION:
            # Check if code is present and looks valid
            if "def " in response or "function" in response:
                score = 50

                # Try to extract and test code (simplified)
                test_cases = prompt_data.get("test_cases", [])
                if "def " in response and test_cases:
                    # Extract function
                    try:
                        # Very basic code extraction
                        code_start = response.find("def ")
                        code_end = response.find("\n\n", code_start)
                        if code_end == -1:
                            code_end = len(response)

                        # For safety, don't actually execute - just check structure
                        code = response[code_start:code_end]
                        if "return" in code:
                            score += 25
                        if ":" in code and "(" in code:
                            score += 25
                    except Exception:
                        pass

                return score
            return 20

        elif benchmark_type == BenchmarkType.COHERENCE:
            # Basic coherence check
            score = 50

            # Has reasonable length
            if 50 < len(response) < 2000:
                score += 20

            # Has sentence structure
            if "." in response and response[0].isupper():
                score += 15

            # Mentions topic keywords
            criteria = prompt_data.get("criteria", [])
            if criteria:
                # Simplified check
                score += 15

            return min(score, 100)

        elif benchmark_type == BenchmarkType.CREATIVITY:
            # Creativity is hard to measure automatically
            score = 50

            # Longer, more detailed responses get higher scores
            if len(response) > 200:
                score += 20
            if len(response) > 500:
                score += 15

            # Check for variety in vocabulary (simple proxy)
            words = response.split()
            unique_ratio = len(set(words)) / len(words) if words else 0
            score += int(unique_ratio * 15)

            return min(score, 100)

        return 50  # Default neutral score

    def _save_benchmark_result(self, result: BenchmarkResult):
        """Save benchmark result to database"""
        try:
            with get_db() as conn:
                conn.execute("""
                    INSERT INTO benchmark_results
                    (model, benchmark_type, score, latency_ms, tokens_per_second, details, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    result.model,
                    result.benchmark_type.value,
                    result.score,
                    result.latency_ms,
                    result.tokens_per_second,
                    json.dumps(result.details),
                    result.timestamp.isoformat()
                ))
        except Exception as e:
            api_logger.error(f"Failed to save benchmark: {e}")

    async def run_full_benchmark_suite(
        self,
        model: str,
        ollama_url: str = "http://localhost:11434"
    ) -> Dict[str, Any]:
        """Run all benchmarks on a model"""
        results = {}

        for benchmark_type in BenchmarkType:
            if benchmark_type == BenchmarkType.RESPONSE_TIME:
                continue  # This is tracked automatically

            result = await self.run_benchmark(model, benchmark_type, ollama_url)
            results[benchmark_type.value] = {
                "score": round(result.score, 1),
                "latency_ms": round(result.latency_ms, 2),
                "tokens_per_second": round(result.tokens_per_second, 2)
            }

        # Calculate overall score
        overall = sum(r["score"] for r in results.values()) / len(results) if results else 0

        return {
            "model": model,
            "overall_score": round(overall, 1),
            "benchmarks": results,
            "timestamp": datetime.utcnow().isoformat()
        }

    # ==================== Model Comparison ====================

    async def compare_models(
        self,
        model_a: str,
        model_b: str,
        benchmark_type: BenchmarkType,
        ollama_url: str = "http://localhost:11434"
    ) -> Dict[str, Any]:
        """Compare two models on a specific benchmark"""
        result_a = await self.run_benchmark(model_a, benchmark_type, ollama_url)
        result_b = await self.run_benchmark(model_b, benchmark_type, ollama_url)

        winner = model_a if result_a.score > result_b.score else (
            model_b if result_b.score > result_a.score else "tie"
        )
        score_diff = abs(result_a.score - result_b.score)

        # Save comparison
        try:
            with get_db() as conn:
                conn.execute("""
                    INSERT INTO model_comparisons
                    (model_a, model_b, benchmark_type, winner, score_diff, compared_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    model_a, model_b, benchmark_type.value,
                    winner, score_diff, datetime.utcnow().isoformat()
                ))
        except Exception:
            pass

        return {
            "model_a": {
                "name": model_a,
                "score": round(result_a.score, 1),
                "latency_ms": round(result_a.latency_ms, 2),
                "tps": round(result_a.tokens_per_second, 2)
            },
            "model_b": {
                "name": model_b,
                "score": round(result_b.score, 1),
                "latency_ms": round(result_b.latency_ms, 2),
                "tps": round(result_b.tokens_per_second, 2)
            },
            "winner": winner,
            "score_difference": round(score_diff, 1),
            "benchmark": benchmark_type.value
        }

    def get_leaderboard(
        self,
        benchmark_type: Optional[BenchmarkType] = None,
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """Get model leaderboard"""
        try:
            with get_db() as conn:
                since = (datetime.utcnow() - timedelta(days=days)).isoformat()

                if benchmark_type:
                    rows = conn.execute("""
                        SELECT model, AVG(score) as avg_score,
                               AVG(latency_ms) as avg_latency,
                               AVG(tokens_per_second) as avg_tps,
                               COUNT(*) as runs
                        FROM benchmark_results
                        WHERE benchmark_type = ? AND timestamp >= ?
                        GROUP BY model
                        ORDER BY avg_score DESC
                    """, (benchmark_type.value, since)).fetchall()
                else:
                    rows = conn.execute("""
                        SELECT model, AVG(score) as avg_score,
                               AVG(latency_ms) as avg_latency,
                               AVG(tokens_per_second) as avg_tps,
                               COUNT(*) as runs
                        FROM benchmark_results
                        WHERE timestamp >= ?
                        GROUP BY model
                        ORDER BY avg_score DESC
                    """, (since,)).fetchall()

                return [
                    {
                        "rank": i + 1,
                        "model": row["model"],
                        "avg_score": round(row["avg_score"], 1),
                        "avg_latency_ms": round(row["avg_latency"], 2),
                        "avg_tps": round(row["avg_tps"], 2),
                        "benchmark_runs": row["runs"]
                    }
                    for i, row in enumerate(rows)
                ]

        except Exception as e:
            api_logger.error(f"Failed to get leaderboard: {e}")
            return []

    def get_performance_trends(
        self,
        model: str,
        days: int = 30
    ) -> Dict[str, Any]:
        """Get performance trends for a model over time"""
        try:
            with get_db() as conn:
                since = (datetime.utcnow() - timedelta(days=days)).isoformat()

                # Daily averages
                rows = conn.execute("""
                    SELECT
                        date(timestamp) as date,
                        AVG(latency_ms) as avg_latency,
                        AVG(CASE WHEN completion_tokens > 0 AND latency_ms > 0
                            THEN completion_tokens * 1000.0 / latency_ms ELSE 0 END) as avg_tps,
                        COUNT(*) as requests,
                        SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as errors
                    FROM model_requests
                    WHERE model = ? AND timestamp >= ?
                    GROUP BY date(timestamp)
                    ORDER BY date
                """, (model, since)).fetchall()

                return {
                    "model": model,
                    "period_days": days,
                    "daily_data": [
                        {
                            "date": row["date"],
                            "avg_latency_ms": round(row["avg_latency"], 2),
                            "avg_tps": round(row["avg_tps"], 2),
                            "requests": row["requests"],
                            "errors": row["errors"]
                        }
                        for row in rows
                    ]
                }

        except Exception as e:
            api_logger.error(f"Failed to get trends: {e}")
            return {"model": model, "daily_data": []}


# Global instance
_benchmark_system: Optional[ModelBenchmarkSystem] = None


def get_benchmark_system() -> ModelBenchmarkSystem:
    """Get the global ModelBenchmarkSystem instance"""
    global _benchmark_system
    if _benchmark_system is None:
        _benchmark_system = ModelBenchmarkSystem()
    return _benchmark_system
