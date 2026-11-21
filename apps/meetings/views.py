import datetime
import logging
import os

from asgiref.sync import async_to_sync
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from .forms import MeetingForm
from .models import Meeting, MeetingAIReport, TranscriptLine
from apps.projects.models import Project, ProjectGroup

logger = logging.getLogger(__name__)


def _can_access_meeting(user, meeting):
    if user.is_staff or user.role == 'admin':
        return True
    if meeting.project_id:
        group = ProjectGroup.objects.filter(project_id=meeting.project_id).first()
        if group:
            return group.members.filter(pk=user.pk).exists()
    return meeting.created_by_id == user.id or meeting.participants.filter(pk=user.pk).exists()


def _ensure_project_group(meeting, report=None):
    with transaction.atomic():
        meeting = Meeting.objects.select_for_update().get(pk=meeting.pk)
        project = meeting.project
        if project is None:
            base_name = ((report.project_name if report else '') or f'{meeting.title[:170]} project').strip()[:200]
            base_name = base_name or f'Meeting {meeting.pk} project'
            name, suffix = base_name, 2
            while Project.objects.filter(name=name).exists():
                ending = f' ({suffix})'
                name = f'{base_name[:200 - len(ending)]}{ending}'
                suffix += 1
            description = (report.project_description if report else '') or (report.summary if report else '')
            project = Project.objects.create(name=name, description=description or f'Project created from meeting: {meeting.title}')
            meeting.project = project
            meeting.save(update_fields=['project'])
        elif report:
            if project.description.startswith('Project created from meeting:'):
                candidate = (report.project_name or project.name).strip()[:200] or project.name
                name, suffix = candidate, 2
                while Project.objects.filter(name=name).exclude(pk=project.pk).exists():
                    ending = f' ({suffix})'
                    name = f'{candidate[:200 - len(ending)]}{ending}'
                    suffix += 1
                project.name = name
                project.description = report.project_description or report.summary
                project.save(update_fields=['name', 'description'])
            elif not project.description and report.project_description:
                project.description = report.project_description
                project.save(update_fields=['description'])
        group, _ = ProjectGroup.objects.get_or_create(project=project)
        group.members.add(*meeting.participants.all())
    return group


def _generate_report_when_ending(meeting):
    try:
        from .ai import generate_meeting_report
        report = generate_meeting_report(meeting)
        _ensure_project_group(meeting, report)
        return report, None
    except Exception as error:
        logger.exception('Groq could not generate report for meeting %s', meeting.pk)
        _ensure_project_group(meeting)
        return None, error


def _expire_meeting_if_due(meeting, now=None):
    """End a meeting whose optional deadline has passed, even if no one joined."""
    now = now or timezone.now()
    became_ended = False
    was_live = False
    with transaction.atomic():
        meeting = Meeting.objects.select_for_update().get(pk=meeting.pk)
        if (meeting.status in (Meeting.Status.SCHEDULED, Meeting.Status.LIVE)
                and meeting.ends_at and meeting.ends_at <= now):
            was_live = meeting.status == Meeting.Status.LIVE
            meeting.status = Meeting.Status.ENDED
            meeting.ended_at = now
            meeting.save(update_fields=['status', 'ended_at'])
            became_ended = True

    if became_ended:
        if was_live:
            try:
                _delete_livekit_room(meeting)
            except Exception:
                logger.exception('Could not close expired LiveKit room for meeting %s', meeting.pk)
        if meeting.transcript_lines.exists():
            _generate_report_when_ending(meeting)
    return meeting


def _delete_livekit_room(meeting):
    livekit_url = os.environ.get('LIVEKIT_URL', '').strip()
    api_key = os.environ.get('LIVEKIT_API_KEY', '').strip()
    api_secret = os.environ.get('LIVEKIT_API_SECRET', '').strip()
    if not (livekit_url and api_key and api_secret):
        raise RuntimeError('LiveKit is not configured.')
    from livekit import api
    from livekit.api.twirp_client import ServerError

    async def delete_room():
        client = api.LiveKitAPI(
            livekit_url.replace('wss://', 'https://', 1).replace('ws://', 'http://', 1),
            api_key,
            api_secret,
        )
        try:
            await client.room.delete_room(api.DeleteRoomRequest(room=meeting.livekit_room))
        finally:
            await client.aclose()

    try:
        async_to_sync(delete_room)()
    except ServerError as error:
        if error.status != 404:
            raise


@login_required
def dashboard(request):
    for due_meeting in Meeting.objects.filter(
        status__in=(Meeting.Status.SCHEDULED, Meeting.Status.LIVE),
        ends_at__lte=timezone.now(),
    ).only('pk'):
        _expire_meeting_if_due(due_meeting)
    meetings = Meeting.objects.filter(status__in=(Meeting.Status.SCHEDULED, Meeting.Status.LIVE)).select_related('created_by').prefetch_related('participants')
    return render(request, 'meetings/dashboard.html', {
        'meetings': meetings.distinct(),
    })


