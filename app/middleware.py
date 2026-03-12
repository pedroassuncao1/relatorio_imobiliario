from django.http import HttpResponseRedirect
from django.conf import settings
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken


class JWTAuthMiddleware:
    """
    Intercepta cada request, lê o cookie JWT e
    autentica o usuário automaticamente.
    """

    # Rotas que NÃO precisam de autenticação
    ROTAS_PUBLICAS = [
        '/login/',
        '/admin/',  # django admin nativo
    ]

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        # Rotas públicas passam direto
        if any(request.path.startswith(rota) for rota in self.ROTAS_PUBLICAS):
            return self.get_response(request)

        # Tenta ler o cookie
        token_raw = request.COOKIES.get(settings.SIMPLE_JWT['AUTH_COOKIE'])

        if not token_raw:
            return HttpResponseRedirect(settings.LOGIN_URL)

        # Valida o token
        try:
            token = AccessToken(token_raw)
            user_id = token['user_id']

            # Importa aqui para evitar import circular
            from app.models import Usuario
            usuario = Usuario.objects.get(id=user_id)

            # Injeta o usuário na request (igual ao Django padrão)
            request.user = usuario

        except (TokenError, InvalidToken):
            # Token expirado ou inválido → volta para login
            response = HttpResponseRedirect(settings.LOGIN_URL)
            response.delete_cookie(settings.SIMPLE_JWT['AUTH_COOKIE'])
            return response

        except Exception:
            return HttpResponseRedirect(settings.LOGIN_URL)

        return self.get_response(request)