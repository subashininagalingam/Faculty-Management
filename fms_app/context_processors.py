from .decorators import ADMIN, FACULTY, HOD, get_department, get_role


def rbac(request):
    """Expose the current role to every template."""
    user = request.user
    if not user.is_authenticated:
        return {}
    role = get_role(user)
    return {
        'role': role,
        'is_admin': role == ADMIN,
        'is_hod': role == HOD,
        'is_faculty': role == FACULTY,
        'is_manager': role in (ADMIN, HOD),
        'user_department': get_department(user) if role == HOD else None,
    }
