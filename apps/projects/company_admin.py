from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from apps.accounts.models import EmployeeProfile
from apps.accounts.permissions import company_admin_required
from apps.meetings.models import ActionItem
from .models import DailyUpdate, Project


User = get_user_model()


def _employee_queryset():
    return User.objects.filter(
        is_active=True,
        role=User.Role.EMPLOYEE,
        is_staff=False,
    ).select_related('profile')


@company_admin_required
def employee_updates(request):
    today = timezone.localdate()
    employees = _employee_queryset().annotate(
        project_count=Count('project_groups__project', distinct=True),
        today_update_count=Count('daily_updates', filter=Q(daily_updates__report_date=today), distinct=True),
    ).order_by('first_name', 'last_name', 'username')
    query = request.GET.get('q', '').strip()
    if query:
        employees = employees.filter(
            Q(username__icontains=query) | Q(email__icontains=query)
            | Q(first_name__icontains=query) | Q(last_name__icontains=query)
            | Q(profile__full_name__icontains=query) | Q(profile__department__icontains=query)
        ).distinct()
    return render(request, 'projects/company_employee_list.html', {
        'employees': employees,
        'query': query,
        'today': today,
        'employee_count': _employee_queryset().count(),
    })


@company_admin_required
def employee_detail(request, user_id):
    employee = get_object_or_404(
        _employee_queryset().prefetch_related('project_groups__project'), pk=user_id,
    )
    profile, _ = EmployeeProfile.objects.get_or_create(user=employee)
    projects = Project.objects.filter(group__members=employee).distinct().order_by('name')
    updates = list(
        DailyUpdate.objects.filter(user=employee).select_related('project')
        .order_by('-report_date', '-submitted_at')[:90]
    )
    tasks = ActionItem.objects.filter(assigned_to=employee).select_related(
        'meeting', 'meeting__project',
    ).order_by('due_date', '-id')[:60]
    today = timezone.localdate()
    today_updates = [row for row in updates if row.report_date == today]
    return render(request, 'projects/company_employee_detail.html', {
        'employee': employee,
        'profile': profile,
        'projects': projects,
        'updates': updates,
        'today_updates': today_updates,
        'tasks': tasks,
        'today': today,
    })
