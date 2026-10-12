"""
Acquisition OS — Event System
Publishes and consumes domain events.
"""

from datetime import datetime
from typing import Dict, Any, List, Optional, Callable
import asyncio
import logging

logger = logging.getLogger(__name__)


class Event:
    """Domain event."""
    def __init__(self, event_type: str, data: Dict[str, Any], org_id: str, timestamp: Optional[datetime] = None):
        self.event_type = event_type
        self.data = data
        self.org_id = org_id
        self.timestamp = timestamp or datetime.utcnow()


class EventPublisher:
    """Publishes events to subscribers."""

    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = {}

    def subscribe(self, event_type: str, handler: Callable):
        """Subscribe a handler to an event type."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)

    async def publish(self, event_type: str, data: Dict[str, Any], org_id: str):
        """Publish an event to all subscribers."""
        event = Event(event_type, data, org_id)
        handlers = self._subscribers.get(event_type, [])
        if not handlers:
            return

        tasks = []
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    tasks.append(handler(event))
                else:
                    tasks.append(asyncio.get_event_loop().run_in_executor(None, handler, event))
            except Exception as e:
                logger.error(f"Error preparing handler for {event_type}: {e}")

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"Error in event handler for {event_type}: {result}")


class EventBus:
    """
    Global event bus singleton.
    """
    _instance: Optional["EventBus"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.publisher = EventPublisher()
        return cls._instance

    @classmethod
    def get(cls) -> "EventBus":
        return cls()

    def subscribe(self, event_type: str, handler: Callable):
        self.publisher.subscribe(event_type, handler)

    async def publish(self, event_type: str, data: Dict[str, Any], org_id: str):
        await self.publisher.publish(event_type, data, org_id)


class EventTypes:
    OPPORTUNITY_DISCOVERED = "opportunity_discovered"
    OPPORTUNITY_RESEARCHED = "opportunity_researched"
    OPPORTUNITY_QUALIFIED = "opportunity_qualified"
    OPPORTUNITY_STATE_CHANGED = "opportunity_state_changed"
    OPPORTUNITY_SCORE_UPDATED = "opportunity_score_updated"
    MESSAGE_SENT = "message_sent"
    MESSAGE_DELIVERED = "message_delivered"
    MESSAGE_OPENED = "message_opened"
    MESSAGE_CLICKED = "message_clicked"
    MESSAGE_REPLIED = "message_replied"
    MESSAGE_BOUNCED = "message_bounced"
    MESSAGE_COMPLAINED = "message_complained"
    HIGH_INTENT_DETECTED = "high_intent_detected"
    CONVERSATION_CREATED = "conversation_created"
    CONVERSATION_CLOSED = "conversation_closed"
    APPOINTMENT_BOOKED = "appointment_booked"
    APPOINTMENT_CANCELLED = "appointment_cancelled"
    CONTENT_CREATED = "content_created"
    CONTENT_PUBLISHED = "content_published"
    CAMPAIGN_STARTED = "campaign_started"
    CAMPAIGN_PAUSED = "campaign_paused"
    AUTOMATION_TRIGGERED = "automation_triggered"
    SYSTEM_ACTIVITY = "system_activity"
    ACQUISITION_HEALTH_UPDATED = "acquisition_health_updated"


async def _log_event_handler(event: Event):
    """Default handler that logs all events."""
    logger.info(f"[EVENT] {event.event_type}: {event.data.get('id', '')} (org={event.org_id})")


async def _system_activity_handler(event: Event):
    """Handler that creates system activity entries for important events."""
    if event.event_type in [
        EventTypes.OPPORTUNITY_DISCOVERED,
        EventTypes.OPPORTUNITY_RESEARCHED,
        EventTypes.HIGH_INTENT_DETECTED,
        EventTypes.MESSAGE_SENT,
        EventTypes.MESSAGE_REPLIED,
        EventTypes.APPOINTMENT_BOOKED,
        EventTypes.CONTENT_PUBLISHED,
        EventTypes.AUTOMATION_TRIGGERED,
    ]:
        logger.info(f"[SYSTEM_ACTIVITY] {event.event_type}: {event.data}")


async def _opportunity_state_handler(event: Event):
    """Handler that reacts to opportunity state changes."""
    if event.event_type == EventTypes.OPPORTUNITY_STATE_CHANGED:
        logger.info(f"[STATE_CHANGE] Opportunity {event.data.get('id')} moved to {event.data.get('to_state')}")


def register_default_handlers(event_bus: EventBus):
    """Register default event handlers."""
    event_bus.subscribe("*", _log_event_handler)
    event_bus.subscribe(EventTypes.OPPORTUNITY_STATE_CHANGED, _opportunity_state_handler)
    event_bus.subscribe(EventTypes.SYSTEM_ACTIVITY, _system_activity_handler)
