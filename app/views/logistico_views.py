"""
app/views/logistico_views.py

Views para o dashboard logístico.
Telas: mapa_kpis, abl_estoque, precos, distancias, share_logistico
"""

import json
from django.shortcuts import render, get_object_or_404
from django.db.models import Sum, Avg, Count, F, Q
from django.contrib.auth.decorators import login_required

from app.models import Dashboard, EmpreendimentoLogistico, AcessoDashboard
from app.views.helpers import set_jwt_cookie


def _check_acesso(request, dash):
    """Retorna True se o usuário tem acesso ao dashboard."""
    usuario = request.user
    if usuario.role == 'admin':
        return True
    return AcessoDashboard.objects.filter(usuario=usuario, dashboard=dash).exists()


def _get_raizes(dash, request):
    """Retorna queryset dos empreendimentos-raiz com filtros da sidebar."""
    qs = EmpreendimentoLogistico.objects.filter(
        dashboard=dash,
        empreendimento_principal__isnull=True,
    )

    # Filtros multiselect
    cidades = request.GET.getlist('cidade')
    construtoras = request.GET.getlist('construtora')
    fases = request.GET.getlist('fase')

    if cidades:
        qs = qs.filter(cidade__in=cidades)
    if construtoras:
        qs = qs.filter(construtora__in=construtoras)
    if fases:
        qs = qs.filter(fase_obra__in=fases)

    # Filtros de range
    abl_min = request.GET.get('abl_min')
    abl_max = request.GET.get('abl_max')
    vac_min = request.GET.get('vac_min')
    vac_max = request.GET.get('vac_max')

    if abl_min:
        qs = qs.filter(abl_m2__gte=float(abl_min))
    if abl_max:
        qs = qs.filter(abl_m2__lte=float(abl_max))
    if vac_min:
        qs = qs.filter(vacancia__gte=float(vac_min) / 100)
    if vac_max:
        qs = qs.filter(vacancia__lte=float(vac_max) / 100)

    return qs


def _get_listas_sidebar(dash):
    """Retorna listas de opções para os filtros da sidebar."""
    base = EmpreendimentoLogistico.objects.filter(
        dashboard=dash,
        empreendimento_principal__isnull=True,
    )
    cidades = sorted(base.exclude(cidade__isnull=True).values_list('cidade', flat=True).distinct())
    construtoras = sorted(base.exclude(construtora__isnull=True).values_list('construtora', flat=True).distinct())
    fases = sorted(base.exclude(fase_obra__isnull=True).values_list('fase_obra', flat=True).distinct())
    return cidades, construtoras, fases


