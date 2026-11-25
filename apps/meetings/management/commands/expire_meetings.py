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
        parser.add_argument(
            '--once', action='store_true',
            help='End due meetings once and exit, for use with a scheduled job.',
        )

    def handle(self, *args, **options):
        interval = options['interval']
        if interval < 1:
            raise CommandError('--interval must be at least 1 second.')

        if options['once']:
            self._expire_due_meetings()
            return

        self.stdout.write(self.style.SUCCESS(
            f'Checking meeting end times every {interval} seconds. Press Ctrl+C to stop.'
        ))
        try:
            while True:
                self._expire_due_meetings()
                time.sleep(interval)
        except KeyboardInterrupt:
            self.stdout.write('\nMeeting deadline checker stopped.')

    def _expire_due_meetings(self):
        due_meetings = Meeting.objects.filter(
            status__in=(Meeting.Status.SCHEDULED, Meeting.Status.LIVE),
            ends_at__lte=timezone.now(),
        ).only('pk')
        for meeting in due_meetings.iterator():
            self.stdout.write(f'Ending expired meeting {meeting.pk}.')
            _expire_meeting_if_due(meeting)