@login_required
def meetings_page(request):
    for due_meeting in Meeting.objects.filter(
        status__in=(Meeting.Status.SCHEDULED, Meeting.Status.LIVE),
        ends_at__lte=timezone.now(),
    ).only('pk'):
        _expire_meeting_if_due(due_meeting)
    meetings = Meeting.objects.select_related('created_by').prefetch_related('participants').all()
    return render(request, 'meetings/meetings_page.html', {'meetings': meetings.distinct()})


@login_required
def meeting_detail(request, pk):
    meeting = get_object_or_404(Meeting.objects.select_related('created_by', 'project').prefetch_related('participants'), pk=pk)
    meeting = _expire_meeting_if_due(meeting)
    can_view_report = _can_access_meeting(request.user, meeting)
    return render(request, 'meetings/meeting_detail.html', {
        'meeting': meeting, 'can_view_report': can_view_report,
        'report': getattr(meeting, 'ai_report', None) if can_view_report else None,
    })


@login_required
def meeting_create(request):
    form = MeetingForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        meeting = form.save(commit=False)
        meeting.created_by = request.user
        meeting.save()
        meeting.participants.set([*form.cleaned_data['participants'], request.user])
        messages.success(request, f'Meeting “{meeting.title}” was created.')
        return redirect('dashboard')
    return render(request, 'meetings/meeting_form.html', {'form': form, 'title': 'Schedule a meeting'})


@login_required
def meeting_edit(request, pk):
    meeting = get_object_or_404(Meeting, pk=pk)
    if meeting.created_by != request.user and not (request.user.is_staff or request.user.role == 'admin'):
        return redirect('dashboard')
    form = MeetingForm(request.POST or None, instance=meeting)
    if request.method == 'POST' and form.is_valid():
        meeting = form.save()
        meeting.participants.set([*form.cleaned_data['participants'], meeting.created_by])
        messages.success(request, f'Meeting “{meeting.title}” was updated.')
        return redirect('dashboard')
    return render(request, 'meetings/meeting_form.html', {'form': form, 'title': 'Edit meeting'})


@login_required
def meeting_delete(request, pk):
    meeting = get_object_or_404(Meeting, pk=pk)
    if request.method == 'POST' and (meeting.created_by == request.user or request.user.is_staff or request.user.role == 'admin'):
        meeting.delete()
        messages.success(request, 'Meeting deleted.')
    return redirect('dashboard')


@login_required
def meeting_room(request, pk):
    meeting = get_object_or_404(Meeting, pk=pk)
    meeting = _expire_meeting_if_due(meeting)
    if meeting.status == Meeting.Status.ENDED:
        messages.info(request, 'This meeting has ended.')
        return redirect('dashboard')
    invite_url = request.build_absolute_uri(reverse('meeting_invite', args=[meeting.pk, meeting.invite_token]))
    return render(request, 'meetings/room.html', {
        'meeting': meeting,
        'invite_url': invite_url,
        'transcription_configured': bool(os.environ.get('DEEPGRAM_API_KEY', '').strip()),
        'can_end_meeting': meeting.created_by_id == request.user.id or request.user.is_staff or request.user.role == 'admin',
    })


@login_required
def meeting_invite(request, pk, invite_token):
    meeting = get_object_or_404(Meeting, pk=pk, invite_token=invite_token)
    meeting = _expire_meeting_if_due(meeting)
    if meeting.status == Meeting.Status.ENDED:
        messages.info(request, 'This meeting has ended.')
        return redirect('dashboard')
    meeting.participants.add(request.user)
    return redirect('meeting_room', pk=meeting.pk)


