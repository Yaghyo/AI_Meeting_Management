from django.contrib.auth import authenticate, login
from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
import logging
from django.shortcuts import redirect, render
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from .forms import EmployeeProfileForm
from .models import EmployeeProfile, User


logger = logging.getLogger(__name__)


class EmployeeRegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('email', 'username')

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError('An account with this email already exists.')
        return email


class EmailAuthenticationForm(AuthenticationForm):
    username = forms.EmailField(label='Email', widget=forms.EmailInput(attrs={'autofocus': True, 'autocomplete': 'email'}))

    def clean(self):
        email = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')
        if email and password:
            self.user_cache = authenticate(self.request, email=email.strip().lower(), password=password)
            if self.user_cache is None:
                raise self.get_invalid_login_error()
            self.confirm_login_allowed(self.user_cache)
        return self.cleaned_data


def register(request):
    form = EmployeeRegistrationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        EmployeeProfile.objects.create(user=user)
        login(request, user)
        return redirect('dashboard')
    return render(request, 'registration/register.html', {'form': form})


@login_required
def profile_detail(request):
    profile, _ = EmployeeProfile.objects.get_or_create(user=request.user)
    old_resume_name = profile.resume.name if profile.resume else ''
    form = EmployeeProfileForm(request.POST or None, request.FILES or None, instance=profile)
    if request.method == 'POST' and form.is_valid():
        profile = form.save(commit=False)
        resume_text = getattr(form, 'resume_text', '')
        if form.cleaned_data.get('remove_resume') and not resume_text:
            profile.resume = ''
            profile.resume_text = ''
        elif resume_text:
            profile.resume_text = resume_text
        elif not profile.resume:
            profile.resume_text = ''
        profile.save()

        new_resume_name = profile.resume.name if profile.resume else ''
        if old_resume_name and old_resume_name != new_resume_name:
            try:
                default_storage.delete(old_resume_name)
            except Exception:
                logger.exception('Could not remove replaced resume file for user %s', request.user.pk)
        messages.success(request, 'Your profile has been saved.')
        return redirect('profile_detail')
    return render(request, 'accounts/profile.html', {'form': form, 'profile': profile})
