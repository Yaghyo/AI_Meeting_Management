import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone
from apps.projects.models import Project


class Meeting(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = 'scheduled', 'Scheduled'
        LIVE = 'live', 'Live'
        ENDED = 'ended', 'Ended'
        PROCESSING = 'processing', 'Processing'

    title = models.CharField(max_length=200)
    scheduled_at = models.DateTimeField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SCHEDULED)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='created_meetings')
    livekit_room = models.CharField(max_length=100, unique=True, default=uuid.uuid4)
    invite_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    started_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, blank=True, related_name='meetings')
    participants = models.ManyToManyField(settings.AUTH_USER_MODEL, through='MeetingParticipant', related_name='invited_meetings')

    class Meta:
        ordering = ['scheduled_at']

    def __str__(self):
        return self.title


class MeetingParticipant(models.Model):
    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name='participant_records')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    joined_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=('meeting', 'user'), name='unique_meeting_participant')]


class TranscriptLine(models.Model):
    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name='transcript_lines')
    speaker = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    text = models.TextField()
    spoken_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f'{self.meeting}: {self.text[:60]}'


class MeetingAIReport(models.Model):
    meeting = models.OneToOneField(Meeting, on_delete=models.CASCADE, related_name='ai_report')
    summary = models.TextField()
    key_points = models.JSONField(default=list, blank=True)
    decisions = models.JSONField(default=list, blank=True)
    project_updates = models.JSONField(default=list, blank=True)
    project_name = models.CharField(max_length=200, blank=True)
    project_description = models.TextField(blank=True)
    transcript_line_count = models.PositiveIntegerField(default=0)
    model = models.CharField(max_length=100)
    generated_at = models.DateTimeField(default=timezone.now)


class ActionItem(models.Model):
    class Priority(models.TextChoices):
        LOW = 'low', 'Low'
        MEDIUM = 'medium', 'Medium'
        HIGH = 'high', 'High'

    class Status(models.TextChoices):
        OPEN = 'open', 'Open'
        IN_PROGRESS = 'in_progress', 'In progress'
        DONE = 'done', 'Done'

    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name='action_items')
    title = models.CharField(max_length=240)
    description = models.TextField(blank=True)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='meeting_action_items')
    suggested_assignee = models.CharField(max_length=150, blank=True)
    due_date = models.DateField(null=True, blank=True)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIUM)
    evidence = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)

# Create your models here.
