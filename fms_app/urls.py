from django.urls import path
from django.contrib.auth import views as auth_views

from . import views


urlpatterns = [

    
    path(
        'login/',
        auth_views.LoginView.as_view(
            template_name='registration/login.html'
        ),
        name='login'
    ),

    path(
        'logout/',
        auth_views.LogoutView.as_view(),
        name='logout'
    ),

   

    path(
        '',
        views.dashboard,
        name='dashboard'
    ),

   

    path('users/', views.user_list, name='user_list'),
    path('users/<int:pk>/edit/', views.user_edit, name='user_edit'),
    path('media/<path:path>', views.protected_media, name='protected_media'),

    path(
        'users/add/',
        views.user_add,
        name='user_add'
    ),

   

    path(
        'faculty/',
        views.faculty_list,
        name='faculty_list'
    ),

    path(
        'faculty/add/',
        views.faculty_add,
        name='faculty_add'
    ),

    path('faculty/me/', views.faculty_own, name='faculty_own'),

    path(
        'faculty/<int:pk>/',
        views.faculty_detail,
        name='faculty_detail'
    ),

    path(
        'faculty/<int:pk>/edit/',
        views.faculty_edit,
        name='faculty_edit'
    ),

    path(
        'faculty/<int:pk>/delete/',
        views.faculty_delete,
        name='faculty_delete'
    ),

   

    path(
        'qualifications/',
        views.qualification_list,
        name='qualification_list'
    ),

    path(
        'qualifications/add/',
        views.qualification_add,
        name='qualification_add'
    ),

    path(
        'qualifications/<int:pk>/edit/',
        views.qualification_edit,
        name='qualification_edit'
    ),

    path(
        'qualifications/<int:pk>/delete/',
        views.qualification_delete,
        name='qualification_delete'
    ),

    

    path(
        'subjects/',
        views.subject_list,
        name='subject_list'
    ),

    path(
        'subjects/add/',
        views.subject_add,
        name='subject_add'
    ),

    path(
        'subjects/<int:pk>/edit/',
        views.subject_edit,
        name='subject_edit'
    ),

    path(
        'subjects/<int:pk>/delete/',
        views.subject_delete,
        name='subject_delete'
    ),

   

    path(
        'allocations/',
        views.allocation_list,
        name='allocation_list'
    ),

    path(
        'allocations/add/',
        views.allocation_add,
        name='allocation_add'
    ),

    path(
        'allocations/<int:pk>/delete/',
        views.allocation_delete,
        name='allocation_delete'
    ),

   

    path(
        'workload/',
        views.workload,
        name='workload'
    ),

  
    path(
        'leave/',
        views.leave_list,
        name='leave_list'
    ),

    path(
        'leave/apply/',
        views.leave_add,
        name='leave_add'
    ),

    path(
        'leave/<int:pk>/<str:action>/',
        views.leave_action,
        name='leave_action'
    ),

  

    path(
        'performance/',
        views.performance_list,
        name='performance_list'
    ),

    path(
        'performance/add/',
        views.performance_add,
        name='performance_add'
    ),

    path(
        'performance/<int:pk>/delete/',
        views.performance_delete,
        name='performance_delete'
    ),

   

    path(
        'reports/',
        views.reports,
        name='reports'
    ),
]
