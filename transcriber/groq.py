import array
import asyncio
import io
import json
import logging
import math
import urllib.error
import urllib.request
import uuid
import wave

from django.conf import settings

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16_000
BYTES_PER_SECOND = SAMPLE_RATE * 2
LANGUAGES = {
    "hinglish": {"label": "Hinglish (Hindi + English)", "code": None,
                 "prompt": "नमस्ते, आज की meeting में हम project update discuss करेंगे. Please सबको inform कर देना."},
    "en": {"label": "English only", "code": "en",
           "prompt": "Hello everyone, today we will discuss the project update."},
    "hi": {"label": "Hindi only", "code": "hi",
           "prompt": "नमस्ते, आज हम परियोजना की प्रगति पर चर्चा करेंगे।"},
}
DEFAULT_LANGUAGE = "hinglish"
HALLUCINATIONS = {"thank you.", "thank you", "thanks for watching!", "धन्यवाद", "धन्यवाद।", "you", "."}
RETRYABLE_STATUS = {429, 500, 502, 503}


class TranscriberError(Exception):
    pass


def rms(pcm):
    samples = array.array("h")
    samples.frombytes(pcm[: len(pcm) - len(pcm) % 2])
    if not samples:
        return 0.0
    return math.sqrt(sum(s * s for s in samples) / len(samples))


def pcm_to_wav(pcm):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(pcm)
    return buf.getvalue()


def append_text(full, segment):
    segment = segment.strip()
    if not segment:
        return full
    if not full:
        return segment
    if segment[0] in ",.?!;:।":
        return full + segment
    return f"{full} {segment}"


class GroqTranscriber:
    """Cuts streamed 16 kHz PCM at pauses and transcribes each phrase with Whisper on Groq."""

    min_segment_seconds = 2.5
    max_segment_seconds = 8.0
    pause_seconds = 0.4
    silence_rms = 350.0
    min_speech_rms = 300.0

    def __init__(self, on_event, language=DEFAULT_LANGUAGE):
        self.on_event = on_event
        self.language = LANGUAGES.get(language, LANGUAGES[DEFAULT_LANGUAGE])
        self.model_name = settings.GROQ_WHISPER_MODEL
        self._buffer = bytearray()
        self._quiet_bytes = 0
        self._queue = asyncio.Queue()
        self._worker = None
        self._closed = False

    async def start(self):
        if not settings.GROQ_API_KEY:
            raise TranscriberError("GROQ_API_KEY is not configured on the server.")
        self._worker = asyncio.create_task(self._run())

    async def send_audio(self, pcm):
        if self._closed:
            return
        self._buffer.extend(pcm)
        self._quiet_bytes = self._quiet_bytes + len(pcm) if rms(pcm) < self.silence_rms else 0
        seconds = len(self._buffer) / BYTES_PER_SECOND
        paused = self._quiet_bytes >= self.pause_seconds * BYTES_PER_SECOND
        if seconds >= self.max_segment_seconds or (seconds >= self.min_segment_seconds and paused):
            self._cut()

    def _cut(self):
        segment = bytes(self._buffer)
        self._buffer.clear()
        self._quiet_bytes = 0
        if segment and rms(segment) >= self.min_speech_rms:
            self._queue.put_nowait(segment)

    async def _run(self):
        while True:
            segment = await self._queue.get()
            if segment is None:
                return
            await self.on_event({"type": "interim", "text": "…"})
            try:
                text = await self.transcribe(segment)
            except Exception as exc:
                logger.exception("Transcription failed")
                await self.on_event({"type": "error", "message": f"Transcription failed: {exc}"})
                continue
            if text:
                await self.on_event({"type": "final", "text": text})
            else:
                await self.on_event({"type": "interim", "text": ""})

    async def finish(self):
        if self._closed:
            return
        self._closed = True
        if len(self._buffer) >= 0.3 * BYTES_PER_SECOND:
            self._cut()
        self._queue.put_nowait(None)
        if self._worker:
            try:
                await asyncio.wait_for(self._worker, timeout=30)
            except asyncio.TimeoutError:
                self._worker.cancel()

    async def abort(self):
        self._closed = True
        if self._worker:
            self._worker.cancel()

    async def transcribe(self, pcm):
        fields = {
            "model": settings.GROQ_WHISPER_MODEL,
            "response_format": "json",
            "temperature": "0",
            "prompt": self.language["prompt"],
        }
        if self.language["code"]:
            fields["language"] = self.language["code"]
        body, content_type = self._multipart(fields, pcm_to_wav(pcm))
        for attempt in range(2):
            try:
                text = await asyncio.to_thread(self._post, body, content_type)
                break
            except urllib.error.HTTPError as exc:
                if exc.code in RETRYABLE_STATUS and attempt == 0:
                    await asyncio.sleep(1.5)
                    continue
                raise TranscriberError(f"Groq API error {exc.code}: {self._error_message(exc)}") from exc
        text = text.strip()
        return "" if text.lower() in HALLUCINATIONS else text

    @staticmethod
    def _multipart(fields, wav):
        boundary = f"----stt{uuid.uuid4().hex}"
        parts = [
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
            for name, value in fields.items()
        ]
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="segment.wav"\r\n'
            "Content-Type: audio/wav\r\n\r\n".encode() + wav + b"\r\n"
        )
        parts.append(f"--{boundary}--\r\n".encode())
        return b"".join(parts), f"multipart/form-data; boundary={boundary}"

    @staticmethod
    def _post(body, content_type):
        request = urllib.request.Request(
            settings.GROQ_API_URL,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                "Content-Type": content_type,
                "User-Agent": "speech-to-text/1.0",
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8")).get("text", "")

    @staticmethod
    def _error_message(exc):
        detail = exc.read().decode("utf-8", "replace")
        try:
            return json.loads(detail)["error"]["message"]
        except (ValueError, KeyError, TypeError):
            return detail[:300]
