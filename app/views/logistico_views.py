"""
app/views/logistico_views.py

Views para o dashboard logístico.
Telas: dashboard_logistico, abl_estoque, precos, distancias, share_logistico

IMPORTANTE: O banco armazena 1 registro por empreendimento (sem tipologias separadas).
O ABL já vem somado do parser. Não há mais necessidade de agrupar por nome.
"""

import json
import math
from django.shortcuts import render, get_object_or_404
from django.db.models import Sum, Avg, Count
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from app.models import Dashboard, EmpreendimentoLogistico, AcessoDashboard
from app.utils import buscar_coordenadas
from app.views.helpers import set_jwt_cookie


# ── Helpers ──────────────────────────────────────────────────────────────────

def _check_acesso(request, dash):
    if request.user.role == 'admin':
        return True
    return AcessoDashboard.objects.filter(usuario=request.user, dashboard=dash).exists()


def _haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _get_raizes(dash, request):
    """Queryset de empreendimentos com filtros da sidebar aplicados."""
    qs = EmpreendimentoLogistico.objects.filter(
        dashboard=dash,
        empreendimento_principal__isnull=True,
    )

    cidades     = request.GET.getlist('cidade')
    construtoras = request.GET.getlist('construtora')
    fases       = request.GET.getlist('fase')

    if cidades:      qs = qs.filter(cidade__in=cidades)
    if construtoras: qs = qs.filter(construtora__in=construtoras)
    if fases:        qs = qs.filter(fase_obra__in=fases)

    abl_min = request.GET.get('abl_min')
    abl_max = request.GET.get('abl_max')
    vac_min = request.GET.get('vac_min')
    vac_max = request.GET.get('vac_max')

    if abl_min: qs = qs.filter(abl_m2__gte=float(abl_min))
    if abl_max: qs = qs.filter(abl_m2__lte=float(abl_max))
    if vac_min: qs = qs.filter(vacancia__gte=float(vac_min) / 100)
    if vac_max: qs = qs.filter(vacancia__lte=float(vac_max) / 100)

    return qs


def _get_listas_sidebar(dash):
    base = EmpreendimentoLogistico.objects.filter(
        dashboard=dash,
        empreendimento_principal__isnull=True,
    )
    cidades = sorted(set(
        c.strip() for c in base.exclude(cidade__isnull=True).exclude(cidade='')
                               .values_list('cidade', flat=True)
    ))
    construtoras = sorted(set(
        c.strip() for c in base.exclude(construtora__isnull=True).exclude(construtora='')
                               .values_list('construtora', flat=True)
    ))
    fases = sorted(set(
        f.strip() for f in base.exclude(fase_obra__isnull=True).exclude(fase_obra='')
                               .values_list('fase_obra', flat=True)
    ))
    return cidades, construtoras, fases


