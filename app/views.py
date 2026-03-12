from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Avg, Sum
from django.conf import settings
from django.http import HttpResponse

from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError

from .models import Usuario, Dashboard, AcessoDashboard, Empreendimento
from .utils import mapear_colunas_com_ia, limpar_valor, buscar_coordenadas, analisar_dados_com_gemini

import pandas as pd


# ==============================
# HELPERS
# ==============================

def set_jwt_cookie(response, usuario):
    """Gera tokens JWT e salva no cookie HttpOnly."""
    refresh = RefreshToken.for_user(usuario)
    access  = str(refresh.access_token)

    response.set_cookie(
        key      = settings.SIMPLE_JWT['AUTH_COOKIE'],
        value    = access,
        httponly = settings.SIMPLE_JWT['AUTH_COOKIE_HTTPONLY'],
        secure   = settings.SIMPLE_JWT['AUTH_COOKIE_SECURE'],
        samesite = settings.SIMPLE_JWT['AUTH_COOKIE_SAMESITE'],
        max_age  = int(settings.SIMPLE_JWT['ACCESS_TOKEN_LIFETIME'].total_seconds()),
    )
    return response


def admin_required(view_func):
    """Decorator: bloqueia viewers de acessar rotas admin."""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_admin():
            messages.error(request, 'Acesso restrito a administradores.')
            return redirect('lista_dashboards')
        return view_func(request, *args, **kwargs)
    return wrapper


# ==============================
# AUTH
# ==============================

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

            # Login OK → gera cookie JWT
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


# ==============================
# LISTA DE DASHBOARDS
# ==============================

def lista_dashboards(request):
    if request.user.is_admin():
        # Admin vê todos
        dashboards = Dashboard.objects.all().order_by('-criado_em')
    else:
        # Viewer vê só os liberados
        ids_liberados = AcessoDashboard.objects.filter(
            usuario=request.user
        ).values_list('dashboard_id', flat=True)
        dashboards = Dashboard.objects.filter(id__in=ids_liberados).order_by('-criado_em')

    return render(request, 'app/lista_dashboards.html', {
        'dashboards': dashboards,
        'usuario': request.user,
    })


# ==============================
# DASHBOARD (BI)
# ==============================

def dashboard(request, dashboard_id):
    dash = get_object_or_404(Dashboard, id=dashboard_id)

    # Viewer só acessa se tiver permissão
    if not request.user.is_admin():
        tem_acesso = AcessoDashboard.objects.filter(
            usuario=request.user,
            dashboard=dash
        ).exists()
        if not tem_acesso:
            messages.error(request, 'Você não tem acesso a este dashboard.')
            return redirect('lista_dashboards')

    # Filtra empreendimentos deste dashboard
    dados_queryset = Empreendimento.objects.filter(dashboard=dash).order_by('-data_importacao')

    # --- FILTROS ---
    if request.GET.get('quartos'):
        dados_queryset = dados_queryset.filter(quartos=request.GET.get('quartos'))
    if request.GET.get('construtora'):
        dados_queryset = dados_queryset.filter(construtora=request.GET.get('construtora'))
    if request.GET.get('bairro'):
        dados_queryset = dados_queryset.filter(bairro=request.GET.get('bairro'))
    if request.GET.get('fase'):
        dados_queryset = dados_queryset.filter(fase_obra=request.GET.get('fase'))
    if request.GET.get('data_inicio') and request.GET.get('data_fim'):
        dados_queryset = dados_queryset.filter(
            data_entrega__range=[request.GET.get('data_inicio'), request.GET.get('data_fim')]
        )
    if request.GET.get('pm2_min'):
        dados_queryset = dados_queryset.filter(preco_medio_m2__gte=request.GET.get('pm2_min'))
    if request.GET.get('pm2_max'):
        dados_queryset = dados_queryset.filter(preco_medio_m2__lte=request.GET.get('pm2_max'))
    if request.GET.get('area_min'):
        dados_queryset = dados_queryset.filter(area_unidade__gte=request.GET.get('area_min'))
    if request.GET.get('area_max'):
        dados_queryset = dados_queryset.filter(area_unidade__lte=request.GET.get('area_max'))
    if request.GET.get('preco_min'):
        dados_queryset = dados_queryset.filter(preco_unidade__gte=request.GET.get('preco_min'))
    if request.GET.get('preco_max'):
        dados_queryset = dados_queryset.filter(preco_unidade__lte=request.GET.get('preco_max'))

    # --- KPIs ---
    stats = dados_queryset.aggregate(
        total_u=Sum('unidades_totais'),
        total_e=Sum('estoque'),
        total_v=Sum('unidades_vendidas'),
        avg_area=Avg('area_unidade'),
        avg_m2=Avg('preco_medio_m2')
    )

    total_unidades     = stats['total_u'] or 0
    total_estoque      = stats['total_e'] or 0
    total_vendidas     = stats['total_v'] or 0
    media_area         = stats['avg_area'] or 0
    media_m2           = stats['avg_m2'] or 0
    num_empreendimentos = dados_queryset.values('nome').distinct().count()

    # --- FILTROS DOS SELECTS ---
    todos = Empreendimento.objects.filter(dashboard=dash)
    bairros       = sorted(todos.values_list('bairro', flat=True).distinct())
    construtoras  = sorted(todos.values_list('construtora', flat=True).distinct().exclude(construtora__isnull=True))
    fases_lista   = sorted(todos.values_list('fase_obra', flat=True).distinct().exclude(fase_obra__isnull=True))
    quartos_lista = sorted(todos.values_list('quartos', flat=True).distinct().exclude(quartos__isnull=True))

    contagem_fases = [dados_queryset.filter(fase_obra=f).count() for f in fases_lista]

    return render(request, 'app/dashboard.html', {
        'dash': dash,
        'dados': dados_queryset,
        'total_unidades': total_unidades,
        'total_estoque': total_estoque,
        'total_vendidas': total_vendidas,
        'media_area': media_area,
        'media_m2': media_m2,
        'num_empreendimentos': num_empreendimentos,
        'lista_bairros': bairros,
        'lista_construtoras': construtoras,
        'lista_fases': fases_lista,
        'lista_contagem_fases': contagem_fases,
        'lista_quartos': quartos_lista,
        'usuario': request.user,
    })


