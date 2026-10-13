from datetime import date
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db.models import Q, Sum, Count, Avg
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.db import transaction
from django.http import FileResponse, Http404
from .decorators import (ADMIN, HOD, FACULTY, get_role, get_department, can_access_faculty,
                         role_required, scope_queryset, scoped_faculty)
from .forms import FacultyForm, QualificationForm, SubjectForm, AllocationForm, LeaveForm, PerformanceForm, UserCreateForm
from .models import Department, Faculty, Qualification, Subject, SubjectAllocation, Workload, LeaveRequest, PerformanceEvaluation, UserProfile


# --------------------------------------------------------------------------
# RBAC helpers
# --------------------------------------------------------------------------
def _denied(request):
    messages.error(request, 'You do not have permission to access that record.')
    return redirect('dashboard')


def visible_departments(user):
    """Departments the user may pick / filter by."""
    qs = Department.objects.filter(status=True)
    role = get_role(user)
    if role == ADMIN:
        return qs
    if role == HOD:
        dept = get_department(user)
        return qs.filter(pk=dept.pk) if dept else qs.none()
    return qs.none()


def login_page(request):
    return render(request, 'registration/login.html')


@login_required
def dashboard(request):
    user = request.user
    role = get_role(user)
    faculties = scoped_faculty(user)
    allocations = scope_queryset(SubjectAllocation.objects.all(), user, 'department', 'faculty')
    leaves = scope_queryset(LeaveRequest.objects.all(), user, 'faculty__department', 'faculty')
    evaluations = scope_queryset(PerformanceEvaluation.objects.select_related('faculty'), user, 'faculty__department', 'faculty')
    active_allocations = allocations.filter(status='Active')
    if role == ADMIN:
        subjects = Subject.objects.filter(status='Active')
    elif role == HOD:
        subjects = scope_queryset(Subject.objects.filter(status='Active'), user, 'department')
    else:
        subjects = Subject.objects.filter(status='Active', allocations__in=active_allocations).distinct()
    high_workload = (faculties.select_related('department')
                     .annotate(total_hours=Sum('allocations__hours_per_week', filter=Q(allocations__status='Active')))
                     .filter(total_hours__gt=20).order_by('-total_hours')[:5])
    context = {
        'own_faculty': Faculty.objects.filter(user=user).first(),
        'total_faculty': faculties.count(),
        'active_faculty': faculties.filter(status='Active').count(),
        'departments': visible_departments(user).count(),
        'subjects': subjects.count(),
        'pending_leaves': leaves.filter(status='Pending').count(),
        'allocations': active_allocations.count(),
        'weekly_hours': active_allocations.aggregate(total=Sum('hours_per_week'))['total'] or 0,
        'high_workload': high_workload,
        'recent_evaluations': evaluations.order_by('-evaluation_date')[:5],
    }
    return render(request, 'dashboard/dashboard.html', context)


@login_required
@role_required('ADMIN', 'HOD')
def faculty_list(request):
    qs = Faculty.objects.select_related('department').all().order_by('name')
    q = request.GET.get('q', '')
    department = request.GET.get('department', '')
    designation = request.GET.get('designation', '')
    status = request.GET.get('status', '')
    qs = qs.filter(pk__in=scoped_faculty(request.user).values('pk'))
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(faculty_id__icontains=q) | Q(email__icontains=q))
    if department:
        qs = qs.filter(department_id=department)
    if designation:
        qs = qs.filter(designation__icontains=designation)
    if status:
        qs = qs.filter(status=status)
    paginator = Paginator(qs, 8)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'faculty/list.html', {'page': page, 'departments': visible_departments(request.user), 'q': q, 'designation': designation, 'status': status})


@login_required
@role_required('ADMIN', 'HOD')
def faculty_add(request):
    form = FacultyForm(request.POST or None, request.FILES or None)
    form.fields['department'].queryset = visible_departments(request.user)
    if request.method == 'POST' and form.is_valid():
        faculty = form.save()
        messages.success(request, 'Faculty profile added successfully.')
        return redirect('faculty_detail', faculty.pk)
    return render(request, 'faculty/form.html', {'form': form, 'title': 'Add Faculty', 'button': 'Save Faculty'})


