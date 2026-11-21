from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import EmployeeProfile, User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (('Meeting AI', {'fields': ('role',)}),)
    list_display = ('username', 'email', 'role', 'is_active', 'is_staff')


@admin.register(EmployeeProfile)
class EmployeeProfileAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'user', 'department', 'designation')
