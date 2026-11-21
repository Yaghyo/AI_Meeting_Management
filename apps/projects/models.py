from django.conf import settings
from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator
from django.utils import timezone
import uuid


class Project(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    name = models.CharField(max_length=200, unique=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name


class ProjectGroup(models.Model):
    project = models.OneToOneField(Project, on_delete=models.CASCADE, related_name='group')
    members = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='project_groups', blank=True)
    project_manager = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='managed_project_groups')

    def __str__(self):
        return f'{self.project.name} group'


class GroupMessage(models.Model):
    group = models.ForeignKey(ProjectGroup, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    body = models.TextField(max_length=4000)
    read_by = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='read_group_messages', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']


class ProjectAIMessage(models.Model):
    class Role(models.TextChoices):
        USER = 'user', 'User'
        ASSISTANT = 'assistant', 'Assistant'

    group = models.ForeignKey(ProjectGroup, on_delete=models.CASCADE, related_name='ai_messages')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='project_ai_messages')
    role = models.CharField(max_length=10, choices=Role.choices)
    body = models.TextField(max_length=8000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']


class DailyUpdate(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='daily_updates')
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='daily_updates')
    report_date = models.DateField(default=timezone.localdate)
    working_on = models.TextField(max_length=2000, blank=True)
    completed_today = models.TextField(max_length=5000, blank=True)
    remaining_work = models.TextField(max_length=5000, blank=True)
    blockers = models.TextField(max_length=3000, blank=True)
    no_work_today = models.BooleanField(default=False)
    hours_worked = models.DecimalField(
        max_digits=4, decimal_places=1, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(24)],
    )
    submitted_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-report_date', '-submitted_at']
        constraints = [
            models.UniqueConstraint(
                fields=('user', 'project', 'report_date'),
                name='unique_daily_update_user_project_date',
            ),
        ]

    def __str__(self):
        return f'{self.user} · {self.project} · {self.report_date}'


class ProjectKnowledgeChunk(models.Model):
    class SourceType(models.TextChoices):
        MEETING_SUMMARY = 'meeting_summary', 'Meeting summary'
        TRANSCRIPT = 'transcript', 'Transcript'
        GROUP_MESSAGE = 'group_message', 'Project chat'
        ACTION_ITEM = 'action_item', 'Action item'

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='knowledge_chunks')
    source_type = models.CharField(max_length=24, choices=SourceType.choices)
    source_key = models.CharField(max_length=180)
    source_label = models.CharField(max_length=320)
    content = models.TextField()
    content_hash = models.CharField(max_length=64)
    embedding = models.JSONField(null=True, blank=True)
    embedding_model = models.CharField(max_length=100, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('project', 'source_key'),
                name='unique_project_knowledge_source_chunk',
            ),
        ]
        indexes = [
            models.Index(fields=('project', 'source_type'), name='project_knowledge_type_idx'),
        ]

    def __str__(self):
        return self.source_label


class DirectMessage(models.Model):
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_direct_messages')
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='received_direct_messages')
    body = models.TextField(max_length=4000)
    read_by = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='read_direct_messages', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']
