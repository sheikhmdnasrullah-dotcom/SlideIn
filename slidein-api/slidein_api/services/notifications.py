"""Notification dispatcher for 24/7 background alerts via Telegram, Discord, and Slack.

Operates autonomously on the VPS / cloud background worker to notify operators
immediately when:
1. An inbound prospect reply arrives (including 24-hr grace period countdown).
2. A meeting is booked via Notion Calendar or synced link.
3. A human takeover is triggered.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional
import httpx

logger = logging.getLogger("slidein.notifications")


class NotificationDispatcher:
    """Dispatches real-time alerts across configured messenger webhooks."""

    def __init__(
        self,
        telegram_bot_token: Optional[str] = None,
        telegram_chat_id: Optional[str] = None,
        discord_webhook_url: Optional[str] = None,
        slack_webhook_url: Optional[str] = None,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.telegram_bot_token = telegram_bot_token
        self.telegram_chat_id = telegram_chat_id
        self.discord_webhook_url = discord_webhook_url
        self.slack_webhook_url = slack_webhook_url
        self._client = client

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None and not self._client.is_closed:
            return self._client
        return httpx.AsyncClient(timeout=10.0)

    async def notify_inbound_reply(
        self,
        *,
        tenant_id: str,
        prospect_name: str,
        prospect_email: str,
        company: str,
        subject: str,
        summary: str,
        intent: str,
        grace_deadline_iso: str,
    ) -> Dict[str, bool]:
        """Send notification about a new prospect reply and start of 24h grace period."""
        results = {}

        # 1. Telegram
        if self.telegram_bot_token and self.telegram_chat_id:
            tg_text = (
                f"📬 *New Inbound Reply Received*\n\n"
                f"*Prospect:* {prospect_name} ({company})\n"
                f"*Email:* `{prospect_email}`\n"
                f"*Intent:* {intent.upper()}\n"
                f"*Subject:* {subject}\n"
                f"*Summary:* {summary}\n\n"
                f"⏳ *Human Grace Window:* 24 business hrs\n"
                f"Agent will auto-reply on: `{grace_deadline_iso}` if unhandled."
            )
            results["telegram"] = await self._send_telegram(tg_text)

        # 2. Discord Webhook
        if self.discord_webhook_url:
            discord_payload = {
                "username": "SlideIn Operations",
                "avatar_url": "https://slidein.me/icon.png",
                "embeds": [
                    {
                        "title": f"📬 Inbound Reply: {prospect_name} ({company})",
                        "description": summary,
                        "color": 0xFF6B00,  # SlideIn Brand Orange
                        "fields": [
                            {"name": "Email", "value": prospect_email, "inline": True},
                            {"name": "Intent", "value": intent.capitalize(), "inline": True},
                            {"name": "Subject", "value": subject, "inline": False},
                            {"name": "24h Grace Deadline", "value": grace_deadline_iso, "inline": False},
                        ],
                        "footer": {"text": f"Tenant: {tenant_id} • 24/7 VPS Telemetry"},
                    }
                ],
            }
            results["discord"] = await self._send_discord(discord_payload)

        # 3. Slack Webhook
        if self.slack_webhook_url:
            slack_payload = {
                "text": f"📬 Inbound Reply from {prospect_name} ({company})",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": (
                                f"*📬 New Inbound Reply Received*\n"
                                f"*{prospect_name}* from *{company}* (`{prospect_email}`)\n"
                                f"*Intent:* {intent} | *Deadline:* {grace_deadline_iso}\n"
                                f"> {summary}"
                            ),
                        },
                    }
                ],
            }
            results["slack"] = await self._send_slack(slack_payload)

        return results

    async def notify_meeting_booked(
        self,
        *,
        tenant_id: str,
        prospect_name: str,
        prospect_email: str,
        company: str,
        meeting_time: str,
        calendar_link: str,
    ) -> Dict[str, bool]:
        """Send notification when a meeting is confirmed via Notion or dedicated link."""
        results = {}

        if self.telegram_bot_token and self.telegram_chat_id:
            tg_text = (
                f"🎉 *New Meeting Confirmed!*\n\n"
                f"*Prospect:* {prospect_name} ({company})\n"
                f"*Email:* `{prospect_email}`\n"
                f"*Meeting Time:* {meeting_time}\n"
                f"*Calendar Link:* {calendar_link}\n"
            )
            results["telegram"] = await self._send_telegram(tg_text)

        if self.discord_webhook_url:
            discord_payload = {
                "username": "SlideIn Booking",
                "embeds": [
                    {
                        "title": f"🎉 Meeting Booked: {prospect_name} ({company})",
                        "color": 0x22C55E,  # Green
                        "fields": [
                            {"name": "Time", "value": meeting_time, "inline": True},
                            {"name": "Email", "value": prospect_email, "inline": True},
                            {"name": "Calendar", "value": f"[View Booking]({calendar_link})", "inline": False},
                        ],
                        "footer": {"text": f"Tenant: {tenant_id}"},
                    }
                ],
            }
            results["discord"] = await self._send_discord(discord_payload)

        if self.slack_webhook_url:
            slack_payload = {
                "text": f"🎉 Meeting Booked with {prospect_name} ({meeting_time})",
            }
            results["slack"] = await self._send_slack(slack_payload)

        return results

    async def _send_telegram(self, text: str) -> bool:
        try:
            client = await self._get_client()
            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
            resp = await client.post(
                url,
                json={"chat_id": self.telegram_chat_id, "text": text, "parse_mode": "Markdown"},
            )
            return resp.status_code == 200
        except Exception as exc:
            logger.warning("Failed to dispatch Telegram alert: %s", exc)
            return False

    async def _send_discord(self, payload: Dict[str, Any]) -> bool:
        try:
            client = await self._get_client()
            resp = await client.post(str(self.discord_webhook_url), json=payload)
            return resp.status_code in (200, 204)
        except Exception as exc:
            logger.warning("Failed to dispatch Discord webhook: %s", exc)
            return False

    async def _send_slack(self, payload: Dict[str, Any]) -> bool:
        try:
            client = await self._get_client()
            resp = await client.post(str(self.slack_webhook_url), json=payload)
            return resp.status_code == 200
        except Exception as exc:
            logger.warning("Failed to dispatch Slack webhook: %s", exc)
            return False
