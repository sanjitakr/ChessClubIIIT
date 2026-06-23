from django.urls import path
from . import views

urlpatterns = [
    path('admin/', views.newsletter_admin, name='newsletter_admin'),
    path('', views.newsletter_list, name='newsletters'),
    path('<slug:slug>/', views.newsletter_article, name='newsletter_article'),
]
