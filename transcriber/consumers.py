import asyncio
import contextlib
import json
import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings

from .groq import DEFAULT_LANGUAGE, GroqTranscriber, TranscriberError, append_text
from .models import Transcription

logger = logging.getLogger(__name__)

MAX_CHUNK_BYTES = 64 * 1024


class TranscriptionConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.transcriber = None
        self.full_text = ""
        self.timer = None
        self.lock = asyncio.Lock()
        await self.accept()

    async def disconnect(self, code):
        await self.stop_session(notify=False)

    async def receive(self, text_data=None, bytes_data=None):
        if bytes_data is not None:
            if self.transcriber and len(bytes_data) <= MAX_CHUNK_BYTES:
                await self.transcriber.send_audio(bytes_data)
            return
        try:
            message = json.loads(text_data or "{}")
        except json.JSONDecodeError:
            message = {}
        kind = message.get("type")
        if kind == "start":
            await self.start_session(message.get("language", DEFAULT_LANGUAGE))
        elif kind == "stop":
            await self.stop_session()

    async def start_session(self, language):
        async with self.lock:
            if self.transcriber:
                return
            self.full_text = ""
            transcriber = GroqTranscriber(on_event=self.on_transcriber_event, language=language)
            try:
                await transcriber.start()
            except TranscriberError as exc:
                await self.send_json({"type": "error", "message": str(exc)})
                return
            self.transcriber = transcriber
            self.timer = asyncio.create_task(self.enforce_limit())
        await self.send_json({"type": "ready"})

    async def stop_session(self, notify=True):
        async with self.lock:
            transcriber, self.transcriber = self.transcriber, None
            if transcriber is None:
                return
            if self.timer and self.timer is not asyncio.current_task():
                self.timer.cancel()
            try:
                await transcriber.finish()
            except Exception:
                logger.exception("Error while finishing transcription")
            text = self.full_text.strip()
            if text:
                obj = await database_sync_to_async(Transcription.objects.create)(text=text)
                if notify:
                    await self.send_json({"type": "saved", "id": obj.pk, "text": text})
            elif notify:
                await self.send_json({"type": "stopped"})

    async def enforce_limit(self):
        await asyncio.sleep(settings.MAX_SESSION_SECONDS)
        await self.send_json({"type": "limit"})
        await self.stop_session()

    async def on_transcriber_event(self, event):
        if event["type"] == "final":
            self.full_text = append_text(self.full_text, event["text"])
            await self.send_json({"type": "final", "text": self.full_text})
        else:
            await self.send_json(event)

    async def send_json(self, payload):
        with contextlib.suppress(Exception):
            await self.send(text_data=json.dumps(payload, ensure_ascii=False))
