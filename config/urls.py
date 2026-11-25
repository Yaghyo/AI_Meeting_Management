"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from django.contrib.auth import views as auth_views
from apps.accounts.views import EmailAuthenticationForm, profile_detail, register
from apps.meetings import views as meeting_views
from apps.projects import views as project_views
from apps.projects import company_admin as company_admin_views
from apps.projects import company_assistant as company_assistant_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', meeting_views.dashboard, name='dashboard'),
    path('accounts/login/', auth_views.LoginView.as_view(template_name='registration/login.html', authentication_form=EmailAuthenticationForm), name='login'),
    path('accounts/logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('accounts/register/', register, name='register'),
    path('accounts/profile/', profile_detail, name='profile_detail'),
    path('meetings/new/', meeting_views.meeting_create, name='meeting_create'),
    path('meetings/<int:pk>/edit/', meeting_views.meeting_edit, name='meeting_edit'),
    path('meetings/<int:pk>/delete/', meeting_views.meeting_delete, name='meeting_delete'),
    path('meetings/<int:pk>/room/', meeting_views.meeting_room, name='meeting_room'),
    path('meetings/<int:pk>/invite/<uuid:invite_token>/', meeting_views.meeting_invite, name='meeting_invite'),
    path('meetings/<int:pk>/token/', meeting_views.meeting_token, name='meeting_token'),
    path('meetings/<int:pk>/transcript/', meeting_views.meeting_transcript, name='meeting_transcript'),
    path('meetings/<int:pk>/end/', meeting_views.meeting_end, name='meeting_end'),
    path('meetings/<int:pk>/ai-report/', meeting_views.meeting_ai_report, name='meeting_ai_report'),
    path('meetings/', meeting_views.meetings_page, name='meetings_page'),
    path('meetings/<int:pk>/', meeting_views.meeting_detail, name='meeting_detail'),
    path('projects/groups/<int:pk>/', project_views.group_detail, name='project_group'),
    path('projects/groups/<int:pk>/manager/', project_views.volunteer_manager, name='volunteer_manager'),
    path('projects/groups/<int:pk>/members/', project_views.manage_group_member, name='manage_group_member'),
    path('projects/groups/<int:pk>/ai-chat/', project_views.project_ai_chat, name='project_ai_chat'),
    path('people/<int:pk>/chat/', project_views.direct_chat, name='direct_chat'),
    path('chat/unread/', project_views.unread_counts, name='unread_counts'),
    path('daily-updates/', project_views.daily_update_submit, name='daily_update_submit'),
    path('daily-updates/overview/', project_views.daily_update_overview, name='daily_update_overview'),
    path('company/employees/', company_admin_views.employee_updates, name='company_employee_updates'),
    path('company/employees/<int:user_id>/', company_admin_views.employee_detail, name='company_employee_detail'),
    path('company/assistant/', company_assistant_views.company_ai, name='company_ai'),
]
