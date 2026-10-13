"""Role-based access control (RBAC) helpers.

Roles
-----
ADMIN    full access (superusers are always ADMIN)
HOD      access limited to the HOD's own department
FACULTY  access limited to the faculty member's own records

Fail-safe rules: a HOD without a department, or a Faculty login that is not
linked to a Faculty record, sees nothing (never "everything").
"""
from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect

ADMIN, HOD, FACULTY = 'ADMIN', 'HOD', 'FACULTY'


def get_role(user):
    if not user.is_authenticated:
        return None
    if user.is_superuser:
        return ADMIN
    profile = getattr(user, 'userprofile', None)
    return profile.role if profile else FACULTY


def get_department(user):
    """Department of a HOD user (None for everybody else / unassigned HOD)."""
    profile = getattr(user, 'userprofile', None)
    return profile.department if profile else None


def get_own_faculty(user):
    """Faculty record linked to this login, if any."""
    from .models import Faculty
    return Faculty.objects.filter(user=user).select_related('department').first()


def scope_queryset(qs, user, department_field=None, faculty_field=None):
    """Restrict ``qs`` to what ``user`` may see.

    department_field: lookup path to a Department (used for HOD)
    faculty_field:    lookup path to a Faculty    (used for FACULTY)
    """
    role = get_role(user)
    if role == ADMIN:
        return qs
    if role == HOD:
        dept = get_department(user)
        if dept is None or department_field is None:
            return qs.none()
        return qs.filter(**{department_field: dept})
    if role == FACULTY and faculty_field:
        return qs.filter(**{f'{faculty_field}__user': user})
    return qs.none()


def scoped_faculty(user):
    """Faculty records visible to ``user`` (Faculty model owns the ``user`` link itself)."""
    from .models import Faculty
    role = get_role(user)
    if role == FACULTY:
        return Faculty.objects.filter(user=user)
    return scope_queryset(Faculty.objects.all(), user, 'department')


def can_access_faculty(user, faculty):
    role = get_role(user)
    if role == ADMIN:
        return True
    if role == HOD:
        dept = get_department(user)
        return dept is not None and faculty.department_id == dept.id
    return faculty.user_id is not None and faculty.user_id == user.id


def role_required(*allowed_roles):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if get_role(request.user) not in allowed_roles:
                messages.error(request, 'You do not have permission to access this page.')
                return redirect('dashboard')
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator
