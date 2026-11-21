from io import BytesIO
from pathlib import Path

from django import forms
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile

from .models import EmployeeProfile


MAX_RESUME_TEXT_LENGTH = 30_000


class CommaSeparatedSkillsField(forms.CharField):
    def to_python(self, value):
        value = super().to_python(value)
        return [skill.strip()[:80] for skill in value.split(',') if skill.strip()][:40]

    def prepare_value(self, value):
        if isinstance(value, (list, tuple)):
            return ', '.join(str(skill) for skill in value)
        return super().prepare_value(value)


class EmployeeProfileForm(forms.ModelForm):
    remove_resume = forms.BooleanField(required=False, label='Remove the saved resume')

    class Meta:
        model = EmployeeProfile
        fields = (
            'full_name', 'designation', 'department', 'age', 'phone',
            'experience', 'skills', 'resume', 'remove_resume',
        )
        widgets = {
            'full_name': forms.TextInput(attrs={'autocomplete': 'name', 'placeholder': 'Your name'}),
            'designation': forms.TextInput(attrs={'placeholder': 'e.g. Product designer'}),
            'department': forms.TextInput(attrs={'placeholder': 'e.g. Product'}),
            'age': forms.NumberInput(attrs={'min': 16, 'max': 100, 'placeholder': 'Optional'}),
            'phone': forms.TelInput(attrs={'autocomplete': 'tel', 'placeholder': 'Optional'}),
            'experience': forms.Textarea(attrs={
                'rows': 5,
                'maxlength': 6000,
                'placeholder': 'Describe your experience, strengths, and the kinds of work you do best.',
            }),
            'skills': forms.TextInput(attrs={
                'placeholder': 'Comma-separated, e.g. project planning, analytics, Python',
            }),
            'resume': forms.FileInput(attrs={
                'accept': '.pdf,.docx,.txt',
            }),
        }
    skills = CommaSeparatedSkillsField(
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'Comma-separated, e.g. project planning, analytics, Python',
        }),
        label='Skills',
        help_text='Separate skills with commas.',
    )

    def clean_skills(self):
        skills = self.cleaned_data.get('skills')
        return skills or []

    def clean_resume(self):
        upload = self.cleaned_data.get('resume')
        if not isinstance(upload, UploadedFile):
            return upload
        if upload.size > 5 * 1024 * 1024:
            raise ValidationError('Resume files must be 5 MB or smaller.')

        extension = Path(upload.name).suffix.lower()
        upload.seek(0)
        try:
            raw = upload.read()
            if extension == '.txt':
                text = raw.decode('utf-8-sig', errors='replace')
            elif extension == '.pdf':
                from pypdf import PdfReader
                reader = PdfReader(BytesIO(raw))
                extracted_pages = []
                for index, page in enumerate(reader.pages):
                    if index >= 50:
                        break
                    extracted_pages.append(page.extract_text() or '')
                text = '\n'.join(extracted_pages)
            elif extension == '.docx':
                from docx import Document
                document = Document(BytesIO(raw))
                paragraphs = [paragraph.text for paragraph in document.paragraphs]
                paragraphs.extend(
                    cell.text
                    for table in document.tables
                    for row in table.rows
                    for cell in row.cells
                )
                text = '\n'.join(paragraphs)
            else:
                raise ValidationError('Upload a PDF, DOCX, or TXT resume.')
        except ValidationError:
            raise
        except ImportError as error:
            raise ValidationError(
                'Resume extraction dependencies are missing. Install the packages from requirements.txt and retry.'
            ) from error
        except Exception as error:
            raise ValidationError(
                'We could not read this resume. Upload a text-based PDF, DOCX, or TXT file.'
            ) from error
        finally:
            upload.seek(0)

        text = '\n'.join(line.strip() for line in text.splitlines() if line.strip())
        if not text:
            raise ValidationError('This resume contains no extractable text. Try a text-based PDF or DOCX.')
        self.resume_text = text[:MAX_RESUME_TEXT_LENGTH]
        return upload
