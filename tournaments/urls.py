from django.urls import path
from . import views, staff_views

urlpatterns = [
    path('register/<int:tournament_id>/', views.toggle_registration, name='toggle_registration'),
    path('guest-register/<int:tournament_id>/', views.guest_register, name='guest_register'),
    path('extend-register/<int:tournament_id>/', views.extend_registration, name='extend_registration'),
    path('time-control/<int:tournament_id>/', views.update_time_control, name='update_time_control'),
    path('generate/<int:tournament_id>/', views.generate_matches, name='generate_matches'),
    path('round/<int:tournament_id>/', views.generate_next_round, name='generate_next_round'),
    path('result/<int:match_id>/', views.report_result, name='report_result'),
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('api/<int:tournament_id>/standings/', views.tournament_standings_api, name='tournament_standings_api'),
    path('staff/login/', staff_views.staff_login, name='staff_login'),
    path('staff/logout/', staff_views.staff_logout, name='staff_logout'),
    path('staff/', staff_views.staff_portal, name='staff_portal'),
    path('staff/result/<int:match_id>/', staff_views.staff_record_result, name='staff_record_result'),
    path('staff/end-tournament/<int:tournament_id>/', staff_views.staff_end_tournament, name='staff_end_tournament'),
    path('staff/role/', staff_views.staff_set_role, name='staff_set_role'),
    path('staff/disable-user/<int:user_id>/', staff_views.staff_disable_user, name='staff_disable_user'),
    path('<int:tournament_id>/', views.tournament_detail, name='tournament_detail'),
    path('match/<int:match_id>/schedule/', views.schedule_match, name='schedule_match'),
    path('', views.tournaments, name='tournaments'),
]