# ==============================
# UPLOAD (só admin)
# ==============================

def tratar_quartos(valor):
    if pd.isna(valor) or valor == "":
        return 0
    val_str = str(valor).upper().strip()
    if "STUDIO" in val_str or "LOFT" in val_str:
        return 1
    try:
        import re
        numeros = re.findall(r'\d+', val_str)
        return int(numeros[0]) if numeros else 0
    except:
        return 0
    
def tratar_inteiro(valor):
    """Converte para int com segurança, retorna 0 se não conseguir."""
    if pd.isna(valor) or valor == "" or valor is None:
        return 0
    val_str = str(valor).strip().upper()
    if val_str in ('NI', 'N/I', 'N/A', 'NA', '-', '--', 'ND'):
        return 0
    try:
        return int(float(val_str))
    except:
        return 0


@admin_required
def upload_planilha(request):
    if request.method == 'POST' and request.FILES.get('planilha'):
        arquivo   = request.FILES['planilha']
        nome_dash = request.POST.get('nome_dashboard', arquivo.name)
        cidade_padrao = request.POST.get('cidade', '').strip()
        estado_padrao = request.POST.get('estado', '').strip().upper()

        # Cria o Dashboard
        dash = Dashboard.objects.create(
            nome       = nome_dash,
            criado_por = request.user
        )

        df = pd.read_excel(arquivo) if arquivo.name.endswith('.xlsx') else pd.read_csv(arquivo)
        mapeamento = mapear_colunas_com_ia(df.columns.tolist())

        objetos = []
        for _, row in df.iterrows():
            nome_val = row.get(mapeamento.get('nome'))
            if not nome_val:
                continue

            data_raw   = row.get(mapeamento.get('data_entrega'))
            data_final = None
            if pd.notna(data_raw):
                try:
                    data_final = pd.to_datetime(data_raw).date()
                except:
                    data_final = None

            rua    = str(row.get(mapeamento.get('endereco'), ''))
            bairro = str(row.get(mapeamento.get('bairro'), ''))

            # ← usa cidade/estado do formulário se a planilha não tiver
            cidade_planilha = str(row.get(mapeamento.get('cidade'), '') or '').strip()
            cidade = cidade_planilha if cidade_planilha else cidade_padrao

            # monta string completa para o geocoder: "Recife, PE, Brasil"
            cidade_geo = f"{cidade}, {estado_padrao}, Brasil"

            lat, lon = buscar_coordenadas(rua, bairro, cidade_geo)

            obj = Empreendimento(
                dashboard         = dash,
                nome              = nome_val,
                categoria         = str(row.get(mapeamento.get('categoria'), 'VA'))[:20],
                construtora       = row.get(mapeamento.get('construtora')),
                endereco          = rua,
                bairro            = bairro,
                cidade            = cidade,
                data_entrega      = data_final,
                unidades_totais   = tratar_inteiro(row.get(mapeamento.get('unidades_totais'), 0)),
                unidades_vendidas = tratar_inteiro(row.get(mapeamento.get('unidades_vendidas'), 0)),
                preco_medio_m2    = limpar_valor(row.get(mapeamento.get('preco_m2'))),
                preco_unidade     = limpar_valor(row.get(mapeamento.get('preco_unidade'))),
                area_unidade      = limpar_valor(row.get(mapeamento.get('area_unidade'))),
                estoque           = tratar_inteiro(row.get(mapeamento.get('estoque'), 0)),
                quartos           = tratar_quartos(row.get(mapeamento.get('quartos'))),
                vagas_garagem     = row.get(mapeamento.get('vagas_garagem')),
                fase_obra         = row.get(mapeamento.get('fase_obra')),
                latitude          = lat,
                longitude         = lon,
            )
            objetos.append(obj)

        if objetos:
            Empreendimento.objects.bulk_create(objetos)

        return redirect('lista_dashboards')

    return render(request, 'app/upload.html', {'usuario': request.user})


