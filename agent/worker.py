"""Audio-only LiveKit worker that writes final speech captions to Django."""

import asyncio
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
sys.path.insert(0, str(BASE_DIR))

import django  # noqa: E402

django.setup()

from asgiref.sync import sync_to_async  # noqa: E402
from livekit import agents, rtc  # noqa: E402
from livekit.agents import AgentServer  # noqa: E402
from livekit.agents.stt import SpeechEventType  # noqa: E402
from livekit.agents.vad import VADEventType  # noqa: E402
from livekit.plugins import deepgram, silero  # noqa: E402

from apps.meetings.models import Meeting, TranscriptLine  # noqa: E402
from apps.accounts.models import User  # noqa: E402

logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO'))
logger = logging.getLogger('meeting-listener')
server = AgentServer()
AGENT_NAME = 'meeting-listener'


def prewarm(proc: agents.JobProcess) -> None:
    proc.userdata['silero_vad'] = silero.VAD.load()


server.setup_fnc = prewarm


@sync_to_async
def find_meeting(room_name: str):
    return Meeting.objects.filter(livekit_room=room_name).first()


@sync_to_async
def save_transcript(room_name: str, speaker_identity: str, text: str) -> None:
    meeting = Meeting.objects.filter(livekit_room=room_name).first()
    if meeting is None:
        return
    speaker = User.objects.filter(username=speaker_identity).first()
    TranscriptLine.objects.create(meeting=meeting, speaker=speaker, text=text)


@sync_to_async
def generate_ended_meeting_report(room_name: str) -> None:
    meeting = Meeting.objects.filter(livekit_room=room_name).first()
    if meeting is None or meeting.status != Meeting.Status.ENDED or not meeting.transcript_lines.exists():
        return
    try:
        from apps.meetings.ai import generate_meeting_report
        from apps.meetings.views import _ensure_project_group

        report = generate_meeting_report(meeting)
        _ensure_project_group(meeting, report)
        logger.info('Finished the AI report for ended meeting %s.', meeting.pk)
    except Exception:
        logger.exception('Could not finish the AI report for ended meeting %s.', meeting.pk)


@server.rtc_session(agent_name=AGENT_NAME)
async def meeting_listener(ctx: agents.JobContext) -> None:
    if not os.getenv('DEEPGRAM_API_KEY', '').strip():
        logger.error('DEEPGRAM_API_KEY is missing; listener cannot transcribe.')
        return

    await ctx.connect()
    meeting = await find_meeting(ctx.room.name)
    if meeting is None:
        logger.error('No meeting record matches the connected room.')
        return

    vad = ctx.proc.userdata['silero_vad']
    tasks: dict[str, asyncio.Task] = {}

    async def transcribe_track(track: rtc.RemoteTrack, identity: str) -> None:
        vad_stream = vad.stream()
        stt = deepgram.STT(
            model=os.getenv('DEEPGRAM_MODEL', 'nova-3'),
            language=os.getenv('DEEPGRAM_LANGUAGE', 'multi'),
            interim_results=True,
        )
        stt_stream = stt.stream()
        audio_stream = rtc.AudioStream(track)
        speech_active = False

        async def send_speech_to_stt() -> None:
            nonlocal speech_active
            async for event in vad_stream:
                if event.type == VADEventType.START_OF_SPEECH:
                    speech_active = True
                    for frame in event.frames:
                        stt_stream.push_frame(frame)
                elif event.type == VADEventType.INFERENCE_DONE and speech_active:
                    for frame in event.frames:
                        stt_stream.push_frame(frame)
                elif event.type == VADEventType.END_OF_SPEECH:
                    speech_active = False
            stt_stream.end_input()

        async def save_final_transcripts() -> None:
            async for event in stt_stream:
                if event.type not in (SpeechEventType.INTERIM_TRANSCRIPT, SpeechEventType.FINAL_TRANSCRIPT) or not event.alternatives:
                    continue
                text = event.alternatives[0].text.strip()
                if not text:
                    continue
                is_final = event.type == SpeechEventType.FINAL_TRANSCRIPT
                if is_final:
                    await save_transcript(ctx.room.name, identity, text)

        try:
            async with asyncio.TaskGroup() as group:
                vad_task = group.create_task(send_speech_to_stt())
                group.create_task(save_final_transcripts())
                async for audio_event in audio_stream:
                    vad_stream.push_frame(audio_event.frame)
                vad_stream.end_input()
                await vad_task
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception('Audio transcription stream failed for a participant.')
        finally:
            await audio_stream.aclose()
            await vad_stream.aclose()
            await stt_stream.aclose()

    @ctx.room.on('track_subscribed')
    def on_track_subscribed(track: rtc.RemoteTrack, publication: rtc.RemoteTrackPublication, participant: rtc.RemoteParticipant):
        if track.kind != rtc.TrackKind.KIND_AUDIO:
            return
        if publication.source != rtc.TrackSource.SOURCE_MICROPHONE:
            return
        identity = participant.identity
        task = asyncio.create_task(transcribe_track(track, identity))
        tasks[track.sid] = task

    @ctx.room.on('track_unsubscribed')
    def on_track_unsubscribed(track: rtc.RemoteTrack, publication: rtc.RemoteTrackPublication, participant: rtc.RemoteParticipant):
        task = tasks.pop(track.sid, None)
        if task:
            task.cancel()

    logger.info('Meeting transcription listener connected.')
    shutdown_event = asyncio.Event()

    async def on_shutdown(reason: str) -> None:
        shutdown_event.set()

    ctx.add_shutdown_callback(on_shutdown)
    try:
        await shutdown_event.wait()
    finally:
        for task in tasks.values():
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks.values(), return_exceptions=True)
        await generate_ended_meeting_report(ctx.room.name)


if __name__ == '__main__':
    agents.cli.run_app(server)
