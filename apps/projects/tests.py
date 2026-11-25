from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import EmployeeProfile, User
from apps.meetings.models import ActionItem, Meeting, TranscriptLine
from .models import CompanyAIMessage, DailyUpdate, GroupMessage, Project, ProjectAIMessage, ProjectGroup


class ProjectAssistantRetrievalTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='project_user', email='project_user@example.com', password='test-pass-123',
        )
        self.project = Project.objects.create(
            name='Aurora release', description='Release planning for the Aurora dashboard.',
        )
        self.group = ProjectGroup.objects.create(project=self.project, project_manager=self.user)
        self.group.members.add(self.user)
        EmployeeProfile.objects.create(
            user=self.user,
            designation='Operations analyst',
            department='Operations',
            age=38,
            experience='Experienced in reducing project delivery delays.',
            skills=['planning', 'analytics'],
            resume_text='Led delivery planning and operational reporting.',
        )
        self.meeting = Meeting.objects.create(
            title='Aurora release planning', scheduled_at='2026-11-20T10:00:00Z',
            created_by=self.user, project=self.project,
        )
        self.line = TranscriptLine.objects.create(
            meeting=self.meeting,
            speaker=self.user,
            text='Priya will complete Aurora dashboard regression testing before launch.',
        )
        self.task = ActionItem.objects.create(
            meeting=self.meeting,
            title='Complete dashboard regression testing',
            description='Run the release regression suite.',
            assigned_to=self.user,
            evidence='I will complete regression testing before launch.',
        )
        GroupMessage.objects.create(
            group=self.group, sender=self.user, body='Regression testing is the remaining launch blocker.',
        )
        self.other_project = Project.objects.create(name='Private Orion project')
        other_group = ProjectGroup.objects.create(project=self.other_project)
        other_group.members.add(self.user)
        other_meeting = Meeting.objects.create(
            title='Orion confidential planning', scheduled_at='2026-11-20T11:00:00Z',
            created_by=self.user, project=self.other_project,
        )
        TranscriptLine.objects.create(
            meeting=other_meeting, speaker=self.user,
            text='Confidential Orion acquisition details must never be exposed.',
        )
        self.client.force_login(self.user)

    @patch('apps.meetings.ai.groq_client')
    def test_answer_context_retrieves_project_sources_and_excludes_other_projects(self, mock_groq_client):
        create_completion = Mock(return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='Priya owns the regression test [Task source].'))]
        ))
        mock_groq_client.return_value = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=create_completion)
            )
        )

        response = self.client.post(
            reverse('project_ai_chat', args=[self.group.pk]),
            {'body': 'Who owns regression testing for the Aurora release?'},
            HTTP_ACCEPT='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('answer', response.json())
        prompt = create_completion.call_args.kwargs['messages'][0]['content']
        self.assertIn(f'[Task #{self.task.pk}: Aurora release planning]', prompt)
        self.assertIn('Complete dashboard regression testing', prompt)
        self.assertIn('Retrieved transcript passages', prompt)
        self.assertIn('Retrieved project group messages', prompt)
        self.assertIn('Operations analyst', prompt)
        self.assertIn('Led delivery planning', prompt)
        self.assertNotIn('Age: 38', prompt)
        self.assertNotIn('Orion confidential', prompt)

    def test_search_queryset_matches_terms_without_crossing_project_queryset(self):
        from .retrieval import search_queryset

        matches = search_queryset(
            TranscriptLine.objects.filter(meeting__project=self.project).select_related('meeting'),
            'Aurora regression testing',
            ('text', 'meeting__title'),
            limit=5,
        )

        self.assertEqual([line.pk for line in matches], [self.line.pk])
        self.assertEqual(self.task.assigned_to, self.user)


class DailyUpdateTests(TestCase):
    def setUp(self):
        self.member = User.objects.create_user(
            username='daily_member', email='daily_member@example.com', password='test-pass-123',
        )
        self.project = Project.objects.create(name='Daily report project')
        self.group = ProjectGroup.objects.create(project=self.project, project_manager=self.member)
        self.group.members.add(self.member)
        self.client.force_login(self.member)

    def post_update(self, **overrides):
        data = {
            'project_id': str(self.project.public_id),
            'working_on': 'Prepare the reporting dashboard',
            'completed_today': 'Added the first dashboard layout and reviewed it with the team.',
            'remaining_work': 'Connect the weekly usage metric.',
            'blockers': 'Waiting for the API test data.',
            'no_work_today': '',
            'hours_worked': '6.5',
        }
        data.update(overrides)
        return self.client.post(reverse('daily_update_submit'), data)

    def test_daily_update_is_saved_to_authenticated_user_and_project(self):
        response = self.post_update(email='other-person@example.com')

        self.assertRedirects(response, reverse('daily_update_submit'))
        update = DailyUpdate.objects.get()
        self.assertEqual(update.user, self.member)
        self.assertEqual(update.user.email, 'daily_member@example.com')
        self.assertEqual(update.project, self.project)
        self.assertIn('first dashboard layout', update.completed_today)
        self.assertEqual(str(update.hours_worked), '6.5')
        self.assertNotContains(self.client.get(reverse('daily_update_submit')), 'Added the first dashboard layout')

    def test_resubmitting_same_project_updates_today_record(self):
        self.post_update()
        self.post_update(completed_today='Dashboard layout reviewed and approved.')

        self.assertEqual(DailyUpdate.objects.count(), 1)
        self.assertEqual(DailyUpdate.objects.get().completed_today, 'Dashboard layout reviewed and approved.')

    def test_user_cannot_report_to_a_project_they_do_not_belong_to(self):
        outsider = User.objects.create_user(
            username='outsider', email='outsider@example.com', password='test-pass-123',
        )
        self.client.force_login(outsider)

        response = self.post_update()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'You can submit updates only to a project you belong to.')
        self.assertEqual(DailyUpdate.objects.count(), 0)

    def test_admin_overview_shows_updates_and_missing_project_members(self):
        missing = User.objects.create_user(
            username='missing_member', email='missing@example.com', password='test-pass-123',
        )
        self.group.members.add(missing)
        self.post_update()
        admin = User.objects.create_user(
            username='daily_admin', email='daily_admin@example.com', password='test-pass-123', role='admin',
        )
        self.client.force_login(admin)

        response = self.client.get(reverse('daily_update_overview'), {'project': str(self.project.public_id)})

        self.assertContains(response, 'Prepare the reporting dashboard')
        self.assertContains(response, 'missing_member')
        self.assertContains(response, 'Who submitted a daily update today, and who has not?')

    def test_non_admin_cannot_view_team_daily_updates(self):
        response = self.client.get(reverse('daily_update_overview'))

        self.assertRedirects(response, reverse('dashboard'))


