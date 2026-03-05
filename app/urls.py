from django.urls import path
from . import views

urlpatterns = [
    path('upload/', views.upload_planilha, name='upload_planilha'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('limpar/', views.limpar_banco, name='limpar_banco'),
]