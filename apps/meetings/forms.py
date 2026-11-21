from django import forms
from apps.accounts.models import User
from apps.projects.models import Project
from .models import Meeting


class MeetingForm(forms.ModelForm):
    project = forms.ModelChoiceField(queryset=Project.objects.order_by('name'), required=False, empty_label='No project')
    participants = forms.ModelMultipleChoiceField(
        queryset=User.objects.filter(is_active=True).order_by('username'),
        required=False,
        help_text='Choose the employees who can join this meeting. You will be added automatically.',
        widget=forms.SelectMultiple(attrs={'size': 6}),
    )

    scheduled_at = forms.DateTimeField(
        input_formats=['%Y-%m-%dT%H:%M'],
        widget=forms.DateTimeInput(
            attrs={'type': 'datetime-local', 'step': '60'},
            format='%Y-%m-%dT%H:%M',
        ),
        help_text='Displayed in India Standard Time.',
    )
    ends_at = forms.DateTimeField(
        required=False,
        input_formats=['%Y-%m-%dT%H:%M'],
        widget=forms.DateTimeInput(
            attrs={'type': 'datetime-local', 'step': '60'},
            format='%Y-%m-%dT%H:%M',
        ),
        label='End time (optional)',
        help_text='Leave blank if the end time is not decided.',
    )

    class Meta:
        model = Meeting
        fields = ('title', 'scheduled_at', 'ends_at', 'project', 'participants')

    def clean(self):
        cleaned_data = super().clean()
        starts_at = cleaned_data.get('scheduled_at')
        ends_at = cleaned_data.get('ends_at')
        if starts_at and ends_at and ends_at <= starts_at:
            self.add_error('ends_at', 'End time must be after the meeting start time.')
        return cleaned_data
