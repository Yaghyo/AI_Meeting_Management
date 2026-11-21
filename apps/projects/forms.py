from django import forms

from .models import DailyUpdate


class DailyUpdateForm(forms.ModelForm):
    project_id = forms.UUIDField(
        label='Project ID',
        help_text='Paste the project ID shown beside your project name.',
        widget=forms.TextInput(attrs={'placeholder': 'Project UUID', 'autocomplete': 'off'}),
    )

    class Meta:
        model = DailyUpdate
        fields = (
            'project_id', 'working_on', 'completed_today', 'remaining_work', 'blockers',
            'no_work_today', 'hours_worked',
        )
        widgets = {
            'working_on': forms.Textarea(attrs={
                'rows': 2, 'placeholder': 'What project work were you focused on today?',
            }),
            'completed_today': forms.Textarea(attrs={
                'rows': 4, 'placeholder': 'What did you finish or move forward? Add concrete results where possible.',
            }),
            'remaining_work': forms.Textarea(attrs={
                'rows': 3, 'placeholder': 'What is still left to do? Mention the next milestone or estimate if known.',
            }),
            'blockers': forms.Textarea(attrs={
                'rows': 2, 'placeholder': 'Anything blocked or needing help? Write “None” if there are no blockers.',
            }),
            'hours_worked': forms.NumberInput(attrs={'min': '0', 'max': '24', 'step': '0.5', 'placeholder': 'Optional'}),
        }

    def clean(self):
        cleaned = super().clean()
        no_work = cleaned.get('no_work_today')
        completed = (cleaned.get('completed_today') or '').strip()
        working = (cleaned.get('working_on') or '').strip()
        if no_work and completed:
            self.add_error('completed_today', 'Clear completed work if you select “No work today”.')
        if not no_work and not completed:
            self.add_error('completed_today', 'Describe work completed, or select “No work today”.')
        if not no_work and not working:
            self.add_error('working_on', 'Describe what you worked on today.')
        return cleaned
