SPEECH TO TEXT - REAL-TIME TRANSCRIPTION
========================================

A web application that transcribes speech in real time, including speech that
mixes Hindi and English in the same sentence. Every transcription is stored in
a PostgreSQL database and shown on a history dashboard with full CRUD
(create, read, update, delete). Saved transcriptions can be played back as
speech (text to speech).


1. TECHNOLOGY STACK
-------------------
Backend        : Python 3.12+, Django 5.1
Real-time      : Django Channels (WebSockets) served by Daphne (ASGI server)
Database       : PostgreSQL (via dj-database-url and psycopg)
Speech to text : Whisper large-v3-turbo (open-source model by OpenAI),
                 served through Groq's free API
Text to speech : Browser Web Speech API (no key, no server cost)
Frontend       : Django templates, plain JavaScript, AudioWorklet
Static files   : WhiteNoise
Hosting        : Render (free web service + free PostgreSQL)


2. HOW THE SYSTEM WORKS
-----------------------

  Browser microphone
        |
        v
  AudioWorklet (pcm-worklet.js)
    converts mic audio to 16 kHz, 16-bit, mono PCM, sent every 100 ms
        |
        v   binary WebSocket frames  ->  /ws/transcribe/
  Django Channels consumer (consumers.py)
        |
        v
  GroqTranscriber (groq.py)
    - buffers the audio stream
    - detects pauses by measuring loudness (RMS) of each 100 ms block
    - cuts a segment at a pause (min 2.5 s) or after 8 s of continuous speech
    - skips silent segments
    - wraps each segment as a WAV file and sends it to Groq Whisper
        |
        v
  Groq API  (whisper-large-v3-turbo)
    returns the text for that segment (Hindi in Devanagari, English in Latin)
        |
        v
  Consumer appends the text to the running transcript and pushes it
  back to the browser over the same WebSocket -> text appears on screen
        |
        v   user presses Stop
  Remaining audio is transcribed, the full transcript is saved to
  PostgreSQL, and the browser shows "Saved to history."


Step by step for one recording:

  1. The user opens the Record page, picks a language and clicks the red
     button.
  2. The browser asks for microphone permission and opens a WebSocket to
     the server.
  3. The browser sends {"type": "start", "language": "<choice>"} with the
     language picked in the dropdown. The server creates a
     GroqTranscriber and replies {"type": "ready"}. Status shows "Listening".
  4. The AudioWorklet streams small PCM chunks to the server.
  5. When the speaker pauses, the server sends that phrase to Groq. While it
     waits, the browser shows "…"; when Groq answers, the server sends
     {"type": "final", "text": "<full transcript so far>"} and the text updates.
  6. The user clicks Stop. The browser sends {"type": "stop"}. The server
     transcribes the last piece of audio, saves the full text as a
     Transcription row and replies {"type": "saved", ...}.
  7. If the tab is closed mid-recording, whatever was transcribed is still
     saved. Sessions stop automatically after 10 minutes.


WebSocket messages:

  client -> server   {"type": "start", "language": "hinglish" | "en" | "hi"}
  client -> server   <binary 16 kHz PCM16 audio chunk>   (repeated)
  client -> server   {"type": "stop"}

  server -> client   {"type": "ready"}
  server -> client   {"type": "interim", "text": "…"}    (segment being processed)
  server -> client   {"type": "final", "text": "..."}    (full transcript so far)
  server -> client   {"type": "saved", "id": 1, "text": "..."}
  server -> client   {"type": "stopped"}                 (nothing was said)
  server -> client   {"type": "limit"}                   (10-minute cap reached)
  server -> client   {"type": "error", "message": "..."}


Language selection (dropdown on the Record page):

  Hinglish (default)  No language is forced; Whisper detects it for every
                      segment, so mixed Hindi-English sentences work. A short
                      mixed-script example is sent as Whisper's "prompt",
                      nudging it to write Hindi in Devanagari and English in
                      Latin script.
  English only        Sends language=en with an English prompt.
  Hindi only          Sends language=hi with a Hindi (Devanagari) prompt.

  The dropdown is locked while recording and applies to the whole session.

