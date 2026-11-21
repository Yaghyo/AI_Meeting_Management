"""Run a synthetic meeting through the Groq report workflow without keeping test data."""

import json
import os
import sys
import uuid
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.meetings.models import Meeting, TranscriptLine
from apps.meetings.views import _generate_report_when_ending
from apps.projects.models import ProjectGroup


TRANSCRIPT = [
    ('morgan', 'Morgan', 'Lee', "Let's plan the Atlas launch. The customer dashboard needs a final prototype. Priya, can you own that? We need it by November 25, 2026."),
    ('priya', 'Priya', 'Shah', "Yes, I'll deliver the dashboard prototype by November 25."),
    ('alex', 'Alex', 'Kim', "I can run regression tests once the prototype is ready. I'll send the results by November 27."),
    ('morgan', 'Morgan', 'Lee', "I'll confirm the production API response schema with the backend team by November 23."),
    ('morgan', 'Morgan', 'Lee', "Decision: we will use the existing PostgreSQL database and release after Alex's tests pass."),
]


class RollBackDemo(Exception):
    pass


try:
    with transaction.atomic():
        suffix = uuid.uuid4().hex[:8]
        users = {}
        for username, first_name, last_name in dict.fromkeys((row[0], row[1], row[2]) for row in TRANSCRIPT):
            user = User(
                username=f'demo_{username}_{suffix}',
                email=f'demo_{username}_{suffix}@example.invalid',
                first_name=first_name,
                last_name=last_name,
            )
            user.set_unusable_password()
            user.save()
            users[username] = user

        meeting = Meeting.objects.create(
            title='Atlas launch planning (synthetic demo)',
            scheduled_at=timezone.now(),
            status=Meeting.Status.ENDED,
            created_by=users['morgan'],
        )
        meeting.participants.add(*users.values())
        for username, _first, _last, text in TRANSCRIPT:
            TranscriptLine.objects.create(meeting=meeting, speaker=users[username], text=text)

        report, error = _generate_report_when_ending(meeting)
        if error or report is None:
            raise RuntimeError(f'Groq report failed: {type(error).__name__ if error else "no report returned"}')

        fresh_meeting = Meeting.objects.get(pk=meeting.pk)
        project_group = ProjectGroup.objects.get(project=fresh_meeting.project)
        output = {
            'model': report.model,
            'summary': report.summary,
            'key_points': report.key_points,
            'decisions': report.decisions,
            'project_name': fresh_meeting.project.name,
            'project_description': fresh_meeting.project.description,
            'action_items': [
                {
                    'title': item.title,
                    'description': item.description,
                    'assigned_to': item.assigned_to.get_full_name() if item.assigned_to else None,
                    'due_date': item.due_date.isoformat() if item.due_date else None,
                    'priority': item.priority,
                    'evidence': item.evidence,
                }
                for item in meeting.action_items.select_related('assigned_to')
            ],
            'project_group_created': project_group.members.count() == len(users),
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
        raise RollBackDemo()
except RollBackDemo:
    print('\nDemo database records rolled back; only the Groq response above was kept in the console.')