# ==============================
# GERENCIAR USUÁRIOS (só admin)
# ==============================

@admin_required
def gerenciar_usuarios(request):
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'criar':
            username = request.POST.get('username', '').strip()
            password = request.POST.get('password', '').strip()
            role     = request.POST.get('role', 'viewer')

            if Usuario.objects.filter(username=username).exists():
                messages.error(request, f'Usuário "{username}" já existe.')
            else:
                u = Usuario.objects.create_user(
                    username=username,
                    password=password,
                    role=role
                )
                messages.success(request, f'Usuário "{u.username}" criado com sucesso.')

        elif action == 'deletar':
            uid = request.POST.get('usuario_id')
            try:
                u = Usuario.objects.get(id=uid)
                if u == request.user:
                    messages.error(request, 'Você não pode deletar a si mesmo.')
                else:
                    u.delete()
                    messages.success(request, f'Usuário removido.')
            except Usuario.DoesNotExist:
                messages.error(request, 'Usuário não encontrado.')

        return redirect('gerenciar_usuarios')

    usuarios = Usuario.objects.all().order_by('username')
    return render(request, 'app/gerenciar_usuarios.html', {
        'usuarios': usuarios,
        'usuario': request.user,
    })


# ==============================
# GERENCIAR ACESSOS (só admin)
# ==============================

@admin_required
def gerenciar_acessos(request):
    if request.method == 'POST':
        usuario_id   = request.POST.get('usuario_id')
        dashboard_ids = request.POST.getlist('dashboards')  # lista de IDs

        try:
            usuario_alvo = Usuario.objects.get(id=usuario_id)

            # Remove todos os acessos antigos e recria
            AcessoDashboard.objects.filter(usuario=usuario_alvo).delete()
            for did in dashboard_ids:
                AcessoDashboard.objects.create(
                    usuario   = usuario_alvo,
                    dashboard = Dashboard.objects.get(id=did)
                )
            messages.success(request, f'Acessos de "{usuario_alvo.username}" atualizados.')

        except Exception as e:
            messages.error(request, f'Erro: {e}')

        return redirect('gerenciar_acessos')

    usuarios   = Usuario.objects.filter(role='viewer').order_by('username')
    dashboards = Dashboard.objects.all().order_by('-criado_em')

    # Monta lista de dicts ao invés de dict com chave int
    usuarios_com_acessos = []
    for u in usuarios:
        ids_liberados = list(
            AcessoDashboard.objects.filter(usuario=u).values_list('dashboard_id', flat=True)
        )
        usuarios_com_acessos.append({
            'usuario': u,
            'ids_liberados': ids_liberados,
        })

    return render(request, 'app/gerenciar_acessos.html', {
        'usuarios_com_acessos': usuarios_com_acessos,
        'dashboards'          : dashboards,
        'usuario'             : request.user,
    })


# ==============================
# DELETAR DASHBOARD (só admin)
# ==============================

@admin_required
def deletar_dashboard(request, dashboard_id):
    if request.method == 'POST':
        dash = get_object_or_404(Dashboard, id=dashboard_id)
        nome = dash.nome
        dash.delete()
        messages.success(request, f'Dashboard "{nome}" removido.')
    return redirect('lista_dashboards')