class CompanyAdminWorkspaceTests(TestCase):
    def setUp(self):
        self.employee = User.objects.create_user(
            username='company_employee', email='company_employee@example.com', password='test-pass-123',
            first_name='Asha', last_name='Rao',
        )
        self.profile = EmployeeProfile.objects.create(
            user=self.employee, department='Design', designation='Product designer',
            experience='Leads user research and product design.', skills=['research', 'design'],
        )
        self.project = Project.objects.create(name='Company admin project', description='Private project work.')
        self.group = ProjectGroup.objects.create(project=self.project)
        self.group.members.add(self.employee)
        self.update = DailyUpdate.objects.create(
            user=self.employee, project=self.project, working_on='Review onboarding flows',
            completed_today='Mapped the first-run experience.', remaining_work='Prototype the new flow.',
            blockers='Waiting for research notes.',
        )

    def test_employee_cannot_access_admin_employee_list_or_details(self):
        self.client.force_login(self.employee)

        list_response = self.client.get(reverse('company_employee_updates'))
        detail_response = self.client.get(reverse('company_employee_detail', args=[self.employee.pk]))

        self.assertRedirects(list_response, reverse('dashboard'))
        self.assertRedirects(detail_response, reverse('dashboard'))
        self.assertNotContains(self.client.get(reverse('dashboard')), 'Employee updates')

    def test_app_admin_can_review_employee_and_daily_submissions(self):
        admin_user = User.objects.create_user(
            username='company_admin', email='company_admin@example.com', password='test-pass-123', role='admin',
        )
        self.client.force_login(admin_user)

        roster = self.client.get(reverse('company_employee_updates'))
        details = self.client.get(reverse('company_employee_detail', args=[self.employee.pk]))

        self.assertContains(roster, self.employee.email)
        self.assertContains(roster, 'Employee updates')
        self.assertContains(details, self.profile.experience)
        self.assertContains(details, self.project.name)
        self.assertContains(details, self.update.completed_today)
        self.assertContains(details, self.update.remaining_work)
        self.assertContains(details, self.update.blockers)

    def test_staff_superuser_gets_app_admin_navigation(self):
        staff_user = User.objects.create_superuser(
            username='staff_owner', email='staff_owner@example.com', password='test-pass-123',
        )
        self.client.force_login(staff_user)

        response = self.client.get(reverse('dashboard'))

        self.assertContains(response, 'Employee updates')
        self.assertContains(response, reverse('company_employee_updates'))
        self.assertNotContains(response, 'admin:index')

    def test_employee_cannot_open_company_ai_or_see_admin_links(self):
        self.client.force_login(self.employee)

        response = self.client.get(reverse('company_ai'))
        dashboard = self.client.get(reverse('dashboard'))

        self.assertRedirects(response, reverse('dashboard'))
        self.assertNotContains(dashboard, 'Company AI')
        self.assertNotContains(dashboard, 'Employee updates')

    @patch('apps.meetings.ai.groq_client')
    def test_admin_ai_uses_employee_profile_daily_updates_and_company_context(self, mock_groq_client):
        admin_user = User.objects.create_user(
            username='company_admin_chat', email='company_admin_chat@example.com',
            password='test-pass-123', role='admin',
        )
        mock_groq_client.return_value = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=Mock(return_value=SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content='Asha completed the onboarding flow map.'))]
            ))))
        )
        self.client.force_login(admin_user)

        response = self.client.post(reverse('company_ai'), {'body': 'What did Asha complete today?'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Asha completed the onboarding flow map.')
        self.assertEqual(CompanyAIMessage.objects.filter(user=admin_user).count(), 2)
        prompt = mock_groq_client.return_value.chat.completions.create.call_args.kwargs['messages'][0]['content']
        self.assertIn('Asha Rao', prompt)
        self.assertIn(self.employee.email, prompt)
        self.assertIn(self.profile.experience, prompt)
        self.assertIn(self.update.completed_today, prompt)
        self.assertIn(self.project.name, prompt)

    def test_employee_cannot_open_another_projects_group_ai(self):
        other_employee = User.objects.create_user(
            username='other_project_owner', email='other_project_owner@example.com', password='test-pass-123',
        )
        other_project = Project.objects.create(name='Restricted second project')
        other_group = ProjectGroup.objects.create(project=other_project, project_manager=other_employee)
        other_group.members.add(other_employee)
        self.client.force_login(self.employee)

        response = self.client.post(
            reverse('project_ai_chat', args=[other_group.pk]),
            {'body': 'Show me every project and employee record.'},
        )

        self.assertRedirects(response, reverse('dashboard'))
        self.assertFalse(ProjectAIMessage.objects.filter(group=other_group, user=self.employee).exists())


class SemanticRetrievalUtilityTests(TestCase):
    def test_text_chunking_has_overlap_and_covers_long_content(self):
        from .semantic import CHUNK_LENGTH, split_text

        text = 'project work ' * 250
        chunks = split_text(text)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= CHUNK_LENGTH for chunk in chunks))
        self.assertIn(chunks[0][-80:], chunks[1])
        self.assertTrue(chunks[-1].endswith('project work'))
