from django.shortcuts import render, redirect
from django.contrib import messages
from django.conf import settings
from ..models import Usuario
from .helpers import set_jwt_cookie


def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()
        try:
            usuario = Usuario.objects.get(username=username)
            if not usuario.check_password(password):
                raise ValueError('Senha incorreta')
            if not usuario.is_active:
                raise ValueError('Usuário inativo')
            response = redirect('lista_dashboards')
            set_jwt_cookie(response, usuario)
            return response
        except Exception:
            messages.error(request, 'Usuário ou senha inválidos.')
            return render(request, 'auth/login.html')
    return render(request, 'auth/login.html')


def logout_view(request):
    response = redirect('login')
    response.delete_cookie(settings.SIMPLE_JWT['AUTH_COOKIE'])
    return response