Other handling:

  - Whisper sometimes invents filler such as "Thank you." on near-silent
    audio; those known phrases are dropped.
  - If Groq is busy or rate-limited (HTTP 429/5xx), the request is retried
    once after 1.5 seconds.


3. DATABASE
-----------
Table: transcriber_transcription

  id          bigint, primary key
  text        text      the transcript
  created_at  timestamp set when the row is created
  updated_at  timestamp updated on every edit

Rows are listed newest first.


4. PAGES AND CRUD
-----------------
  /                          Record page: live transcription
  /history/                  History dashboard: list of all transcriptions
  /history/new/              Create a transcription manually
  /history/<id>/edit/        Update a transcription
  /history/<id>/delete/      Delete a transcription (with confirmation)

On the history page each row has:
  Listen  - reads the text aloud (Hindi voice for Devanagari text,
            Indian English voice otherwise); click again to stop
  Edit    - opens the edit form
  Delete  - asks for confirmation, then deletes


5. PROJECT FILES
----------------
manage.py                      Django command-line entry point
requirements.txt               Python dependencies
.env.example                   Template for environment variables
build.sh                       Render build: install, collect static, migrate
render.yaml                    Render deployment blueprint (web service + DB)

config/settings.py             Settings read from environment variables
config/asgi.py                 Routes HTTP to Django and WebSockets to Channels
config/urls.py                 Root URL configuration

transcriber/models.py          Transcription model
transcriber/forms.py           Form used for create and edit
transcriber/views.py           Record page and CRUD views
transcriber/urls.py            Page URLs
transcriber/routing.py         WebSocket URL
transcriber/consumers.py       WebSocket consumer: session start/stop,
                               relays text, saves to the database
transcriber/groq.py            Pause detection, segmenting, Groq Whisper calls
transcriber/migrations/        Database schema migrations

transcriber/templates/transcriber/
  base.html                    Layout and navigation
  live.html                    Record page
  list.html                    History dashboard
  form.html                    Create / edit form
  confirm_delete.html          Delete confirmation

transcriber/static/transcriber/
  pcm-worklet.js               Microphone audio -> 16 kHz PCM16 chunks
  live.js                      Record page logic and WebSocket client
  tts.js                       Text to speech for the Listen buttons
  app.css                      Styles


6. ENVIRONMENT VARIABLES
------------------------
  GROQ_API_KEY          required   Free key from https://console.groq.com
  DATABASE_URL          required   postgres://user:password@host:5432/dbname
  DJANGO_SECRET_KEY     required in production
  DJANGO_DEBUG          optional   true locally; false on Render
  DJANGO_ALLOWED_HOSTS  optional   default localhost,127.0.0.1
  GROQ_WHISPER_MODEL    optional   default whisper-large-v3-turbo
  MAX_SESSION_SECONDS   optional   default 600


7. RUN LOCALLY (Windows PowerShell)
-----------------------------------
  1. Create a PostgreSQL database named speech_to_text (for example in pgAdmin).

  2. In the project folder:
       python -m venv .venv
       .venv\Scripts\Activate.ps1
       pip install -r requirements.txt

  3. Copy .env.example to .env and fill in DATABASE_URL and GROQ_API_KEY.

  4. Create the tables and start the server:
       python manage.py migrate
       python manage.py runserver

  5. Open http://localhost:8000 in Chrome or Edge, click the red button,
     allow the microphone and speak. Click again to stop and save.

  The browser only allows microphone access on localhost or HTTPS.


8. DEPLOY ON RENDER
-------------------
  1. Push the project to a GitHub repository.
  2. In Render: New -> Blueprint -> select the repository.
     Render reads render.yaml and creates the web service and the
     PostgreSQL database, and connects them through DATABASE_URL.
  3. When asked for GROQ_API_KEY, paste your Groq key.
  4. After the deploy finishes, open https://<service-name>.onrender.com

  Free-tier notes:
  - The service sleeps after 15 minutes without traffic; the first request
    after that takes about a minute.
  - Free Render PostgreSQL databases expire after 30 days.
  - Groq's free tier allows 20 requests per minute; segments are at least
    2.5 seconds long to stay within it.
