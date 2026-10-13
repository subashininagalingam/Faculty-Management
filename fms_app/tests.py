"""RBAC end-to-end tests: Admin = everything, HOD = own department, Faculty = own data."""
import tempfile
from datetime import date

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from pathlib import Path

from .models import (Department, Faculty, LeaveRequest, PerformanceEvaluation, Qualification,
                     Subject, SubjectAllocation, UserProfile, Workload)

MEDIA = Path(tempfile.mkdtemp())


def mk_user(name, role, dept=None, superuser=False):
    u = User.objects.create_user(name, password='pw-12345!x', is_superuser=superuser)
    if not superuser:
        UserProfile.objects.create(user=u, role=role, department=dept)
    return u


@override_settings(MEDIA_ROOT=MEDIA)
class RBACTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cs = Department.objects.create(name='Computer Science', code='CS')
        cls.it = Department.objects.create(name='Information Tech', code='IT')
        cls.admin = mk_user('admin', 'ADMIN', superuser=True)
        cls.hod_cs = mk_user('hod_cs', 'HOD', cls.cs)
        cls.hod_it = mk_user('hod_it', 'HOD', cls.it)
        cls.hod_none = mk_user('hod_none', 'HOD', None)
        cls.fac_cs_user = mk_user('fac_cs', 'FACULTY')
        cls.fac_it_user = mk_user('fac_it', 'FACULTY')
        cls.unlinked = mk_user('unlinked', 'FACULTY')
        cls.data = {}
        for tag, dept, user in (('cs', cls.cs, cls.fac_cs_user), ('it', cls.it, cls.fac_it_user)):
            f = Faculty.objects.create(faculty_id=f'F-{tag}', name=f'Prof {tag.upper()}', gender='Male', email=f'{tag}@x.com',
                                       phone='9999999999', department=dept, designation='Professor', joining_date=date(2020, 1, 1),
                                       employment_type='Permanent', user=user)
            s = Subject.objects.create(subject_code=f'SUB-{tag}', subject_name=f'Subject {tag.upper()}', department=dept, semester=1)
            a = SubjectAllocation.objects.create(faculty=f, subject=s, department=dept, semester=1, academic_year='2026-27', hours_per_week=25)
            l = LeaveRequest.objects.create(faculty=f, leave_type='Casual', from_date=date(2026, 5, 1), to_date=date(2026, 5, 2), reason=f'reason-{tag}')
            e = PerformanceEvaluation.objects.create(faculty=f, evaluator=cls.admin, evaluation_period=f'period-{tag}', evaluation_date=date(2026, 1, 1),
                                                     **{k: 8 for k in ['teaching_effectiveness', 'attendance_punctuality', 'subject_completion', 'student_feedback',
                                                                        'academic_contribution', 'research_publications', 'department_activities', 'overall_performance']})
            q = Qualification.objects.create(faculty=f, degree=f'Degree-{tag}', specialization='X', institution='Inst', year=2015,
                                             certificate=SimpleUploadedFile(f'cert_{tag}.pdf', b'%PDF cert'))
            f.profile_photo = SimpleUploadedFile(f'photo_{tag}.jpg', b'jpgdata'); f.save()
            cls.data[tag] = dict(f=f, s=s, a=a, l=l, e=e, q=q)

    def login(self, user):
        self.client.force_login(user)

    def get(self, name, *args, **kw):
        return self.client.get(reverse(name, args=args), **kw)

    # ---- helpers -------------------------------------------------------
    def assertSees(self, resp, *texts):
        for t in texts:
            self.assertContains(resp, t)

    def assertHides(self, resp, *texts):
        for t in texts:
            self.assertNotContains(resp, t)

    # ---- authentication ------------------------------------------------
    def test_anonymous_redirected_everywhere(self):
        for name in ['dashboard', 'faculty_list', 'qualification_list', 'subject_list', 'allocation_list', 'workload',
                     'leave_list', 'performance_list', 'reports', 'user_list', 'user_add']:
            r = self.get(name)
            self.assertEqual(r.status_code, 302, name)
            self.assertIn('/login/', r['Location'])

    # ---- ADMIN ---------------------------------------------------------
    def test_admin_sees_everything(self):
        self.login(self.admin)
        for name in ['dashboard', 'faculty_list', 'qualification_list', 'subject_list', 'allocation_list', 'workload',
                     'leave_list', 'performance_list', 'reports', 'user_list', 'user_add']:
            self.assertEqual(self.get(name).status_code, 200, name)
        self.assertSees(self.get('faculty_list'), 'Prof CS', 'Prof IT')
        self.assertSees(self.get('subject_list'), 'Subject CS', 'Subject IT')
        self.assertSees(self.get('leave_list'), 'reason-cs', 'reason-it')
        self.assertSees(self.get('performance_list'), 'period-cs', 'period-it')
        self.assertSees(self.get('qualification_list'), 'Degree-cs', 'Degree-it')
        self.assertSees(self.get('allocation_list'), 'Prof CS', 'Prof IT')
        self.assertSees(self.get('workload'), 'Prof CS', 'Prof IT')
        d = self.get('dashboard')
        self.assertEqual(d.context['total_faculty'], 2)
        self.assertEqual(d.context['departments'], 2)
        self.assertEqual(d.context['pending_leaves'], 2)
        self.assertSees(self.get('dashboard'), 'Users')

    def test_superuser_without_profile_sees_delete_buttons(self):
        self.login(self.admin)
        self.assertContains(self.get('subject_list'), 'subject_delete'.replace('subject_delete', '/subjects/%d/delete/' % self.data['cs']['s'].pk))

    # ---- HOD -----------------------------------------------------------
    def test_hod_sees_only_own_department(self):
        self.login(self.hod_cs)
        self.assertSees(self.get('faculty_list'), 'Prof CS'); self.assertHides(self.get('faculty_list'), 'Prof IT')
        self.assertSees(self.get('subject_list'), 'Subject CS'); self.assertHides(self.get('subject_list'), 'Subject IT')
        self.assertSees(self.get('leave_list'), 'reason-cs'); self.assertHides(self.get('leave_list'), 'reason-it')
        self.assertSees(self.get('performance_list'), 'period-cs'); self.assertHides(self.get('performance_list'), 'period-it')
        self.assertSees(self.get('qualification_list'), 'Degree-cs'); self.assertHides(self.get('qualification_list'), 'Degree-it')
        self.assertSees(self.get('allocation_list'), 'Prof CS'); self.assertHides(self.get('allocation_list'), 'Prof IT')
        self.assertSees(self.get('workload'), 'Prof CS'); self.assertHides(self.get('workload'), 'Prof IT')
        d = self.get('dashboard')
        for k, v in dict(total_faculty=1, active_faculty=1, departments=1, subjects=1, pending_leaves=1, allocations=1).items():
            self.assertEqual(d.context[k], v, k)
        self.assertHides(d, 'Prof IT', 'period-it'); self.assertSees(d, 'Prof CS')
        self.assertHides(d, 'Information Tech')

    def test_hod_filters_and_dropdowns_do_not_leak(self):
        self.login(self.hod_cs)
        # department filter dropdowns list only own department
        for name in ['faculty_list', 'subject_list', 'allocation_list']:
            self.assertHides(self.get(name), 'Information Tech')
        # trying to filter by another department yields nothing
        r = self.client.get(reverse('faculty_list') + f'?department={self.it.pk}')
        self.assertHides(r, 'Prof IT', 'Prof CS')
        # form dropdowns
        for name in ['faculty_add', 'subject_add', 'allocation_add', 'qualification_add', 'performance_add', 'leave_add']:
            r = self.get(name)
            self.assertEqual(r.status_code, 200, name)
            self.assertHides(r, 'Prof IT', 'Information Tech', 'Subject IT')

    def test_hod_cannot_touch_other_department_objects(self):
        self.login(self.hod_cs)
        o = self.data['it']
        for name, obj in [('faculty_detail', o['f']), ('faculty_edit', o['f']), ('qualification_edit', o['q']), ('subject_edit', o['s'])]:
            r = self.get(name, obj.pk)
            self.assertEqual(r.status_code, 302, name); self.assertEqual(r['Location'], reverse('dashboard'))
        for name, obj in [('qualification_delete', o['q']), ('subject_delete', o['s']), ('allocation_delete', o['a']),
                          ('performance_delete', o['e']), ('faculty_delete', o['f'])]:
            self.client.post(reverse(name, args=[obj.pk]))
        for action in ('approve', 'reject'):
            self.client.post(reverse('leave_action', args=[o['l'].pk, action]))
        self.assertTrue(Faculty.objects.filter(pk=o['f'].pk).exists())
        self.assertTrue(Qualification.objects.filter(pk=o['q'].pk).exists())
        self.assertTrue(Subject.objects.filter(pk=o['s'].pk).exists())
        self.assertTrue(SubjectAllocation.objects.filter(pk=o['a'].pk).exists())
        self.assertTrue(PerformanceEvaluation.objects.filter(pk=o['e'].pk).exists())
        o['l'].refresh_from_db(); self.assertEqual(o['l'].status, 'Pending')

    def test_hod_cannot_create_in_other_department(self):
        self.login(self.hod_cs)
        r = self.client.post(reverse('subject_add'), dict(subject_code='X1', subject_name='Sneaky', department=self.it.pk, semester=1,
                                                          academic_year='2026-27', credits=3, hours_per_week=3, status='Active'))
        self.assertEqual(r.status_code, 200); self.assertFalse(Subject.objects.filter(subject_code='X1').exists())
        # moving own faculty into another dept is blocked
        f = self.data['cs']['f']
        r = self.client.post(reverse('faculty_edit', args=[f.pk]), dict(faculty_id=f.faculty_id, name=f.name, gender='Male', email=f.email, phone='9999999999',
                             department=self.it.pk, designation='Professor', joining_date='2020-01-01', employment_type='Permanent', experience=1, status='Active'))
        f.refresh_from_db(); self.assertEqual(f.department_id, self.cs.pk)
        # evaluating / leave for other dept faculty
        r = self.client.post(reverse('leave_add'), dict(faculty=self.data['it']['f'].pk, leave_type='Casual', from_date='2026-06-01', to_date='2026-06-02', reason='x'))
        self.assertEqual(LeaveRequest.objects.filter(faculty=self.data['it']['f']).count(), 1)

    def test_hod_own_department_actions_work(self):
        self.login(self.hod_cs)
        l = self.data['cs']['l']
        self.client.post(reverse('leave_action', args=[l.pk, 'approve']))
        l.refresh_from_db(); self.assertEqual(l.status, 'Approved')
        self.assertEqual(self.get('faculty_edit', self.data['cs']['f'].pk).status_code, 200)
        self.assertEqual(self.get('faculty_detail', self.data['cs']['f'].pk).status_code, 200)
        # HOD cannot access admin-only pages
        for name in ['reports', 'user_list', 'user_add']:
            self.assertEqual(self.get(name).status_code, 302, name)
        self.client.post(reverse('faculty_delete', args=[self.data['cs']['f'].pk]))
        self.assertTrue(Faculty.objects.filter(pk=self.data['cs']['f'].pk).exists())
        self.client.post(reverse('subject_delete', args=[self.data['cs']['s'].pk]))
        self.assertTrue(Subject.objects.filter(pk=self.data['cs']['s'].pk).exists())

    def test_hod_cannot_approve_own_leave(self):
        f = Faculty.objects.create(faculty_id='H1', name='HOD Self', gender='Male', email='h@x.com', phone='9999999999', department=self.cs,
                                   designation='HOD', joining_date=date(2019, 1, 1), employment_type='Permanent', user=self.hod_cs)
        l = LeaveRequest.objects.create(faculty=f, leave_type='Sick', from_date=date(2026, 7, 1), to_date=date(2026, 7, 1), reason='self')
        self.login(self.hod_cs)
        self.client.post(reverse('leave_action', args=[l.pk, 'approve']))
        l.refresh_from_db(); self.assertEqual(l.status, 'Pending')

    def test_hod_without_department_sees_nothing(self):
        self.login(self.hod_none)
        for name in ['faculty_list', 'subject_list', 'leave_list', 'performance_list', 'qualification_list', 'allocation_list', 'workload']:
            r = self.get(name); self.assertEqual(r.status_code, 200, name)
            self.assertHides(r, 'Prof CS', 'Prof IT', 'Subject CS', 'Subject IT')
        d = self.get('dashboard')
        self.assertEqual(d.context['total_faculty'], 0); self.assertEqual(d.context['pending_leaves'], 0)
        self.assertEqual(d.context['departments'], 0); self.assertSees(d, 'No department is assigned')

    def test_leave_action_rejects_unknown_action(self):
        self.login(self.admin)
        self.client.post(reverse('leave_action', args=[self.data['cs']['l'].pk, 'whatever']))
        self.data['cs']['l'].refresh_from_db(); self.assertEqual(self.data['cs']['l'].status, 'Pending')

    # ---- FACULTY -------------------------------------------------------
    def test_faculty_sees_only_own_data(self):
        self.login(self.fac_cs_user)
        self.assertSees(self.get('leave_list'), 'reason-cs'); self.assertHides(self.get('leave_list'), 'reason-it')
        self.assertSees(self.get('performance_list'), 'period-cs'); self.assertHides(self.get('performance_list'), 'period-it')
        self.assertSees(self.get('qualification_list'), 'Degree-cs'); self.assertHides(self.get('qualification_list'), 'Degree-it')
        self.assertSees(self.get('allocation_list'), 'Subject CS'); self.assertHides(self.get('allocation_list'), 'Subject IT')
        self.assertSees(self.get('workload'), 'Prof CS'); self.assertHides(self.get('workload'), 'Prof IT')
        d = self.get('dashboard')
        for k, v in dict(total_faculty=1, subjects=1, pending_leaves=1, allocations=1, weekly_hours=25).items():
            self.assertEqual(d.context[k], v, k)
        self.assertHides(d, 'Prof IT', 'period-it')
        self.assertEqual(self.get('faculty_own')['Location'], reverse('faculty_detail', args=[self.data['cs']['f'].pk]))
        self.assertEqual(self.get('faculty_detail', self.data['cs']['f'].pk).status_code, 200)

    def test_faculty_blocked_from_everything_else(self):
        self.login(self.fac_cs_user)
        o = self.data['it']
        self.assertEqual(self.get('faculty_detail', o['f'].pk)['Location'], reverse('dashboard'))
        for name in ['faculty_list', 'faculty_add', 'subject_list', 'subject_add', 'allocation_add', 'qualification_add',
                     'performance_add', 'reports', 'user_list', 'user_add']:
            self.assertEqual(self.get(name).status_code, 302, name)
        for name, obj in [('faculty_edit', self.data['cs']['f']), ('qualification_edit', self.data['cs']['q'])]:
            self.assertEqual(self.get(name, obj.pk).status_code, 302, name)
        for name, obj in [('qualification_delete', self.data['cs']['q']), ('allocation_delete', self.data['cs']['a']),
                          ('performance_delete', self.data['cs']['e']), ('faculty_delete', self.data['cs']['f']), ('subject_delete', self.data['cs']['s'])]:
            self.client.post(reverse(name, args=[obj.pk]))
        c = self.data['cs']
        self.assertTrue(Qualification.objects.filter(pk=c['q'].pk).exists() and SubjectAllocation.objects.filter(pk=c['a'].pk).exists()
                        and PerformanceEvaluation.objects.filter(pk=c['e'].pk).exists() and Faculty.objects.filter(pk=c['f'].pk).exists())
        # cannot approve own leave
        self.client.post(reverse('leave_action', args=[c['l'].pk, 'approve']))
        c['l'].refresh_from_db(); self.assertEqual(c['l'].status, 'Pending')

    def test_faculty_leave_only_for_self(self):
        self.login(self.fac_cs_user)
        r = self.get('leave_add'); self.assertEqual(r.status_code, 200); self.assertHides(r, 'Prof IT')
        self.client.post(reverse('leave_add'), dict(faculty=self.data['it']['f'].pk, leave_type='Casual', from_date='2026-06-01', to_date='2026-06-02', reason='hack'))
        self.assertFalse(LeaveRequest.objects.filter(reason='hack').exists())
        self.client.post(reverse('leave_add'), dict(faculty=self.data['cs']['f'].pk, leave_type='Casual', from_date='2026-06-01', to_date='2026-06-02', reason='mine'))
        self.assertTrue(LeaveRequest.objects.filter(reason='mine', faculty=self.data['cs']['f']).exists())

    def test_unlinked_faculty_sees_nothing(self):
        self.login(self.unlinked)
        for name in ['leave_list', 'performance_list', 'qualification_list', 'allocation_list', 'workload']:
            self.assertHides(self.get(name), 'Prof CS', 'Prof IT', 'reason-cs')
        d = self.get('dashboard'); self.assertEqual(d.context['total_faculty'], 0); self.assertSees(d, 'not linked')
        self.assertEqual(self.get('leave_add')['Location'], reverse('leave_list'))

    # ---- sidebar -------------------------------------------------------
    def test_navigation_per_role(self):
        self.login(self.fac_cs_user); r = self.get('dashboard')
        self.assertHides(r, reverse('subject_list'), reverse('reports'), reverse('user_list'), 'href="/faculty/"'); self.assertSees(r, reverse('faculty_own'))
        self.login(self.hod_cs); r = self.get('dashboard')
        self.assertSees(r, reverse('subject_list'), reverse('faculty_list')); self.assertHides(r, reverse('reports'), reverse('user_list'))
        self.login(self.admin); r = self.get('dashboard')
        self.assertSees(r, reverse('reports'), reverse('user_list'))

    def test_no_action_buttons_for_faculty(self):
        self.login(self.fac_cs_user)
        self.assertHides(self.get('allocation_list'), '/allocations/add/', '/delete/')
        self.assertHides(self.get('qualification_list'), '/edit/', '/delete/', '/qualifications/add/')
        self.assertHides(self.get('performance_list'), '/performance/add/', '/delete/')
        self.assertHides(self.get('faculty_detail', self.data['cs']['f'].pk), '/edit/')

    # ---- protected media -----------------------------------------------
    def test_media_is_protected(self):
        cs_cert = self.data['cs']['q'].certificate.url; it_cert = self.data['it']['q'].certificate.url
        it_photo = self.data['it']['f'].profile_photo.url
        self.client.logout()
        self.assertEqual(self.client.get(cs_cert).status_code, 302)           # anonymous -> login
        self.login(self.fac_cs_user)
        self.assertEqual(b''.join(self.client.get(cs_cert).streaming_content), b'%PDF cert')
        self.assertEqual(self.client.get(it_cert).status_code, 404)
        self.assertEqual(self.client.get(it_photo).status_code, 404)
        self.login(self.hod_cs)
        self.assertEqual(self.client.get(cs_cert).status_code, 200)
        self.assertEqual(self.client.get(it_cert).status_code, 404)
        self.assertEqual(self.client.get('/media/../db.sqlite3').status_code, 404)
        self.login(self.admin)
        self.assertEqual(self.client.get(it_cert).status_code, 200)

    # ---- user management -----------------------------------------------
    def test_admin_creates_scoped_users(self):
        self.login(self.admin)
        base = dict(first_name='A', last_name='B', email='a@b.com', password='Str0ng-Pass#91')
        # HOD requires department
        r = self.client.post(reverse('user_add'), dict(base, username='newhod', role='HOD'))
        self.assertEqual(r.status_code, 200); self.assertFalse(User.objects.filter(username='newhod').exists())
        self.client.post(reverse('user_add'), dict(base, username='newhod', role='HOD', department=self.it.pk))
        self.assertEqual(User.objects.get(username='newhod').userprofile.department, self.it)
        # Faculty requires linked record
        r = self.client.post(reverse('user_add'), dict(base, username='newfac', role='FACULTY'))
        self.assertFalse(User.objects.filter(username='newfac').exists())
        extra = Faculty.objects.create(faculty_id='F-x', name='Extra', gender='Male', email='ex@x.com', phone='9999999999', department=self.cs,
                                       designation='AP', joining_date=date(2021, 1, 1), employment_type='Permanent')
        self.client.post(reverse('user_add'), dict(base, username='newfac', role='FACULTY', faculty=extra.pk))
        extra.refresh_from_db(); self.assertEqual(extra.user.username, 'newfac')
        # new HOD actually scoped; edit keeps password when blank
        self.client.logout(); self.assertTrue(self.client.login(username='newhod', password='Str0ng-Pass#91'))
        self.assertHides(self.get('faculty_list'), 'Prof CS')
        self.login(self.admin)
        u = User.objects.get(username='newhod')
        self.client.post(reverse('user_edit', args=[u.pk]), dict(base, username='newhod', role='HOD', department=self.cs.pk, password=''))
        u.refresh_from_db(); self.assertEqual(u.userprofile.department, self.cs); self.assertTrue(u.check_password('Str0ng-Pass#91'))

    def test_pages_render_for_all_roles(self):
        for user in (self.admin, self.hod_cs, self.fac_cs_user):
            self.login(user)
            for name in ['dashboard', 'qualification_list', 'allocation_list', 'workload', 'leave_list', 'performance_list'] + ([] if user == self.admin else ['leave_add']):
                self.assertEqual(self.get(name).status_code, 200, (user.username, name))

    def test_report_counts_not_multiplied_by_joins(self):
        Subject.objects.create(subject_code='SUB-cs2', subject_name='Another', department=self.cs, semester=2)
        self.login(self.admin)
        rows = {d.code: (d.faculty_count, d.subject_count) for d in self.get('reports').context['department_rows']}
        self.assertEqual(rows['CS'], (1, 2)); self.assertEqual(rows['IT'], (1, 1))

    # ---- login page / HOD creation flow / admin leave button -------------
    def test_login_page_shows_no_credentials(self):
        self.client.logout()
        r = self.client.get('/login/')
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, 'admin123'); self.assertNotContains(r, 'Demo accounts'); self.assertNotContains(r, 'hod123')

    def test_hod_created_from_form_sees_only_chosen_department(self):
        self.login(self.admin)
        base = dict(first_name='H', last_name='O', email='h@o.com', password='Str0ng-Pass#91')
        form_page = self.get('user_add')
        self.assertContains(form_page, 'data-field="department"')
        self.client.post(reverse('user_add'), dict(base, username='cs_head', role='HOD', department=self.cs.pk))
        self.client.logout()
        # sign in through the real login view
        r = self.client.post('/login/', {'username': 'cs_head', 'password': 'Str0ng-Pass#91'})
        self.assertEqual(r.status_code, 302)
        d = self.get('dashboard')
        self.assertContains(d, 'Computer Science'); self.assertNotContains(d, 'Information Tech')
        self.assertEqual((d.context['total_faculty'], d.context['subjects'], d.context['departments']), (1, 1, 1))
        for name, yes, no in [('faculty_list', 'Prof CS', 'Prof IT'), ('subject_list', 'Subject CS', 'Subject IT'),
                              ('leave_list', 'reason-cs', 'reason-it'), ('performance_list', 'period-cs', 'period-it'),
                              ('allocation_list', 'Prof CS', 'Prof IT'), ('workload', 'Prof CS', 'Prof IT'),
                              ('qualification_list', 'Degree-cs', 'Degree-it')]:
            r = self.get(name); self.assertContains(r, yes, msg_prefix=name); self.assertNotContains(r, no, msg_prefix=name)

    def test_admin_has_no_apply_leave(self):
        self.login(self.admin)
        self.assertNotContains(self.get('leave_list'), reverse('leave_add'))
        self.assertEqual(self.get('leave_add')['Location'], reverse('dashboard'))
        for u in (self.hod_cs, self.fac_cs_user):
            self.login(u); self.assertContains(self.get('leave_list'), reverse('leave_add'))

    def test_admin_admin123_can_login(self):
        User.objects.create_user('admin2', password='admin123', is_superuser=True)
        self.client.logout()
        self.assertEqual(self.client.post('/login/', {'username': 'admin2', 'password': 'admin123'}).status_code, 302)