@login_required
@require_POST
def meeting_token(request, pk):
    meeting = get_object_or_404(Meeting, pk=pk)
    meeting = _expire_meeting_if_due(meeting)
    if meeting.status not in (Meeting.Status.SCHEDULED, Meeting.Status.LIVE):
        return JsonResponse({'error': 'This meeting is not open for joining.'}, status=410)
    meeting.participants.add(request.user)

    livekit_url = os.environ.get('LIVEKIT_URL', '').strip()
    api_key = os.environ.get('LIVEKIT_API_KEY', '').strip()
    api_secret = os.environ.get('LIVEKIT_API_SECRET', '').strip()
    if not (livekit_url and api_key and api_secret):
        return JsonResponse(
            {'error': 'LiveKit is not configured. Add LIVEKIT_URL, LIVEKIT_API_KEY, and LIVEKIT_API_SECRET to your environment, then restart Django.'},
            status=503,
        )

    try:
        from livekit import api
    except ImportError:
        return JsonResponse({'error': 'LiveKit server SDK is missing. Install dependencies with: pip install -r requirements.txt'}, status=503)

    display_name = request.user.get_full_name() or request.user.username

    token_builder = (
        api.AccessToken(api_key, api_secret)
        .with_identity(request.user.username)
        .with_name(display_name)
        .with_grants(api.VideoGrants(
            room_join=True,
            room=meeting.livekit_room,
            can_publish=True,
            can_subscribe=True,
            can_publish_data=True,
        ))
        .with_ttl(datetime.timedelta(minutes=15))
    )
    transcription_configured = bool(os.environ.get('DEEPGRAM_API_KEY', '').strip())
    token = token_builder.to_jwt()

    # Token room configuration is applied only when LiveKit creates a room.
    # Explicit dispatch also covers rooms that already existed before the worker started.
    listener_dispatched = False
    if transcription_configured:
        async def dispatch_listener():
            client = api.LiveKitAPI(
                livekit_url.replace('wss://', 'https://', 1).replace('ws://', 'http://', 1),
                api_key,
                api_secret,
            )
            try:
                rooms = await client.room.list_rooms(api.ListRoomsRequest(names=[meeting.livekit_room]))
                room_exists = bool(rooms.rooms)
                if room_exists:
                    participants = await client.room.list_participants(
                        api.ListParticipantsRequest(room=meeting.livekit_room)
                    )
                    if any(participant.identity.startswith('agent-') for participant in participants.participants):
                        return
                    dispatches = await client.agent_dispatch.list_dispatch(meeting.livekit_room)
                else:
                    dispatches = []
                listener_dispatches = [dispatch for dispatch in dispatches if dispatch.agent_name == 'meeting-listener']
                from livekit.protocol.agent import JobStatus

                for dispatch in listener_dispatches:
                    has_pending_job = any(
                        job.state.status in (JobStatus.JS_PENDING, JobStatus.JS_RUNNING)
                        for job in dispatch.state.jobs
                    )
                    recently_requested = timezone.now().timestamp() - dispatch.state.created_at < 30
                    if has_pending_job or recently_requested:
                        return
                    await client.agent_dispatch.delete_dispatch(dispatch.id, meeting.livekit_room)

                await client.agent_dispatch.create_dispatch(api.CreateAgentDispatchRequest(
                    agent_name='meeting-listener',
                    room=meeting.livekit_room,
                    metadata=f'{{"meeting_id": {meeting.pk}}}',
                ))
            finally:
                await client.aclose()

        try:
            async_to_sync(dispatch_listener)()
            listener_dispatched = True
        except Exception:
            # Keep the video meeting usable if the transcription worker is offline.
            listener_dispatched = False

    if meeting.status == Meeting.Status.SCHEDULED:
        meeting.status = Meeting.Status.LIVE
        meeting.started_at = timezone.now()
        meeting.save(update_fields=['status', 'started_at'])

    return JsonResponse({
        'url': livekit_url,
        'token': token,
        'participant': display_name,
        'transcription_configured': transcription_configured,
        'listener_dispatched': listener_dispatched,
    })


@login_required
def meeting_transcript(request, pk):
    meeting = get_object_or_404(Meeting, pk=pk)
    try:
        after_id = max(0, int(request.GET.get('after', 0)))
    except (TypeError, ValueError):
        after_id = 0

    lines = meeting.transcript_lines.filter(id__gt=after_id).select_related('speaker')[:100]
    return JsonResponse({'lines': [
        {
            'id': line.id,
            'speaker': (line.speaker.get_full_name() or line.speaker.username) if line.speaker else 'Unknown speaker',
            'text': line.text,
            'spoken_at': line.spoken_at.isoformat(),
        }
        for line in lines
    ]})


@login_required
@require_POST
def meeting_end(request, pk):
    meeting = get_object_or_404(Meeting, pk=pk)
    if meeting.created_by_id != request.user.id and not (request.user.is_staff or request.user.role == 'admin'):
        return JsonResponse({'error': 'Only the organizer can stop this meeting.'}, status=403)
    livekit_url = os.environ.get('LIVEKIT_URL', '').strip()
    api_key = os.environ.get('LIVEKIT_API_KEY', '').strip()
    api_secret = os.environ.get('LIVEKIT_API_SECRET', '').strip()
    if meeting.status == Meeting.Status.LIVE:
        if not (livekit_url and api_key and api_secret):
            return JsonResponse({'error': 'LiveKit is not configured on the server.'}, status=503)
        try:
            _delete_livekit_room(meeting)
        except Exception:
            return JsonResponse({'error': 'LiveKit could not stop the room. Check the LiveKit connection and try again.'}, status=502)

    if meeting.status != Meeting.Status.ENDED:
        meeting.status = Meeting.Status.ENDED
        meeting.ended_at = timezone.now()
        meeting.save(update_fields=['status', 'ended_at'])
    report, report_error = _generate_report_when_ending(meeting)
    return JsonResponse({
        'ended': True,
        'report_generated': report is not None,
        'report_pending': report_error is not None,
    })

@login_required
def meeting_ai_report(request, pk):
    meeting = get_object_or_404(Meeting.objects.select_related('created_by', 'project'), pk=pk)
    if not _can_access_meeting(request.user, meeting):
        return redirect('dashboard')
    if request.method == 'POST':
        return redirect('meeting_ai_report', pk=pk)
    report = getattr(meeting, 'ai_report', None)
    return render(request, 'meetings/ai_report.html', {
        'meeting': meeting,
        'report': report,
        'action_items': meeting.action_items.select_related('assigned_to').all(),
        'has_transcript': meeting.transcript_lines.exists(),
        'report_pending': meeting.status == Meeting.Status.ENDED and report is None and meeting.transcript_lines.exists(),
    })
