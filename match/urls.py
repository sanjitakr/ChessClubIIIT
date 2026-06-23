from django.urls import path
from . import views

urlpatterns = [

    path('lobby/', views.lobby_view, name='match_lobby'),
    path('<int:match_id>/', views.match_view, name='match_view'),

    path('api/create/', views.create_match, name='create_match'),
    path('api/<int:match_id>/join/', views.join_match, name='join_match'),
    path('api/<int:match_id>/leave/', views.leave_match, name='leave_match'),
    path('api/<int:match_id>/state/', views.match_state, name='match_state'),
    path('api/lobby/data/', views.lobby_data, name='lobby_data'),

    path('api/queue/join/', views.queue_join, name='queue_join'),
    path('api/queue/leave/', views.queue_leave, name='queue_leave'),
    path('api/queue/status/', views.queue_status, name='queue_status'),
    path('api/<int:match_id>/analyze/', views.analyze_match, name='analyze_match'),
    path('api/<int:match_id>/pgn/', views.match_pgn, name='match_pgn'),
    path('api/evaluate/', views.evaluate_position_api, name='evaluate_position'),
    path('api/challenge/<str:username>/', views.send_challenge, name='send_challenge'),
    path('api/challenge/<int:challenge_id>/accept/', views.accept_challenge, name='accept_challenge'),
    path('api/challenge/<int:challenge_id>/decline/', views.decline_challenge, name='decline_challenge'),
    path('api/challenge/<int:challenge_id>/cancel/', views.cancel_challenge, name='cancel_challenge'),
    path('api/challenges/status/', views.challenge_status, name='challenge_status'),
    path('api/challenges/', views.list_challenges, name='list_challenges'),
]