from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .forms import EmployeeProfileForm
from .models import EmployeeProfile, User


class EmployeeProfileTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='profile_user', email='profile@example.com', password='test-pass-123',
        )
        self.profile = EmployeeProfile.objects.create(user=self.user)
        self.client.force_login(self.user)

    def test_profile_page_saves_work_details_and_skills(self):
        response = self.client.post(reverse('profile_detail'), {
            'full_name': 'Taylor Example',
            'designation': 'Project analyst',
            'department': 'Operations',
            'age': '34',
            'phone': '',
            'experience': 'Five years improving project delivery and reporting.',
            'skills': 'project planning, analytics',
            'remove_resume': '',
        })

        self.assertRedirects(response, reverse('profile_detail'))
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.age, 34)
        self.assertEqual(self.profile.department, 'Operations')
        self.assertEqual(self.profile.skills, ['project planning', 'analytics'])
        self.assertContains(self.client.get(reverse('profile_detail')), 'Professional profile')

    def test_text_resume_is_extracted_for_the_private_assistant(self):
        form = EmployeeProfileForm(
            data={
                'full_name': 'Taylor Example',
                'designation': 'Project analyst',
                'department': 'Operations',
                'age': '',
                'phone': '',
                'experience': '',
                'skills': '',
                'remove_resume': '',
            },
            files={'resume': SimpleUploadedFile(
                'resume.txt', b'Experienced analyst with project planning skills.', content_type='text/plain',
            )},
            instance=self.profile,
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertIn('Experienced analyst', form.resume_text)

    def test_sidebar_contains_profile_and_post_logout_controls(self):
        response = self.client.get(reverse('dashboard'))

        self.assertContains(response, reverse('profile_detail'))
        self.assertContains(response, 'Log out')
        self.assertContains(response, 'method="post"')