def _kpis_raizes(qs):
    """KPIs agregados. modulos/ocupados/disponiveis vêm direto do banco (já corretos)."""
    agg = qs.aggregate(
        total_modulos    = Sum('num_modulos'),
        total_ocupados   = Sum('modulos_ocupados'),
        total_disponiveis= Sum('modulos_disponiveis'),
        total_abl        = Sum('abl_m2'),
        avg_m2_loc       = Avg('preco_m2_locacao'),
        avg_m2_cnd       = Avg('preco_m2_condominio'),
        num_emp          = Count('id'),
    )
    t_mod = agg['total_modulos']   or 0
    t_ocu = agg['total_ocupados']  or 0
    pct_vac = round((1 - t_ocu / t_mod) * 100, 1) if t_mod > 0 else 0

    return {
        'total_modulos':      t_mod,
        'modulos_ocupados':   t_ocu,
        'modulos_disponiveis': agg['total_disponiveis'] or 0,
        'total_abl':          round(agg['total_abl'] or 0, 0),
        'pct_vacancia':       max(pct_vac, 0),
        'avg_m2_locacao':     round(float(agg['avg_m2_loc'] or 0), 2),
        'avg_m2_condominio':  round(float(agg['avg_m2_cnd'] or 0), 2),
        'num_empreendimentos': agg['num_emp'] or 0,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 1. MAPA & KPIs
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def dashboard_logistico(request, dashboard_id):
    dash = get_object_or_404(Dashboard, id=dashboard_id, tipo='logistico')
    if not _check_acesso(request, dash):
        return render(request, 'app/sem_acesso.html')

    cidades, construtoras, fases = _get_listas_sidebar(dash)
    qs   = _get_raizes(dash, request)
    kpis = _kpis_raizes(qs)

    dados_mapa = []
    for emp in qs.filter(latitude__isnull=False, longitude__isnull=False):
        dados_mapa.append({
            'id':                  emp.id,
            'nome':                emp.nome,
            'cidade':              emp.cidade or '',
            'construtora':         emp.construtora or '',
            'fase':                emp.fase_obra or '',
            'lat':                 emp.latitude,
            'lng':                 emp.longitude,
            'abl':                 emp.abl_m2 or 0,
            'num_modulos':         emp.num_modulos or 0,
            'modulos_ocupados':    emp.modulos_ocupados or 0,
            'modulos_disponiveis': emp.modulos_disponiveis or 0,
            'pct_vacancia':        emp.pct_vacancia() or 0,
            'preco_m2_locacao':    float(emp.preco_m2_locacao or 0),
            'distancia_km':        emp.distancia_ref_km,
        })

    ctx = {
        'dash': dash,
        'usuario': request.user,
        'lista_cidades': cidades,
        'lista_construtoras': construtoras,
        'lista_construtoras_json': json.dumps(list(construtoras)),
        'lista_fases': fases,
        'kpis': kpis,
        'dados_mapa_json': json.dumps(dados_mapa),
        'ref_lat':  dash.ref_latitude,
        'ref_lon':  dash.ref_longitude,
        'ref_nome': dash.ref_nome or 'Ponto de Referência',
        'aba_atual': 'dashboard',
    }
    response = render(request, 'app/logistico/logistico_dashboard.html', ctx)
    return set_jwt_cookie(response, request.user)


# ─────────────────────────────────────────────────────────────────────────────
# 2. ABL & ESTOQUE
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def abl_estoque(request, dashboard_id):
    dash = get_object_or_404(Dashboard, id=dashboard_id, tipo='logistico')
    if not _check_acesso(request, dash):
        return render(request, 'app/sem_acesso.html')

    cidades, construtoras, fases = _get_listas_sidebar(dash)
    qs   = _get_raizes(dash, request)
    kpis = _kpis_raizes(qs)

    # 1 linha no banco = 1 empreendimento — iteração direta, sem agrupamento
    dados_abl = []
    for emp in qs.order_by('-abl_m2'):
        mod = emp.num_modulos or 0
        ocu = emp.modulos_ocupados or 0
        disp = emp.modulos_disponiveis or 0
        pct_vac = round((1 - ocu / mod) * 100, 1) if mod > 0 else None
        dados_abl.append({
            'nome':          emp.nome,
            'abl':           round(emp.abl_m2 or 0, 0),
            'ocupados':      ocu,
            'disponiveis':   disp,
            'total_modulos': mod,
            'pct_vacancia':  pct_vac if pct_vac is not None else 0,
            'sem_modulos':   mod == 0,   # flag para gráfico (LOG II etc.)
        })

    # ABL por cidade
    por_cidade = (
        qs.values('cidade')
          .annotate(
              total_abl        = Sum('abl_m2'),
              total_modulos    = Sum('num_modulos'),
              total_ocupados   = Sum('modulos_ocupados'),
              total_disponiveis= Sum('modulos_disponiveis'),
          )
          .order_by('-total_abl')
    )

    ctx = {
        'dash': dash,
        'usuario': request.user,
        'lista_cidades': cidades,
        'lista_construtoras': construtoras,
        'lista_fases': fases,
        'kpis': kpis,
        'dados_abl_json':   json.dumps(dados_abl),
        'por_cidade_json':  json.dumps(list(por_cidade)),
        'empreendimentos':  qs.order_by('-abl_m2'),
        'aba_atual': 'abl',
    }
    response = render(request, 'app/logistico/logistico_abl.html', ctx)
    return set_jwt_cookie(response, request.user)


# ─────────────────────────────────────────────────────────────────────────────
# 3. PREÇOS
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def precos(request, dashboard_id):
    dash = get_object_or_404(Dashboard, id=dashboard_id, tipo='logistico')
    if not _check_acesso(request, dash):
        return render(request, 'app/sem_acesso.html')

    cidades, construtoras, fases = _get_listas_sidebar(dash)
    qs   = _get_raizes(dash, request)
    kpis = _kpis_raizes(qs)

    dados_precos = []
    for emp in qs.exclude(preco_m2_locacao__isnull=True).order_by('-preco_m2_locacao'):
        dados_precos.append({
            'nome':          emp.nome,
            'cidade':        emp.cidade or '',
            'pm2_locacao':   float(emp.preco_m2_locacao or 0),
            'pm2_condominio': float(emp.preco_m2_condominio or 0),
            'pm2_iptu':      float(emp.preco_m2_iptu or 0),
            'pm2_total':     round(
                float(emp.preco_m2_locacao    or 0) +
                float(emp.preco_m2_condominio or 0) +
                float(emp.preco_m2_iptu       or 0), 2
            ),
        })

    # Tabela simples (sem hierarquia de tipologias)
    tabela = [{'emp': emp, 'tipologias': []} for emp in qs.order_by('numero')]

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
    response = render(request, 'app/logistico/logistico_precos.html', ctx)
    return set_jwt_cookie(response, request.user)


# ─────────────────────────────────────────────────────────────────────────────
# 4. DISTÂNCIAS
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def distancias(request, dashboard_id):
    dash = get_object_or_404(Dashboard, id=dashboard_id, tipo='logistico')
    if not _check_acesso(request, dash):
        return render(request, 'app/sem_acesso.html')

    cidades, construtoras, fases = _get_listas_sidebar(dash)
    qs = _get_raizes(dash, request)
    kpis = _kpis_raizes(qs)

    # Pegamos apenas quem tem coordenada
    emps_dist = list(qs.filter(latitude__isnull=False, longitude__isnull=False))
    
    if dash.ref_latitude is not None and dash.ref_longitude is not None:
        for emp in emps_dist:
            emp.distancia_ref_km = round(
                _haversine(emp.latitude, emp.longitude, dash.ref_latitude, dash.ref_longitude), 2
            )
        # Ordena por distância
        emps_dist.sort(key=lambda x: x.distancia_ref_km)
    else:
        for emp in emps_dist:
            emp.distancia_ref_km = 0

    dados_dist = []
    for emp in emps_dist:
        dados_dist.append({
            'nome': emp.nome,
            'cidade': emp.cidade or '',
            'distancia_km': emp.distancia_ref_km,
            'lat': float(emp.latitude),
            'lng': float(emp.longitude),
        })

    ctx = {
        'dash': dash,
        'usuario': request.user,
        'kpis': kpis,
        'dados_dist_json': json.dumps(dados_dist),
        'emps_dist': emps_dist,
        'emps_dist_count': len(emps_dist), # Variável que faltava
        'ref_nome': dash.ref_nome or 'Área de Estudo',
        'ref_lat': dash.ref_latitude,
        'ref_lon': dash.ref_longitude,
        'aba_atual': 'distancias',
    }
    response = render(request, 'app/logistico/logistico_distancias.html', ctx)
    return set_jwt_cookie(response, request.user)

# ─────────────────────────────────────────────────────────────────────────────
# 5. SHARE / PARTICIPAÇÃO
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def share_logistico(request, dashboard_id):
    dash = get_object_or_404(Dashboard, id=dashboard_id, tipo='logistico')
    if not _check_acesso(request, dash):
        return render(request, 'app/sem_acesso.html')

    cidades, construtoras, fases = _get_listas_sidebar(dash)
    qs   = _get_raizes(dash, request)
    kpis = _kpis_raizes(qs)

    total_abl = qs.aggregate(t=Sum('abl_m2'))['t']  or 1
    total_mod = qs.aggregate(t=Sum('num_modulos'))['t'] or 1

    # Share por empresa
    por_empresa = (
        qs.values('construtora')
          .annotate(
              abl     = Sum('abl_m2'),
              modulos = Sum('num_modulos'),
              ocupados= Sum('modulos_ocupados'),
              num_emp = Count('id'),
          )
          .order_by('-abl')
    )
    share_empresas = []
    for row in por_empresa:
        construtora = (row['construtora'] or 'Não informado').strip()
        abl = row['abl'] or 0
        mod = row['modulos'] or 0
        ocu = row['ocupados'] or 0
        share_empresas.append({
            'construtora':  construtora,
            'abl':          round(abl, 0),
            'pct_abl':      round(abl / total_abl * 100, 1),
            'modulos':      mod,
            'pct_modulos':  round(mod / total_mod * 100, 1),
            'ocupados':     ocu,
            'pct_vacancia': round((1 - ocu / mod) * 100, 1) if mod > 0 else 0,
            'num_emp':      row['num_emp'],
        })

    # Share por empreendimento
    share_emps = []
    for emp in qs.order_by('-abl_m2'):
        abl = emp.abl_m2 or 0
        mod = emp.num_modulos or 0
        ocu = emp.modulos_ocupados or 0
        share_emps.append({
            'nome':        emp.nome,
            'construtora': (emp.construtora or '').strip(),
            'cidade':      emp.cidade or '',
            'abl':         round(abl, 0),
            'pct_abl':     round(abl / total_abl * 100, 1),
            'modulos':     mod,
            'pct_modulos': round(mod / total_mod * 100, 1),
            'ocupados':    ocu,
            'pct_vacancia': emp.pct_vacancia() or 0,
            'lat':         emp.latitude,
            'lng':         emp.longitude,
        })

    ctx = {
        'dash': dash,
        'usuario': request.user,
        'lista_cidades': cidades,
        'lista_construtoras': construtoras,
        'lista_fases': fases,
        'kpis': kpis,
        'share_empresas':      share_empresas,
        'share_emps':          share_emps,
        'share_empresas_json': json.dumps(share_empresas),
        'share_emps_json':     json.dumps(share_emps),
        'aba_atual': 'share',
    }
    response = render(request, 'app/logistico/logistico_share.html', ctx)
    return set_jwt_cookie(response, request.user)


# ─────────────────────────────────────────────────────────────────────────────
# 6. ATUALIZAR LOCALIZAÇÃO (somente admin) — chamado via fetch do modal
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@require_POST
def atualizar_localizacao(request, dashboard_id):
    """
    Recebe JSON com uma das duas opções:
      { emp_id: int, endereco: str }         → geocoding pelo endereço
      { emp_id: int, lat_direta: float, lng_direta: float }  → coordenadas diretas

    Retorna JSON: { ok: bool, lat, lng, erro? }
    """
    if request.user.role != 'admin':
        return JsonResponse({'ok': False, 'erro': 'Sem permissão.'}, status=403)

    dash = get_object_or_404(Dashboard, id=dashboard_id, tipo='logistico')

    try:
        payload = json.loads(request.body)
        emp_id  = int(payload.get('emp_id', 0))
    except (ValueError, TypeError):
        return JsonResponse({'ok': False, 'erro': 'Dados inválidos.'}, status=400)

    emp = get_object_or_404(EmpreendimentoLogistico, id=emp_id, dashboard=dash)

    # ── Coordenadas diretas? ──────────────────────────────────────────────────
    lat_direta = payload.get('lat_direta')
    lng_direta = payload.get('lng_direta')

    if lat_direta is not None and lng_direta is not None:
        try:
            lat = float(lat_direta)
            lng = float(lng_direta)
        except (ValueError, TypeError):
            return JsonResponse({'ok': False, 'erro': 'Coordenadas inválidas.'}, status=400)

        if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
            return JsonResponse({'ok': False, 'erro': 'Coordenadas fora do intervalo válido.'}, status=400)

        emp.latitude  = lat
        emp.longitude = lng
        emp.save(update_fields=['latitude', 'longitude'])
        return JsonResponse({'ok': True, 'lat': lat, 'lng': lng})

    # ── Geocoding por endereço ────────────────────────────────────────────────
    endereco = str(payload.get('endereco', '')).strip()
    if not endereco:
        return JsonResponse({'ok': False, 'erro': 'Endereço vazio.'}, status=400)

    cidade = emp.cidade or ''
    try:
        lat, lng = buscar_coordenadas(endereco, '', cidade)
    except Exception as e:
        return JsonResponse({'ok': False, 'erro': f'Erro no geocoding: {e}'}, status=500)

    if not lat or not lng:
        return JsonResponse({
            'ok': False,
            'erro': 'Endereço não encontrado. Tente ser mais específico ou cole as coordenadas do Google Maps diretamente.'
        })

    emp.latitude  = lat
    emp.longitude = lng
    emp.save(update_fields=['latitude', 'longitude'])
    return JsonResponse({'ok': True, 'lat': lat, 'lng': lng})


@login_required
@require_POST
def atualizar_referencia_localizacao(request, dashboard_id):
    """Atualiza a referência da Área de Estudo do dashboard logístico."""
    if request.user.role != 'admin':
        return JsonResponse({'ok': False, 'erro': 'Sem permissão.'}, status=403)

    dash = get_object_or_404(Dashboard, id=dashboard_id, tipo='logistico')

    try:
        payload = json.loads(request.body)
    except (ValueError, TypeError):
        return JsonResponse({'ok': False, 'erro': 'Dados inválidos.'}, status=400)

    ref_nome = str(payload.get('ref_nome', '')).strip() or 'Área de Estudo'
    lat_direta = payload.get('ref_lat_direta')
    lng_direta = payload.get('ref_lon_direta')
    endereco = str(payload.get('ref_endereco', '')).strip()

    if lat_direta is not None and lng_direta is not None:
        try:
            lat = float(lat_direta)
            lng = float(lng_direta)
        except (ValueError, TypeError):
            return JsonResponse({'ok': False, 'erro': 'Coordenadas inválidas.'}, status=400)

        if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
            return JsonResponse({'ok': False, 'erro': 'Coordenadas fora do intervalo válido.'}, status=400)

        dash.ref_latitude = lat
        dash.ref_longitude = lng
        dash.ref_nome = ref_nome
        dash.save(update_fields=['ref_latitude', 'ref_longitude', 'ref_nome'])
        return JsonResponse({'ok': True, 'ref_lat': lat, 'ref_lon': lng, 'ref_nome': ref_nome})

    if endereco:
        try:
            lat, lng = buscar_coordenadas(endereco, '', '')
        except Exception as e:
            return JsonResponse({'ok': False, 'erro': f'Erro no geocoding: {e}'}, status=500)

        if not lat or not lng:
            return JsonResponse({
                'ok': False,
                'erro': 'Endereço não encontrado. Tente ser mais específico ou cole as coordenadas do Google Maps diretamente.'
            }, status=400)

        dash.ref_latitude = lat
        dash.ref_longitude = lng
        dash.ref_nome = ref_nome
        dash.save(update_fields=['ref_latitude', 'ref_longitude', 'ref_nome'])
        return JsonResponse({'ok': True, 'ref_lat': lat, 'ref_lon': lng, 'ref_nome': ref_nome})

    return JsonResponse({'ok': False, 'erro': 'Envie endereço ou coordenadas para atualizar a Área de Estudo.'}, status=400)