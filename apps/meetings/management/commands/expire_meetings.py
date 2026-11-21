import time

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.meetings.models import Meeting
from apps.meetings.views import _expire_meeting_if_due


class Command(BaseCommand):
    help = 'Automatically end meetings after their configured end time.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--interval', type=int, default=15,
            help='Seconds between deadline checks (default: 15).',
        )

    def handle(self, *args, **options):
        interval = options['interval']
        if interval < 1:
            raise CommandError('--interval must be at least 1 second.')

        self.stdout.write(self.style.SUCCESS(
            f'Checking meeting end times every {interval} seconds. Press Ctrl+C to stop.'
        ))
        try:
            while True:
                due_meetings = Meeting.objects.filter(
                    status__in=(Meeting.Status.SCHEDULED, Meeting.Status.LIVE),
                    ends_at__lte=timezone.now(),
                ).only('pk')
                for meeting in due_meetings.iterator():
                    self.stdout.write(f'Ending expired meeting {meeting.pk}.')
                    _expire_meeting_if_due(meeting)
                time.sleep(interval)
        except KeyboardInterrupt:
            self.stdout.write('\nMeeting deadline checker stopped.')
