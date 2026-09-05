import asyncio
import json
from typing import AsyncGenerator
from collections import defaultdict

class EventDispatcher:
    def __init__(self):
        self._queues = defaultdict(list)

    def subscribe(self, channel: str) -> asyncio.Queue:
        queue = asyncio.Queue()
        self._queues[channel].append(queue)
        return queue

    def unsubscribe(self, channel: str, queue: asyncio.Queue) -> None:
        if channel in self._queues and queue in self._queues[channel]:
            self._queues[channel].remove(queue)
            if not self._queues[channel]:
                del self._queues[channel]

    async def publish(self, channel: str, event_type: str, data: dict) -> None:
        if channel not in self._queues:
            return
        
        payload = {
            "event": event_type,
            "data": json.dumps(data)
        }
        
        for queue in self._queues[channel]:
            await queue.put(payload)

    async def event_generator(self, channel: str) -> AsyncGenerator[str, None]:
        queue = self.subscribe(channel)
        try:
            while True:
                payload = await queue.get()
                yield f"event: {payload['event']}\ndata: {payload['data']}\n\n"
        except asyncio.CancelledError:
            self.unsubscribe(channel, queue)
            raise
        except Exception:
            self.unsubscribe(channel, queue)

dispatcher = EventDispatcher()
