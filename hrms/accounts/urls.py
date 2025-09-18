from django.urls import path
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from accounts.views import (LoginView, CreateSuperUserView, SignupView, approve_user, reject_user,
                             face_recognition_page, recognize_face, today_attendance, RegisterView, list_attendance,
                             UserViewSet, EmployeeViewSet, HRViewSet, ManagerViewSet, AdminViewSet, CEOViewSet, apply_leave, update_leave_status, leaves_today, list_leaves, create_payroll, update_payroll_status, get_payroll, list_payrolls, list_tasks, get_task, update_task, delete_task, create_task)

urlpatterns = [
    path('signup/', SignupView.as_view(), name='user-signup'),
    path('login/', LoginView.as_view(), name='login'),
    # path('users/', UserListView.as_view(), name='user-list'),

    # path('ceos/', CEOListCreateView.as_view(), name='ceo-list-create'),
    # path('hrs/', HRListCreateView.as_view(), name='hr-list-create'),
    # path('managers/', ManagerListCreateView.as_view(), name='manager-list-create'),
    # path('employees/', EmployeeListCreateView.as_view(), name='employee-list-create'),
    # path('admins/', AdminListCreateView.as_view(), name='employee-list-create'),
    # path('create-superuser/', CreateSuperUserView.as_view(), name='create-superuser'),

    path('approve/', approve_user),
    path('reject/', reject_user),

    # path("attendance/", face_recognition_page, name="face_recognition_page"),
    path("attendance/", recognize_face, name="recognize_face"),
    path("register/", RegisterView.as_view(), name="register"),

    path("token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),

    path("today_attendance/", today_attendance, name="today_attendance"),

    # Employee
    path('users/', UserViewSet.as_view({'get': 'list', 'post': 'create'}), name='employee-list'),
    path('users/<str:email>/', UserViewSet.as_view({'get': 'retrieve', 'put': 'update', 'delete': 'destroy'}), name='users-detail'),

    # Employee
    path('employees/', EmployeeViewSet.as_view({'get': 'list', 'post': 'create'}), name='employee-list'),
    path('employees/<str:email>/', EmployeeViewSet.as_view({'get': 'retrieve', 'put': 'update', 'delete': 'destroy'}), name='employee-detail'),

    # HR
    path('hrs/', HRViewSet.as_view({'get': 'list', 'post': 'create'}), name='hr-list'),
    path('hrs/<str:email>/', HRViewSet.as_view({'get': 'retrieve', 'put': 'update', 'delete': 'destroy'}), name='hr-detail'),

    # Manager
    path('managers/', ManagerViewSet.as_view({'get': 'list', 'post': 'create'}), name='manager-list'),
    path('managers/<str:email>/', ManagerViewSet.as_view({'get': 'retrieve', 'put': 'update', 'delete': 'destroy'}), name='manager-detail'),

    # Admin
    path('admins/', AdminViewSet.as_view({'get': 'list', 'post': 'create'}), name='admin-list'),
    path('admins/<str:email>/', AdminViewSet.as_view({'get': 'retrieve', 'put': 'update', 'delete': 'destroy'}), name='admin-detail'),

    # CEO
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

    path('list_attendance/', list_attendance, name='attendance-list'),

    # List all tasks
    path('list_tasks/', list_tasks, name='list_tasks'),
    path('get_task/<int:task_id>/', get_task, name='get_task'),
    path('create_task/create/', create_task, name='create_task'),
    path('update_task/<int:task_id>/', update_task, name='update_task'),
    path('delete_task/<int:task_id>/', delete_task, name='delete_task'),
]
