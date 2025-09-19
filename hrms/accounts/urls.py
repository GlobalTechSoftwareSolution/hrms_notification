from django.urls import path
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from accounts.views import (
    LoginView, CreateSuperUserView, SignupView, approve_user, reject_user,
    recognize_face, today_attendance, RegisterView, list_attendance,
    UserViewSet, EmployeeViewSet, HRViewSet, ManagerViewSet, AdminViewSet, CEOViewSet,
    apply_leave, update_leave_status, leaves_today, list_leaves,
    create_payroll, update_payroll_status, get_payroll, list_payrolls,
    list_tasks, get_task, update_task, delete_task, create_task,
    list_reports, create_report, update_report, delete_report,
    list_projects, create_project, detail_project, update_project, delete_project,
    list_notices, create_notice, detail_notice, update_notice, delete_notice,
    get_employee_by_email
)

urlpatterns = [
    path('signup/', SignupView.as_view(), name='user-signup'),
    path('login/', LoginView.as_view(), name='login'),
    path('approve/', approve_user),
    path('reject/', reject_user),
    path("token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("recognize_face/", recognize_face, name="recognize_face"),
    path("today_attendance/", today_attendance, name="today_attendance"),
    path('list_attendance/', list_attendance, name='attendance-list'),

    path('users/', UserViewSet.as_view({'get': 'list', 'post': 'create'}), name='employee-list'),
    path('users/<str:email>/', UserViewSet.as_view({'get': 'retrieve', 'put': 'update', 'delete': 'destroy'}), name='users-detail'),

    path('employees/', EmployeeViewSet.as_view({'get': 'list', 'post': 'create'}), name='employee-list'),
    path('employees/<str:email>/', EmployeeViewSet.as_view({'get': 'retrieve', 'put': 'update', 'delete': 'destroy'}), name='employee-detail'),

    path('hrs/', HRViewSet.as_view({'get': 'list', 'post': 'create'}), name='hr-list'),
    path('hrs/<str:email>/', HRViewSet.as_view({'get': 'retrieve', 'put': 'update', 'delete': 'destroy'}), name='hr-detail'),

    path('managers/', ManagerViewSet.as_view({'get': 'list', 'post': 'create'}), name='manager-list'),
    path('managers/<str:email>/', ManagerViewSet.as_view({'get': 'retrieve', 'put': 'update', 'delete': 'destroy'}), name='manager-detail'),

    path('admins/', AdminViewSet.as_view({'get': 'list', 'post': 'create'}), name='admin-list'),
    path('admins/<str:email>/', AdminViewSet.as_view({'get': 'retrieve', 'put': 'update', 'delete': 'destroy'}), name='admin-detail'),

    path('ceos/', CEOViewSet.as_view({'get': 'list', 'post': 'create'}), name='ceo-list'),
    path('ceos/<str:email>/', CEOViewSet.as_view({'get': 'retrieve', 'put': 'update', 'delete': 'destroy'}), name='ceo-detail'),

    path('apply_leave/', apply_leave, name='apply_leave'),
    path('update_leave/<path:email>/', update_leave_status, name='update_leave_status'),
    path('leaves_today/', leaves_today, name='leaves_today'),
    path('list_leaves/', list_leaves, name='list_leaves'),

    path('create_payroll/', create_payroll, name='create_payroll'),
    path('update_payroll/<path:email>/', update_payroll_status, name='update_payroll_status'),
    path('get_payroll/<path:email>/', get_payroll, name='get_payroll'),
    path('list_payrolls/', list_payrolls, name='list_payrolls'),

    path('list_tasks/', list_tasks, name='list_tasks'),
    path('get_task/<int:task_id>/', get_task, name='get_task'),
    path('create_task/', create_task, name='create_task'),
    path('update_task/<int:task_id>/', update_task, name='update_task'),
    path('delete_task/<int:task_id>/', delete_task, name='delete_task'),
    
    path('list_reports/', list_reports, name='list_reports'),
    path('create_report/', create_report, name='create_report'),
    path('update_report/<int:pk>/', update_report, name='update_report'),
    path('delete_report/<int:pk>/', delete_report, name='delete_report'),
    
    path('list_projects/', list_projects, name='list_projects'),
    path('create_project/', create_project, name='create_project'),
    path('project/<int:pk>/', detail_project, name='detail_project'),
    path('update_project/<int:pk>/', update_project, name='update_project'),
    path('delete_project/<int:pk>/', delete_project, name='delete_project'),

    path('list_notices/', list_notices, name='list_notices'),
    path('create_notice/', create_notice, name='create_notice'),
    path('notice/<int:pk>/', detail_notice, name='detail_notice'),
    path('update_notice/<int:pk>/', update_notice, name='update_notice'),
    path('delete_notice/<int:pk>/', delete_notice, name='delete_notice'),
    
    path('api/accounts/employees/<str:email>/', get_employee_by_email, name='get_employee_by_email'),
]