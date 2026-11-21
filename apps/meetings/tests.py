from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from datetime import datetime, timedelta
from unittest.mock import patch
import os

from apps.accounts.models import User
from .models import Meeting


class MeetingCreateFlowTests(TestCase):
    def setUp(self):
        self.organizer = User.objects.create_user(
            username='organizer', email='organizer@example.com', password='test-pass-123',
        )
        self.invitee = User.objects.create_user(
            username='invitee', email='invitee@example.com', password='test-pass-123',
        )
        self.client.force_login(self.organizer)

    def test_create_meeting_saves_and_returns_to_dashboard(self):
        response = self.client.post(reverse('meeting_create'), {
            'title': 'Planning meeting',
            'scheduled_at': '2026-12-01T10:30',
            'participants': [str(self.invitee.pk)],
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('dashboard'))
        meeting = Meeting.objects.get(title='Planning meeting')
        self.assertEqual(meeting.created_by, self.organizer)
        self.assertEqual(meeting.status, Meeting.Status.SCHEDULED)
        self.assertQuerySetEqual(
            meeting.participants.order_by('username'),
            [self.invitee, self.organizer],
        )

        dashboard = self.client.get(reverse('dashboard'))
        self.assertContains(dashboard, 'Planning meeting')
        self.assertContains(dashboard, 'Meeting “Planning meeting” was created.')

    def test_create_meeting_without_invitees_adds_organizer(self):
        response = self.client.post(reverse('meeting_create'), {
            'title': 'One-to-one',
            'scheduled_at': '2026-12-02T09:00',
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('dashboard'))
        meeting = Meeting.objects.get(title='One-to-one')
        self.assertEqual(list(meeting.participants.all()), [self.organizer])

    def test_missing_title_does_not_create_meeting(self):
        response = self.client.post(reverse('meeting_create'), {
            'title': '',
            'scheduled_at': '2026-12-01T10:30',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'This field is required.')
        self.assertEqual(Meeting.objects.count(), 0)

    def test_end_time_is_optional_and_must_follow_start(self):
        response = self.client.post(reverse('meeting_create'), {
            'title': 'No end time yet',
            'scheduled_at': '2026-12-01T10:30',
        })
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(Meeting.objects.get(title='No end time yet').ends_at)

        response = self.client.post(reverse('meeting_create'), {
            'title': 'Invalid end time',
            'scheduled_at': '2026-12-01T10:30',
            'ends_at': '2026-12-01T10:00',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'End time must be after the meeting start time.')
        self.assertFalse(Meeting.objects.filter(title='Invalid end time').exists())

    def test_all_signed_in_users_can_see_scheduled_meetings(self):
        meeting = Meeting.objects.create(
            title='Company planning',
            scheduled_at=timezone.make_aware(datetime(2026, 12, 1, 10, 30)),
            created_by=self.organizer,
        )
        self.client.force_login(self.invitee)

        response = self.client.get(reverse('dashboard'))

        self.assertContains(response, 'Company planning')
        self.assertContains(response, reverse('meeting_room', args=[meeting.pk]))
        self.assertNotContains(response, 'Copy invite link')

        room = self.client.get(reverse('meeting_room', args=[meeting.pk]))
        self.assertEqual(room.status_code, 200)
        self.assertContains(room, 'Copy invite link')

    def test_any_signed_in_user_can_request_a_room_token(self):
        meeting = Meeting.objects.create(
            title='Open company meeting',
            scheduled_at=timezone.make_aware(datetime(2026, 12, 1, 10, 30)),
            created_by=self.organizer,
        )
        self.client.force_login(self.invitee)

        with patch.dict(os.environ, {
            'LIVEKIT_URL': 'wss://example.livekit.cloud',
            'LIVEKIT_API_KEY': 'test-key',
            'LIVEKIT_API_SECRET': 'test-secret-that-is-long-enough-for-signing',
        }):
            response = self.client.post(reverse('meeting_token', args=[meeting.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['token'])

    def test_invite_link_adds_signed_in_user_as_participant(self):
        meeting = Meeting.objects.create(
            title='Shared invite',
            scheduled_at=timezone.make_aware(datetime(2026, 12, 1, 10, 30)),
            created_by=self.organizer,
        )
        self.client.force_login(self.invitee)

        response = self.client.get(reverse('meeting_invite', args=[meeting.pk, meeting.invite_token]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('meeting_room', args=[meeting.pk]))
        self.assertTrue(meeting.participants.filter(pk=self.invitee.pk).exists())

    def test_organizer_can_stop_a_scheduled_meeting(self):
        meeting = Meeting.objects.create(
            title='Stop before joining',
            scheduled_at=timezone.make_aware(datetime(2026, 12, 1, 10, 30)),
            created_by=self.organizer,
        )

        response = self.client.post(reverse('meeting_end', args=[meeting.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ended'])
        meeting.refresh_from_db()
        self.assertEqual(meeting.status, Meeting.Status.ENDED)

    def test_meeting_past_end_time_is_ended_and_cannot_be_joined(self):
        meeting = Meeting.objects.create(
            title='Expired before anyone joined',
            scheduled_at=timezone.now() - timedelta(hours=1),
            ends_at=timezone.now() - timedelta(minutes=1),
            created_by=self.organizer,
        )

        response = self.client.post(reverse('meeting_token', args=[meeting.pk]))

        self.assertEqual(response.status_code, 410)
        meeting.refresh_from_db()
        self.assertEqual(meeting.status, Meeting.Status.ENDED)
        self.assertIsNotNone(meeting.ended_at)

        dashboard = self.client.get(reverse('dashboard'))
        self.assertNotContains(dashboard, 'Expired before anyone joined')
        self.assertNotContains(dashboard, reverse('meeting_room', args=[meeting.pk]))

    def test_meeting_room_redirects_after_end_time(self):
        meeting = Meeting.objects.create(
            title='Expired room',
            scheduled_at=timezone.now() - timedelta(hours=1),
            ends_at=timezone.now() - timedelta(seconds=1),
            created_by=self.organizer,
        )

        response = self.client.get(reverse('meeting_room', args=[meeting.pk]))

        self.assertRedirects(response, reverse('dashboard'))
        meeting.refresh_from_db()
        self.assertEqual(meeting.status, Meeting.Status.ENDED)

    @patch('apps.meetings.views._delete_livekit_room')
    def test_live_meeting_is_closed_when_its_end_time_passes(self, close_livekit_room):
        meeting = Meeting.objects.create(
            title='Live meeting past deadline',
            scheduled_at=timezone.now() - timedelta(hours=1),
            ends_at=timezone.now() - timedelta(seconds=1),
            status=Meeting.Status.LIVE,
            created_by=self.organizer,
        )

        response = self.client.get(reverse('meeting_room', args=[meeting.pk]))

        self.assertRedirects(response, reverse('dashboard'))
        close_livekit_room.assert_called_once()
        meeting.refresh_from_db()
        self.assertEqual(meeting.status, Meeting.Status.ENDED)

    def test_non_organizer_cannot_stop_a_meeting(self):
        meeting = Meeting.objects.create(
            title='Host controlled',
            scheduled_at=timezone.make_aware(datetime(2026, 12, 1, 10, 30)),
            created_by=self.organizer,
        )
        self.client.force_login(self.invitee)

        response = self.client.post(reverse('meeting_end', args=[meeting.pk]))

        self.assertEqual(response.status_code, 403)
        meeting.refresh_from_db()
        self.assertEqual(meeting.status, Meeting.Status.SCHEDULED)