@login_required
@role_required('ADMIN', 'HOD')
def faculty_edit(request, pk):
    faculty = scoped_faculty(request.user).filter(pk=pk).first()
    if faculty is None:
        return _denied(request)
    form = FacultyForm(request.POST or None, request.FILES or None, instance=faculty)
    form.fields['department'].queryset = visible_departments(request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Faculty profile updated.')
        return redirect('faculty_detail', faculty.pk)
    return render(request, 'faculty/form.html', {'form': form, 'title': 'Edit Faculty', 'button': 'Update Faculty', 'faculty': faculty})


@login_required
def faculty_detail(request, pk):
    faculty = scoped_faculty(request.user).select_related('department').filter(pk=pk).first()
    if faculty is None:
        return _denied(request)
    return render(request, 'faculty/detail.html', {'faculty': faculty, 'qualifications': faculty.qualifications.all(), 'allocations': faculty.allocations.select_related('subject'), 'leaves': faculty.leaves.order_by('-applied_date')[:5], 'evaluations': faculty.evaluations.order_by('-evaluation_date')[:5]})


@login_required
def faculty_own(request):
    """'My Profile' shortcut for the logged-in faculty member."""
    own = Faculty.objects.filter(user=request.user).first()
    if own is None:
        messages.error(request, 'Your login is not linked to a faculty record. Please contact the administrator.')
        return redirect('dashboard')
    return redirect('faculty_detail', own.pk)


@login_required
@role_required('ADMIN')
def faculty_delete(request, pk):
    faculty = get_object_or_404(Faculty, pk=pk)
    if request.method == 'POST':
        faculty.delete()
        messages.success(request, 'Faculty profile deleted.')
    return redirect('faculty_list')


def _qualifications(user):
    return scope_queryset(Qualification.objects.select_related('faculty'), user, 'faculty__department', 'faculty')


@login_required
def qualification_list(request):
    qs = _qualifications(request.user).order_by('-year')
    return render(request, 'qualification/list.html', {'qualifications': qs})


@login_required
@role_required('ADMIN', 'HOD')
def qualification_add(request):
    form = QualificationForm(request.POST or None, request.FILES or None)
    form.fields['faculty'].queryset = scoped_faculty(request.user).order_by('name')
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Qualification saved successfully.')
        return redirect('qualification_list')
    return render(request, 'qualification/form.html', {'form': form, 'title': 'Add Qualification'})


@login_required
@role_required('ADMIN', 'HOD')
def qualification_edit(request, pk):
    obj = _qualifications(request.user).filter(pk=pk).first()
    if obj is None:
        return _denied(request)
    form = QualificationForm(request.POST or None, request.FILES or None, instance=obj)
    form.fields['faculty'].queryset = scoped_faculty(request.user).order_by('name')
    if request.method == 'POST' and form.is_valid():
        form.save(); messages.success(request, 'Qualification updated.'); return redirect('qualification_list')
    return render(request, 'qualification/form.html', {'form': form, 'title': 'Edit Qualification'})


@login_required
@role_required('ADMIN', 'HOD')
def qualification_delete(request, pk):
    obj = _qualifications(request.user).filter(pk=pk).first()
    if obj is None:
        return _denied(request)
    if request.method == 'POST': obj.delete(); messages.success(request, 'Qualification deleted.')
    return redirect('qualification_list')


def _subjects(user):
    return scope_queryset(Subject.objects.select_related('department'), user, 'department')


@login_required
@role_required('ADMIN', 'HOD')
def subject_list(request):
    qs = _subjects(request.user).order_by('subject_code')
    q = request.GET.get('q', '')
    department = request.GET.get('department', '')
    if q: qs = qs.filter(Q(subject_code__icontains=q) | Q(subject_name__icontains=q))
    if department: qs = qs.filter(department_id=department)
    return render(request, 'subject/list.html', {'subjects': qs, 'departments': visible_departments(request.user), 'q': q, 'selected_department': department})


@login_required
@role_required('ADMIN', 'HOD')
def subject_add(request):
    form = SubjectForm(request.POST or None)
    form.fields['department'].queryset = visible_departments(request.user)
    if request.method == 'POST' and form.is_valid(): form.save(); messages.success(request, 'Subject added.'); return redirect('subject_list')
    return render(request, 'subject/form.html', {'form': form, 'title': 'Add Subject'})


@login_required
@role_required('ADMIN', 'HOD')
def subject_edit(request, pk):
    obj = _subjects(request.user).filter(pk=pk).first()
    if obj is None:
        return _denied(request)
    form = SubjectForm(request.POST or None, instance=obj)
    form.fields['department'].queryset = visible_departments(request.user)
    if request.method == 'POST' and form.is_valid(): form.save(); messages.success(request, 'Subject updated.'); return redirect('subject_list')
    return render(request, 'subject/form.html', {'form': form, 'title': 'Edit Subject'})


@login_required
@role_required('ADMIN')
def subject_delete(request, pk):
    obj = get_object_or_404(Subject, pk=pk)
    if request.method == 'POST': obj.delete(); messages.success(request, 'Subject deleted.')
    return redirect('subject_list')


def _allocations(user):
    return scope_queryset(SubjectAllocation.objects.select_related('faculty', 'subject', 'department'), user, 'department', 'faculty')


@login_required
@role_required('ADMIN', 'HOD', 'FACULTY')
def allocation_list(request):
    qs = _allocations(request.user).order_by('-allocation_date')
    department = request.GET.get('department', '')
    semester = request.GET.get('semester', '')
    year = request.GET.get('academic_year', '')
    if department: qs = qs.filter(department_id=department)
    if semester: qs = qs.filter(semester=semester)
    if year: qs = qs.filter(academic_year=year)
    return render(request, 'allocation/list.html', {'allocations': qs, 'departments': visible_departments(request.user), 'selected_department': department, 'selected_semester': semester, 'selected_year': year})


@login_required
@role_required('ADMIN', 'HOD')
def allocation_add(request):
    form = AllocationForm(request.POST or None)
    form.fields['department'].queryset = visible_departments(request.user)
    form.fields['faculty'].queryset = scoped_faculty(request.user).order_by('name')
    form.fields['subject'].queryset = _subjects(request.user).filter(status='Active')
    if request.method == 'POST' and form.is_valid():
        obj = form.save()
        Workload.objects.update_or_create(faculty=obj.faculty, subject=obj.subject, academic_year=obj.academic_year, semester=obj.semester, defaults={'hours_per_week': obj.hours_per_week})
        messages.success(request, 'Subject allocated and workload updated.')
        return redirect('allocation_list')
    return render(request, 'allocation/form.html', {'form': form, 'title': 'Allocate Subject'})


@login_required
@role_required('ADMIN', 'HOD')
def allocation_delete(request, pk):
    obj = _allocations(request.user).filter(pk=pk).first()
    if obj is None:
        return _denied(request)
    if request.method == 'POST':
        Workload.objects.filter(faculty=obj.faculty, subject=obj.subject, academic_year=obj.academic_year, semester=obj.semester).delete()
        obj.delete(); messages.success(request, 'Allocation removed and workload recalculated.')
    return redirect('allocation_list')


@login_required
@role_required('ADMIN', 'HOD', 'FACULTY')
def workload(request):
    faculties = scoped_faculty(request.user).select_related('department').order_by('name')
    rows = []
    for faculty in faculties:
        items = faculty.allocations.filter(status='Active').select_related('subject')
        total = items.aggregate(total=Sum('hours_per_week'))['total'] or 0
        rows.append({'faculty': faculty, 'total': total, 'items': items})
    return render(request, 'workload/dashboard.html', {'rows': rows})


def _leaves(user):
    return scope_queryset(LeaveRequest.objects.select_related('faculty', 'approved_by'), user, 'faculty__department', 'faculty')


@login_required
@role_required('ADMIN', 'HOD', 'FACULTY')
def leave_list(request):
    qs = _leaves(request.user).order_by('-applied_date')
    status = request.GET.get('status', '')
    if status: qs = qs.filter(status=status)
    return render(request, 'leave/list.html', {'leaves': qs, 'status': status})


@login_required
@role_required('HOD', 'FACULTY')
def leave_add(request):
    # Faculty: only themselves. HOD: own department. Admin: everyone.
    allowed = scoped_faculty(request.user).order_by('name')
    if get_role(request.user) == FACULTY and not allowed.exists():
        messages.error(request, 'Your login is not linked to a faculty record. Please contact the administrator.')
        return redirect('leave_list')
    form = LeaveForm(request.POST or None)
    form.fields['faculty'].queryset = allowed
    if get_role(request.user) == FACULTY:
        form.fields['faculty'].initial = allowed.first()
    if request.method == 'POST' and form.is_valid(): form.save(); messages.success(request, 'Leave request submitted.'); return redirect('leave_list')
    return render(request, 'leave/form.html', {'form': form})


@login_required
@role_required('ADMIN', 'HOD')
def leave_action(request, pk, action):
    leave = _leaves(request.user).filter(pk=pk).first()
    if leave is None or action not in ('approve', 'reject'):
        return _denied(request)
    if get_role(request.user) == HOD and leave.faculty.user_id == request.user.id:
        messages.error(request, 'You cannot approve or reject your own leave request. Please ask the administrator.')
        return redirect('leave_list')
    if request.method == 'POST' and leave.status == 'Pending':
        if action == 'approve': leave.status = 'Approved'; message = 'Leave approved.'
        else: leave.status = 'Rejected'; message = 'Leave rejected.'
        leave.approved_by = request.user; leave.approval_date = timezone.now(); leave.remarks = request.POST.get('remarks', '')
        leave.save(); messages.success(request, message)
    return redirect('leave_list')


def _evaluations(user):
    return scope_queryset(PerformanceEvaluation.objects.select_related('faculty', 'evaluator'), user, 'faculty__department', 'faculty')


@login_required
@role_required('ADMIN', 'HOD', 'FACULTY')
def performance_list(request):
    qs = _evaluations(request.user).order_by('-evaluation_date')
    return render(request, 'performance/list.html', {'evaluations': qs})


@login_required
@role_required('ADMIN', 'HOD')
def performance_add(request):
    form = PerformanceForm(request.POST or None)
    form.fields['faculty'].queryset = scoped_faculty(request.user).order_by('name')
    if request.method == 'POST' and form.is_valid():
        obj = form.save(commit=False); obj.evaluator = request.user; obj.save(); messages.success(request, f'Evaluation saved. Score: {obj.total_score}/100 ({obj.rating}).'); return redirect('performance_list')
    return render(request, 'performance/form.html', {'form': form})


@login_required
@role_required('ADMIN', 'HOD')
def performance_delete(request, pk):
    obj = _evaluations(request.user).filter(pk=pk).first()
    if obj is None:
        return _denied(request)
    if request.method == 'POST': obj.delete(); messages.success(request, 'Evaluation deleted.')
    return redirect('performance_list')


# --------------------------------------------------------------------------
# User management (Admin only)
# --------------------------------------------------------------------------
def _save_user(form, user=None):
    """Persist user + role/department + faculty link atomically."""
    with transaction.atomic():
        new = form.save(commit=False)
        password = form.cleaned_data.get('password')
        if password:
            new.set_password(password)
        new.save()
        role = form.cleaned_data['role']
        dept = form.cleaned_data['department'] if role == HOD else None
        UserProfile.objects.update_or_create(user=new, defaults={'role': role, 'department': dept})
        Faculty.objects.filter(user=new).update(user=None)
        faculty = form.cleaned_data.get('faculty')
        if faculty:
            faculty.user = new
            faculty.save(update_fields=['user'])
    return new


@login_required
@role_required('ADMIN')
def user_list(request):
    users = User.objects.select_related('userprofile__department').order_by('username')
    linked = {f.user_id: f for f in Faculty.objects.filter(user__isnull=False)}
    rows = [{'user': u, 'role': get_role(u), 'department': getattr(getattr(u, 'userprofile', None), 'department', None), 'faculty': linked.get(u.id)} for u in users]
    return render(request, 'dashboard/user_list.html', {'rows': rows})


@login_required
@role_required('ADMIN')
def user_add(request):
    form = UserCreateForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        _save_user(form)
        messages.success(request, 'User account created.')
        return redirect('user_list')
    return render(request, 'dashboard/user_form.html', {'form': form, 'title': 'Create User Account', 'button': 'Create User'})


@login_required
@role_required('ADMIN')
def user_edit(request, pk):
    target = get_object_or_404(User, pk=pk)
    form = UserCreateForm(request.POST or None, instance=target)
    if request.method == 'POST' and form.is_valid():
        if target.pk == request.user.pk and form.cleaned_data['role'] != ADMIN and not target.is_superuser:
            form.add_error('role', 'You cannot remove your own administrator role.')
        else:
            _save_user(form)
            messages.success(request, 'User account updated.')
            return redirect('user_list')
    return render(request, 'dashboard/user_form.html', {'form': form, 'title': f'Edit User: {target.username}', 'button': 'Save Changes'})


@login_required
def protected_media(request, path):
    """Serve uploaded files only to users allowed to see the owning record."""
    from django.conf import settings
    import posixpath
    clean = posixpath.normpath(path).lstrip('/')
    if clean.startswith('..'):
        raise Http404
    faculty = Faculty.objects.filter(profile_photo=clean).first()
    qual = None if faculty else Qualification.objects.select_related('faculty').filter(certificate=clean).first()
    owner = faculty or (qual.faculty if qual else None)
    if owner is None or not can_access_faculty(request.user, owner):
        raise Http404
    full = (settings.MEDIA_ROOT / clean)
    if not full.is_file():
        raise Http404
    return FileResponse(open(full, 'rb'))


@login_required
@role_required('ADMIN')
def reports(request):
    return render(request, 'reports/index.html', {
        'department_rows': Department.objects.annotate(faculty_count=Count('faculty', distinct=True), subject_count=Count('subject', distinct=True)),
        'allocation_count': SubjectAllocation.objects.count(),
        'leave_count': LeaveRequest.objects.count(),
        'evaluation_count': PerformanceEvaluation.objects.count(),
    })
