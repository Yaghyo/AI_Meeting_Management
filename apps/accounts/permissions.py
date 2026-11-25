from functools import wraps

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect


def is_company_admin(user):
    return bool(user.is_authenticated and (user.is_staff or user.role == 'admin'))


def company_admin_required(view_func):
    @login_required
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not is_company_admin(request.user):
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return wrapped