def _kpis_raizes(qs):
    """Calcula KPIs agregados a partir dos empreendimentos-raiz."""
    agg = qs.aggregate(
        total_modulos=Sum('num_modulos'),
        total_ocupados=Sum('modulos_ocupados'),
        total_disponiveis=Sum('modulos_disponiveis'),
        total_abl=Sum('abl_m2'),
        avg_vac=Avg('vacancia'),
        avg_m2_loc=Avg('preco_m2_locacao'),
        avg_m2_cnd=Avg('preco_m2_condominio'),
        num_emp=Count('id'),
    )
    total_mod = agg['total_modulos'] or 0
    total_ocu = agg['total_ocupados'] or 0
    pct_vac = round((1 - total_ocu / total_mod) * 100, 1) if total_mod > 0 else 0
    return {
        'total_modulos':     total_mod,
        'modulos_ocupados':  total_ocu,
        'modulos_disponiveis': agg['total_disponiveis'] or 0,
        'total_abl':         round(agg['total_abl'] or 0, 0),
        'pct_vacancia':      pct_vac,
        'avg_m2_locacao':    round(float(agg['avg_m2_loc'] or 0), 2),
        'avg_m2_condominio': round(float(agg['avg_m2_cnd'] or 0), 2),
        'num_empreendimentos': agg['num_emp'] or 0,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 1. MAPA & KPIs
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def dashboard_logistico(request, dash_id):
    dash = get_object_or_404(Dashboard, id=dash_id, tipo='logistico')
    if not _check_acesso(request, dash):
        return render(request, 'app/sem_acesso.html')

    cidades, construtoras, fases = _get_listas_sidebar(dash)
    qs = _get_raizes(dash, request)
    kpis = _kpis_raizes(qs)

    # Dados do mapa
    dados_mapa = []
    for emp in qs.filter(latitude__isnull=False, longitude__isnull=False):
        dados_mapa.append({
            'id': emp.id,
            'nome': emp.nome,
            'cidade': emp.cidade or '',
            'construtora': emp.construtora or '',
            'fase': emp.fase_obra or '',
            'lat': emp.latitude,
            'lng': emp.longitude,
            'abl': emp.abl_m2 or 0,
            'num_modulos': emp.num_modulos or 0,
            'modulos_ocupados': emp.modulos_ocupados or 0,
            'modulos_disponiveis': emp.modulos_disponiveis or 0,
            'pct_vacancia': emp.pct_vacancia() or 0,
            'preco_m2_locacao': float(emp.preco_m2_locacao or 0),
            'distancia_km': emp.distancia_ref_km,
        })

    ctx = {
        'dash': dash,
        'usuario': request.user,
        'lista_cidades': cidades,
        'lista_construtoras': construtoras,
        'lista_fases': fases,
        'kpis': kpis,
        'dados_mapa_json': json.dumps(dados_mapa),
        'ref_lat': dash.ref_latitude,
        'ref_lon': dash.ref_longitude,
        'ref_nome': dash.ref_nome or 'Ponto de Referência',
        'aba_atual': 'dashboard',
    }
    response = render(request, 'app/logistico/dashboard.html', ctx)
    return set_jwt_cookie(response, request)


# ─────────────────────────────────────────────────────────────────────────────
# 2. ABL & ESTOQUE
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def abl_estoque(request, dash_id):
    dash = get_object_or_404(Dashboard, id=dash_id, tipo='logistico')
    if not _check_acesso(request, dash):
        return render(request, 'app/sem_acesso.html')

    cidades, construtoras, fases = _get_listas_sidebar(dash)
    qs = _get_raizes(dash, request)
    kpis = _kpis_raizes(qs)

    # Dados por empreendimento para gráfico ABL x Módulos
    dados_abl = []
    for emp in qs.order_by('-abl_m2'):
        dados_abl.append({
            'nome': emp.nome,
            'abl': emp.abl_m2 or 0,
            'ocupados': emp.modulos_ocupados or 0,
            'disponiveis': emp.modulos_disponiveis or 0,
            'total_modulos': emp.num_modulos or 0,
            'pct_vacancia': emp.pct_vacancia() or 0,
        })

    # Dados por cidade
    por_cidade = qs.values('cidade').annotate(
        total_abl=Sum('abl_m2'),
        total_modulos=Sum('num_modulos'),
        total_ocupados=Sum('modulos_ocupados'),
        total_disponiveis=Sum('modulos_disponiveis'),
    ).order_by('-total_abl')

    ctx = {
        'dash': dash,
        'usuario': request.user,
        'lista_cidades': cidades,
        'lista_construtoras': construtoras,
        'lista_fases': fases,
        'kpis': kpis,
        'dados_abl_json': json.dumps(dados_abl),
        'por_cidade_json': json.dumps(list(por_cidade)),
        'empreendimentos': qs.order_by('-abl_m2'),
        'aba_atual': 'abl',
    }
    response = render(request, 'app/logistico/abl_estoque.html', ctx)
    return set_jwt_cookie(response, request)


# ─────────────────────────────────────────────────────────────────────────────
# 3. PREÇOS
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def precos(request, dash_id):
    dash = get_object_or_404(Dashboard, id=dash_id, tipo='logistico')
    if not _check_acesso(request, dash):
        return render(request, 'app/sem_acesso.html')

    cidades, construtoras, fases = _get_listas_sidebar(dash)
    qs = _get_raizes(dash, request)
    kpis = _kpis_raizes(qs)

    # Dados para gráficos de preço
    dados_precos = []
    for emp in qs.exclude(preco_m2_locacao__isnull=True).order_by('-preco_m2_locacao'):
        dados_precos.append({
            'nome': emp.nome,
            'cidade': emp.cidade or '',
            'pm2_locacao': float(emp.preco_m2_locacao or 0),
            'pm2_condominio': float(emp.preco_m2_condominio or 0),
            'pm2_iptu': float(emp.preco_m2_iptu or 0),
            'pm2_total': round(
                float(emp.preco_m2_locacao or 0) +
                float(emp.preco_m2_condominio or 0) +
                float(emp.preco_m2_iptu or 0), 2
            ),
        })

    # Tipologias — tabela detalhada com todas as tipologias
    todas_tipologias = EmpreendimentoLogistico.objects.filter(
        dashboard=dash,
        empreendimento_principal__in=qs,
    ).select_related('empreendimento_principal').order_by(
        'empreendimento_principal__numero', 'area_modulo_m2'
    )

    # Tabela hierárquica empreendimento → tipologias
    tabela = []
    for emp in qs.order_by('numero'):
        tips = todas_tipologias.filter(empreendimento_principal=emp)
        tabela.append({
            'emp': emp,
            'tipologias': tips,
        })

    ctx = {
        'dash': dash,
        'usuario': request.user,
        'lista_cidades': cidades,
        'lista_construtoras': construtoras,
        'lista_fases': fases,
        'kpis': kpis,
        'dados_precos_json': json.dumps(dados_precos),
        'tabela': tabela,
        'aba_atual': 'precos',
    }
    response = render(request, 'app/logistico/precos.html', ctx)
    return set_jwt_cookie(response, request)


# ─────────────────────────────────────────────────────────────────────────────
# 4. DISTÂNCIAS
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def distancias(request, dash_id):
    dash = get_object_or_404(Dashboard, id=dash_id, tipo='logistico')
    if not _check_acesso(request, dash):
        return render(request, 'app/sem_acesso.html')

    cidades, construtoras, fases = _get_listas_sidebar(dash)
    qs = _get_raizes(dash, request)
    kpis = _kpis_raizes(qs)

    # Ordenados por distância
    emps_dist = qs.exclude(distancia_ref_km__isnull=True).order_by('distancia_ref_km')
    sem_dist  = qs.filter(distancia_ref_km__isnull=True)

    dados_dist = []
    for emp in emps_dist:
        dados_dist.append({
            'nome': emp.nome,
            'cidade': emp.cidade or '',
            'distancia_km': emp.distancia_ref_km,
            'abl': emp.abl_m2 or 0,
            'pct_vacancia': emp.pct_vacancia() or 0,
            'pm2_locacao': float(emp.preco_m2_locacao or 0),
        })

    ctx = {
        'dash': dash,
        'usuario': request.user,
        'lista_cidades': cidades,
        'lista_construtoras': construtoras,
        'lista_fases': fases,
        'kpis': kpis,
        'dados_dist_json': json.dumps(dados_dist),
        'emps_dist': emps_dist,
        'sem_dist': sem_dist,
        'ref_nome': dash.ref_nome or 'Ponto de Referência',
        'ref_lat': dash.ref_latitude,
        'ref_lon': dash.ref_longitude,
        'aba_atual': 'distancias',
    }
    response = render(request, 'app/logistico/distancias.html', ctx)
    return set_jwt_cookie(response, request)


# ─────────────────────────────────────────────────────────────────────────────
# 5. SHARE / PARTICIPAÇÃO
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def share_logistico(request, dash_id):
    dash = get_object_or_404(Dashboard, id=dash_id, tipo='logistico')
    if not _check_acesso(request, dash):
        return render(request, 'app/sem_acesso.html')

    cidades, construtoras, fases = _get_listas_sidebar(dash)
    qs = _get_raizes(dash, request)
    kpis = _kpis_raizes(qs)

    total_abl = qs.aggregate(t=Sum('abl_m2'))['t'] or 1
    total_mod = qs.aggregate(t=Sum('num_modulos'))['t'] or 1

    # Share por empresa (construtora)
    por_empresa = (
        qs.values('construtora')
        .annotate(
            abl=Sum('abl_m2'),
            modulos=Sum('num_modulos'),
            ocupados=Sum('modulos_ocupados'),
            num_emp=Count('id'),
        )
        .order_by('-abl')
    )
    share_empresas = []
    for row in por_empresa:
        construtora = row['construtora'] or 'Não informado'
        abl = row['abl'] or 0
        mod = row['modulos'] or 0
        ocu = row['ocupados'] or 0
        share_empresas.append({
            'construtora': construtora,
            'abl': round(abl, 0),
            'pct_abl': round(abl / total_abl * 100, 1),
            'modulos': mod,
            'pct_modulos': round(mod / total_mod * 100, 1),
            'ocupados': ocu,
            'pct_vacancia': round((1 - ocu / mod) * 100, 1) if mod > 0 else 0,
            'num_emp': row['num_emp'],
        })

    # Share por empreendimento
    share_emps = []
    for emp in qs.order_by('-abl_m2'):
        abl = emp.abl_m2 or 0
        mod = emp.num_modulos or 0
        ocu = emp.modulos_ocupados or 0
        share_emps.append({
            'nome': emp.nome,
            'construtora': emp.construtora or '',
            'cidade': emp.cidade or '',
            'abl': round(abl, 0),
            'pct_abl': round(abl / total_abl * 100, 1),
            'modulos': mod,
            'pct_modulos': round(mod / total_mod * 100, 1),
            'ocupados': ocu,
            'pct_vacancia': emp.pct_vacancia() or 0,
        })

    ctx = {
        'dash': dash,
        'usuario': request.user,
        'lista_cidades': cidades,
        'lista_construtoras': construtoras,
        'lista_fases': fases,
        'kpis': kpis,
        'share_empresas': share_empresas,
        'share_emps': share_emps,
        'share_empresas_json': json.dumps(share_empresas),
        'share_emps_json': json.dumps(share_emps),
        'aba_atual': 'share',
    }
    response = render(request, 'app/logistico/share.html', ctx)
    return set_jwt_cookie(response, request)