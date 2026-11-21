from django.contrib.auth.models import AbstractUser
from django.db import models
from django.core.validators import FileExtensionValidator, MaxValueValidator, MinValueValidator


def validate_resume_size(upload):
    if upload.size > 5 * 1024 * 1024:
        from django.core.exceptions import ValidationError
        raise ValidationError('Resume files must be 5 MB or smaller.')


class User(AbstractUser):
    class Role(models.TextChoices):
        EMPLOYEE = 'employee', 'Employee'
        ADMIN = 'admin', 'Admin'

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.EMPLOYEE)
    email = models.EmailField(unique=True)


class EmployeeProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    full_name = models.CharField(max_length=150, blank=True)
    designation = models.CharField(max_length=100, blank=True)
    department = models.CharField(max_length=100, blank=True)
    age = models.PositiveSmallIntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(16), MaxValueValidator(100)],
        help_text='Optional. Age is stored in your profile and is not used by Project AI.',
    )
    experience = models.TextField(blank=True, help_text='Summarize your experience, strengths, and areas of expertise.')
    resume = models.FileField(
        upload_to='employee_resumes/%Y/%m/',
        blank=True,
        validators=[FileExtensionValidator(['pdf', 'docx', 'txt']), validate_resume_size],
    )
    resume_text = models.TextField(blank=True, editable=False)
    phone = models.CharField(max_length=20, blank=True)
    joined_on = models.DateField(null=True, blank=True)
    skills = models.JSONField(default=list, blank=True)

    def __str__(self):
        return self.full_name or self.user.username

# Create your models here.
