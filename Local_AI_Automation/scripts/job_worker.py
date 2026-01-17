#!/usr/bin/env python
"""
Job Queue Worker
Processes jobs from the Redis queue

Usage:
    python job_worker.py                    # Process all queues
    python job_worker.py --queues high      # Process specific queue(s)
    python job_worker.py --burst            # Process and exit when empty
"""
import sys
import os
import argparse
import logging
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Check for Redis/RQ availability
try:
    import redis
    from rq import Worker, Queue, Connection
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    print("ERROR: Redis and RQ packages not installed")
    print("Install with: pip install redis rq")
    sys.exit(1)

from api.job_queue import REDIS_HOST, REDIS_PORT, REDIS_DB, REDIS_PASSWORD, QUEUE_NAMES
from api.logging_config import setup_logging


def main():
    parser = argparse.ArgumentParser(description="Job Queue Worker")
    parser.add_argument(
        "--queues",
        nargs="+",
        default=list(QUEUE_NAMES.values()),
        help="Queues to process (default: all)"
    )
    parser.add_argument(
        "--burst",
        action="store_true",
        help="Run in burst mode (exit when queue is empty)"
    )
    parser.add_argument(
        "--name",
        default=None,
        help="Worker name (default: auto-generated)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    logger = logging.getLogger("worker")

    # Connect to Redis
    try:
        redis_conn = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            password=REDIS_PASSWORD,
            decode_responses=False
        )
        redis_conn.ping()
        logger.info(f"Connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        sys.exit(1)

    # Create queues
    # Process in priority order: critical > high > default > low
    queue_order = ["critical", "high", "default", "low"]
    queues = [q for q in queue_order if q in args.queues]
    if not queues:
        queues = args.queues

    logger.info(f"Processing queues: {queues}")

    # Start worker
    with Connection(redis_conn):
        worker_queues = [Queue(name) for name in queues]
        worker = Worker(
            worker_queues,
            name=args.name,
            log_job_description=True
        )

        print("=" * 50)
        print("  LOCAL AI HUB - JOB WORKER")
        print("=" * 50)
        print(f"  Queues: {', '.join(queues)}")
        print(f"  Mode: {'Burst' if args.burst else 'Continuous'}")
        print("=" * 50)
        print("\nWaiting for jobs... (Ctrl+C to stop)")

        try:
            worker.work(burst=args.burst)
        except KeyboardInterrupt:
            logger.info("Worker stopped by user")


if __name__ == "__main__":
    main()
