"""
GitHub Webhook Handlers
Process GitHub webhook events and trigger actions

Supported Events:
- push: Code pushed to repository
- pull_request: PR opened, closed, merged
- issues: Issue created, closed, labeled
- issue_comment: Comments on issues/PRs
- release: New release published
- workflow_run: GitHub Actions workflow completed
"""
import os
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

from .database import get_db, generate_external_id
from .logging_config import api_logger
from .message_bus import get_message_bus
from .slack_bot import get_slack_bot
from .webhooks import WebhookEvent, webhook_handler


@dataclass
class GitHubEvent:
    """Parsed GitHub webhook event"""
    event_type: str
    action: Optional[str]
    repository: Dict[str, Any]
    sender: Dict[str, Any]
    payload: Dict[str, Any]


def parse_github_event(event_type: str, payload: Dict[str, Any]) -> GitHubEvent:
    """Parse a GitHub webhook payload into a structured event"""
    return GitHubEvent(
        event_type=event_type,
        action=payload.get("action"),
        repository=payload.get("repository", {}),
        sender=payload.get("sender", {}),
        payload=payload
    )


class GitHubWebhookProcessor:
    """
    Processor for GitHub webhook events

    Handles events and can:
    - Create backlog items from issues/PRs
    - Notify via Slack
    - Trigger research on new releases
    - Log activity
    """

    def __init__(self):
        self._handlers = {
            "push": self._handle_push,
            "pull_request": self._handle_pull_request,
            "issues": self._handle_issues,
            "issue_comment": self._handle_issue_comment,
            "release": self._handle_release,
            "workflow_run": self._handle_workflow_run,
            "star": self._handle_star,
            "fork": self._handle_fork,
        }

    async def process(self, event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Process a GitHub webhook event"""
        event = parse_github_event(event_type, payload)

        handler = self._handlers.get(event_type)
        if handler:
            return await handler(event)

        # Default: just log
        api_logger.info(f"GitHub event: {event_type} from {event.repository.get('full_name')}")
        return {"processed": True, "event_type": event_type}

    # ==================== Event Handlers ====================

    async def _handle_push(self, event: GitHubEvent) -> Dict[str, Any]:
        """Handle push event"""
        repo = event.repository.get("full_name", "unknown")
        branch = event.payload.get("ref", "").replace("refs/heads/", "")
        commits = event.payload.get("commits", [])
        pusher = event.payload.get("pusher", {}).get("name", "unknown")

        # Log to database
        self._log_activity("push", {
            "repository": repo,
            "branch": branch,
            "commit_count": len(commits),
            "pusher": pusher
        })

        # Publish to message bus
        bus = get_message_bus()
        await bus.publish(f"github.push.{repo.replace('/', '.')}", {
            "repository": repo,
            "branch": branch,
            "commits": [c.get("message", "")[:100] for c in commits[:5]],
            "pusher": pusher
        })

        # Notify Slack for main branch pushes
        if branch in ("main", "master") and commits:
            bot = get_slack_bot()
            commit_msgs = "\n".join([f"• {c.get('message', '').split(chr(10))[0]}" for c in commits[:3]])
            await bot.send_webhook(
                f"🔀 *{pusher}* pushed {len(commits)} commit(s) to `{repo}:{branch}`\n{commit_msgs}"
            )

        return {
            "processed": True,
            "repository": repo,
            "branch": branch,
            "commits": len(commits)
        }

    async def _handle_pull_request(self, event: GitHubEvent) -> Dict[str, Any]:
        """Handle pull request events"""
        action = event.action
        pr = event.payload.get("pull_request", {})
        repo = event.repository.get("full_name", "unknown")

        pr_number = pr.get("number")
        pr_title = pr.get("title", "")
        pr_author = pr.get("user", {}).get("login", "unknown")
        pr_url = pr.get("html_url", "")

        # Log activity
        self._log_activity("pull_request", {
            "repository": repo,
            "action": action,
            "pr_number": pr_number,
            "title": pr_title,
            "author": pr_author
        })

        # Publish to message bus
        bus = get_message_bus()
        await bus.publish(f"github.pull_request.{action}", {
            "repository": repo,
            "pr_number": pr_number,
            "title": pr_title,
            "author": pr_author,
            "url": pr_url
        })

        # Create backlog item for new PRs (optional - can be configured)
        if action == "opened":
            self._create_backlog_from_pr(pr, repo)

            # Notify Slack
            bot = get_slack_bot()
            await bot.send_webhook(
                text=f"📝 New PR #{pr_number} in `{repo}`",
                blocks=[
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": f"*<{pr_url}|#{pr_number}: {pr_title}>*\nby {pr_author}"}
                    }
                ]
            )

        elif action == "closed" and pr.get("merged"):
            bot = get_slack_bot()
            await bot.send_webhook(f"✅ PR #{pr_number} merged in `{repo}`: {pr_title}")

        return {
            "processed": True,
            "action": action,
            "pr_number": pr_number
        }

    async def _handle_issues(self, event: GitHubEvent) -> Dict[str, Any]:
        """Handle issue events"""
        action = event.action
        issue = event.payload.get("issue", {})
        repo = event.repository.get("full_name", "unknown")

        issue_number = issue.get("number")
        issue_title = issue.get("title", "")
        issue_author = issue.get("user", {}).get("login", "unknown")
        issue_url = issue.get("html_url", "")
        labels = [l.get("name") for l in issue.get("labels", [])]

        # Log activity
        self._log_activity("issue", {
            "repository": repo,
            "action": action,
            "issue_number": issue_number,
            "title": issue_title,
            "author": issue_author,
            "labels": labels
        })

        # Create backlog item for new issues
        if action == "opened":
            self._create_backlog_from_issue(issue, repo)

            # Notify Slack
            bot = get_slack_bot()
            await bot.send_webhook(
                text=f"🐛 New issue #{issue_number} in `{repo}`",
                blocks=[
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": f"*<{issue_url}|#{issue_number}: {issue_title}>*\nby {issue_author}"}
                    }
                ]
            )

        return {
            "processed": True,
            "action": action,
            "issue_number": issue_number
        }

    async def _handle_issue_comment(self, event: GitHubEvent) -> Dict[str, Any]:
        """Handle issue/PR comments"""
        action = event.action
        comment = event.payload.get("comment", {})
        issue = event.payload.get("issue", {})
        repo = event.repository.get("full_name", "unknown")

        # Check for commands in comments (e.g., /task, /research)
        if action == "created":
            body = comment.get("body", "")
            await self._process_comment_commands(body, issue, repo)

        return {"processed": True, "action": action}

    async def _handle_release(self, event: GitHubEvent) -> Dict[str, Any]:
        """Handle release events"""
        action = event.action
        release = event.payload.get("release", {})
        repo = event.repository.get("full_name", "unknown")

        if action == "published":
            tag = release.get("tag_name", "")
            name = release.get("name", tag)
            url = release.get("html_url", "")
            prerelease = release.get("prerelease", False)

            # Log activity
            self._log_activity("release", {
                "repository": repo,
                "tag": tag,
                "name": name,
                "prerelease": prerelease
            })

            # Notify Slack
            bot = get_slack_bot()
            emoji = "🚀" if not prerelease else "🔬"
            await bot.send_webhook(f"{emoji} *{repo}* released *{name}*\n<{url}|View Release>")

            # Publish to message bus
            bus = get_message_bus()
            await bus.publish(f"github.release.{repo.replace('/', '.')}", {
                "repository": repo,
                "tag": tag,
                "name": name,
                "url": url
            })

        return {"processed": True, "action": action, "tag": release.get("tag_name")}

    async def _handle_workflow_run(self, event: GitHubEvent) -> Dict[str, Any]:
        """Handle GitHub Actions workflow events"""
        action = event.action
        workflow = event.payload.get("workflow_run", {})
        repo = event.repository.get("full_name", "unknown")

        if action == "completed":
            conclusion = workflow.get("conclusion", "unknown")
            name = workflow.get("name", "Workflow")
            branch = workflow.get("head_branch", "")

            # Notify on failure
            if conclusion == "failure":
                bot = get_slack_bot()
                await bot.send_webhook(f"❌ Workflow *{name}* failed on `{repo}:{branch}`")

        return {"processed": True, "action": action}

    async def _handle_star(self, event: GitHubEvent) -> Dict[str, Any]:
        """Handle star events"""
        action = event.action
        repo = event.repository.get("full_name", "unknown")
        stars = event.repository.get("stargazers_count", 0)

        if action == "created":
            self._log_activity("star", {"repository": repo, "stars": stars})

        return {"processed": True, "action": action, "stars": stars}

    async def _handle_fork(self, event: GitHubEvent) -> Dict[str, Any]:
        """Handle fork events"""
        repo = event.repository.get("full_name", "unknown")
        forks = event.repository.get("forks_count", 0)

        self._log_activity("fork", {"repository": repo, "forks": forks})

        return {"processed": True, "forks": forks}

    # ==================== Helper Methods ====================

    def _log_activity(self, event_type: str, data: Dict[str, Any]):
        """Log GitHub activity to database"""
        try:
            with get_db() as conn:
                conn.execute("""
                    INSERT INTO webhook_events
                    (id, webhook_id, event_type, payload, headers, source_ip, received_at, processed)
                    VALUES (?, 'github', ?, ?, '{}', 'github.com', ?, 1)
                """, (
                    f"gh_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
                    event_type,
                    str(data),
                    datetime.utcnow().isoformat()
                ))
        except Exception as e:
            api_logger.error(f"Failed to log GitHub activity: {e}")

    def _create_backlog_from_issue(self, issue: Dict[str, Any], repo: str):
        """Create a backlog item from a GitHub issue"""
        try:
            external_id = generate_external_id()
            title = f"[{repo}] {issue.get('title', 'Issue')}"
            description = f"GitHub Issue #{issue.get('number')}\n\n{issue.get('body', '')[:1000]}\n\nURL: {issue.get('html_url')}"

            # Determine priority from labels
            labels = [l.get("name", "").lower() for l in issue.get("labels", [])]
            priority = "P2"
            if "critical" in labels or "urgent" in labels:
                priority = "P0"
            elif "high" in labels or "important" in labels:
                priority = "P1"
            elif "low" in labels:
                priority = "P3"

            with get_db() as conn:
                conn.execute("""
                    INSERT INTO backlog_items
                    (external_id, title, description, priority, category, status, source, created_at)
                    VALUES (?, ?, ?, ?, 'github', 'backlog', 'github', ?)
                """, (external_id, title, description, priority, datetime.utcnow().isoformat()))

            api_logger.info(f"Created backlog item {external_id} from GitHub issue")

        except Exception as e:
            api_logger.error(f"Failed to create backlog from issue: {e}")

    def _create_backlog_from_pr(self, pr: Dict[str, Any], repo: str):
        """Create a backlog item from a GitHub PR"""
        try:
            external_id = generate_external_id()
            title = f"[PR] {pr.get('title', 'Pull Request')}"
            description = f"GitHub PR #{pr.get('number')} in {repo}\n\n{pr.get('body', '')[:1000]}\n\nURL: {pr.get('html_url')}"

            with get_db() as conn:
                conn.execute("""
                    INSERT INTO backlog_items
                    (external_id, title, description, priority, category, status, source, created_at)
                    VALUES (?, ?, ?, 'P2', 'github', 'backlog', 'github', ?)
                """, (external_id, title, description, datetime.utcnow().isoformat()))

            api_logger.info(f"Created backlog item {external_id} from GitHub PR")

        except Exception as e:
            api_logger.error(f"Failed to create backlog from PR: {e}")

    async def _process_comment_commands(self, body: str, issue: Dict, repo: str):
        """Process commands in issue/PR comments"""
        lines = body.strip().split("\n")
        for line in lines:
            line = line.strip()

            if line.startswith("/task"):
                # Create task from comment
                pass

            elif line.startswith("/research"):
                # Start research
                topic = line.replace("/research", "").strip()
                if topic:
                    bus = get_message_bus()
                    await bus.publish("research.requested", {
                        "topic": topic,
                        "source": f"github:{repo}#{issue.get('number')}"
                    })


# Global processor instance
_github_processor: Optional[GitHubWebhookProcessor] = None


def get_github_processor() -> GitHubWebhookProcessor:
    """Get the global GitHub processor instance"""
    global _github_processor
    if _github_processor is None:
        _github_processor = GitHubWebhookProcessor()
    return _github_processor


# Register webhook handler
@webhook_handler("github.*")
async def handle_github_webhook(event: WebhookEvent):
    """Handle GitHub webhooks via the webhook system"""
    processor = get_github_processor()
    await processor.process(event.event_type, event.payload)
