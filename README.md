# Meeting AI

Phase 1 foundation for the meeting assistant. The app currently provides employee registration/login, a custom username-based user, employee profiles, meeting scheduling, and a private meeting dashboard. Development uses SQLite and the Asia/Kolkata timezone.

## Run locally (Windows PowerShell)

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py makemigrations accounts meetings
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open http://127.0.0.1:8000/. Register an employee account, or sign in with the superuser. Django admin is at `/admin/`.

## Connect LiveKit

1. Create a LiveKit Cloud project or configure a reachable self-hosted LiveKit server.
2. Copy `.env.example` to `.env` and fill in `LIVEKIT_URL`, `LIVEKIT_API_KEY`, and `LIVEKIT_API_SECRET` from the LiveKit project/server settings. Keep `.env` private; it is git-ignored.
3. Add a Deepgram API key to `.env` as `DEEPGRAM_API_KEY`. Deepgram provides the real-time speech recognition; Silero runs locally for speech detection.
4. Install the agent dependencies and start the separate worker in a second PowerShell window:

   ```powershell
   .\meeting\Scripts\python.exe -m pip install -r requirements.txt
   .\meeting\Scripts\python.exe agent\worker.py dev
   ```

5. Keep the worker running, restart Django, schedule a meeting, and join it. Everyone who joins can see the saved live captions in the meeting. Captions are stored as text; meeting audio/video are not recorded or saved.

The Django server issues a short-lived token scoped to that meeting and the signed-in username. The browser connects to LiveKit for live audio/video. This app does not record or store meeting media. The browser loads the pinned LiveKit client SDK from jsDelivr, so users need internet access to that CDN as well as a connection to the LiveKit server.

The built-in database is for local development. Do not deploy with the development secret key or `DEBUG=True`. Set `DEEPGRAM_MODEL` or `DEEPGRAM_LANGUAGE` in `.env` if you want to change the default transcription model or language mode. The AI listener worker must be running when a room is first opened so LiveKit can dispatch it.

## Test camera and microphone from another device

Browsers require HTTPS for camera and microphone access on a phone or another computer. `localhost` on that second device points to that device, and a plain `http://<LAN-IP>:8000` page is not a secure context. Use a temporary HTTPS tunnel for local testing:

1. Install `cloudflared` for Windows from the [Cloudflare downloads page](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/downloads/).
2. Start Django in one PowerShell window: `python manage.py runserver 127.0.0.1:8000`.
3. In a second window, run `cloudflared tunnel --url http://127.0.0.1:8000`. Copy the temporary `https://...trycloudflare.com` URL it prints.
4. Add that exact host to `.env`: set `DJANGO_DEBUG=False`, add the host (without `https://`) to `DJANGO_ALLOWED_HOSTS`, set `DJANGO_CSRF_TRUSTED_ORIGINS` to the full `https://...` origin, and set `DJANGO_TRUST_PROXY_SSL=True`.
5. Restart Django, open the HTTPS URL on both devices, sign in, open the meeting, and allow camera/microphone access.

The tunnel URL is temporary and anyone who has it can reach your local app while the tunnel runs. Stop the tunnel when finished. Restore `DJANGO_DEBUG=True`, local-only `DJANGO_ALLOWED_HOSTS`, an empty `DJANGO_CSRF_TRUSTED_ORIGINS`, and `DJANGO_TRUST_PROXY_SSL=False` for normal local development.
