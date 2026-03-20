from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect
from django.db.models import Sum, Avg, Min, Max
from rest_framework_simplejwt.tokens import RefreshToken
import pandas as pd


def set_jwt_cookie(response, usuario):
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
    def wrapper(request, *args, **kwargs):
        if not request.user.is_admin():
            messages.error(request, 'Acesso restrito a administradores.')
            return redirect('lista_dashboards')
        return view_func(request, *args, **kwargs)
    return wrapper


def aplicar_filtros(qs, request, incluir_slider=True):
    # Múltipla seleção — getlist retorna lista
    quartos_list     = request.GET.getlist('quartos')
    construtora_list = request.GET.getlist('construtora')
    bairro_list      = request.GET.getlist('bairro')
    fase_list        = request.GET.getlist('fase')

    if quartos_list:
        qs = qs.filter(quartos__in=quartos_list)
    if construtora_list:
        qs = qs.filter(construtora__in=construtora_list)
    if bairro_list:
        qs = qs.filter(bairro__in=bairro_list)
    if fase_list:
        qs = qs.filter(fase_obra__in=fase_list)

    if request.GET.get('data_inicio') and request.GET.get('data_fim'):
        qs = qs.filter(data_entrega__range=[request.GET.get('data_inicio'), request.GET.get('data_fim')])
    if request.GET.get('comerc_inicio') and request.GET.get('comerc_fim'):
        qs = qs.filter(data_comercializacao__range=[request.GET.get('comerc_inicio'), request.GET.get('comerc_fim')])

    if incluir_slider:
        if request.GET.get('pm2_min'):
            qs = qs.filter(preco_medio_m2__gte=request.GET.get('pm2_min'))
        if request.GET.get('pm2_max'):
            qs = qs.filter(preco_medio_m2__lte=request.GET.get('pm2_max'))
        if request.GET.get('area_min'):
            qs = qs.filter(area_unidade__gte=request.GET.get('area_min'))
        if request.GET.get('area_max'):
            qs = qs.filter(area_unidade__lte=request.GET.get('area_max'))
        if request.GET.get('preco_min'):
            qs = qs.filter(preco_unidade__gte=request.GET.get('preco_min'))
        if request.GET.get('preco_max'):
            qs = qs.filter(preco_unidade__lte=request.GET.get('preco_max'))
    return qs


def get_listas_sidebar(dash, model):
    todos = model.objects.filter(dashboard=dash)
    return {
        'lista_bairros':      sorted(todos.values_list('bairro', flat=True).distinct()),
        'lista_construtoras': sorted(todos.values_list('construtora', flat=True).distinct().exclude(construtora__isnull=True)),
        'lista_fases':        sorted(todos.values_list('fase_obra', flat=True).distinct().exclude(fase_obra__isnull=True)),
        'lista_quartos':      sorted(todos.values_list('quartos', flat=True).distinct().exclude(quartos__isnull=True)),
    }


def get_ranges(dash, model):
    return model.objects.filter(dashboard=dash).aggregate(
        pm2_min=Min('preco_medio_m2'), pm2_max=Max('preco_medio_m2'),
        area_min=Min('area_unidade'),  area_max=Max('area_unidade'),
        preco_min=Min('preco_unidade'), preco_max=Max('preco_unidade'),
    )


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
    if pd.isna(valor) or valor == "" or valor is None:
        return 0
    val_str = str(valor).strip().upper()
    if val_str in ('NI', 'N/I', 'N/A', 'NA', '-', '--', 'ND'):
        return 0
    try:
        return int(float(val_str))
    except:
        return 0


FAIXAS_AREA = [
    ('Até 35,00 m²',          None,   35),
    ('De 35,01 a 45,00 m²',   35.01,  45),
    ('De 45,01 a 60,00 m²',   45.01,  60),
    ('De 60,01 a 80,00 m²',   60.01,  80),
    ('De 80,01 a 100,00 m²',  80.01, 100),
    ('De 100,01 a 120,00 m²', 100.01, 120),
    ('De 120,01 a 150,00 m²', 120.01, 150),
    ('De 150,01 a 200,00 m²', 150.01, 200),
    ('De 200,01 a 300,00 m²', 200.01, 300),
    ('Acima de 300,01 m²',    300.01, None),
]


def tabela_hierarquica_bairro_fase_construtora(base, total_geral_u):
    """
    Faz UMA única query agrupada e monta a hierarquia em Python.
    Antes: N queries em loop. Agora: 1 query só.
    """
    from collections import defaultdict

    # 1 query só — agrupa por bairro+fase+construtora de uma vez
    rows = list(
        base.values('bairro', 'fase_obra', 'construtora')
        .annotate(
            total_u=Sum('unidades_totais'),
            total_e=Sum('estoque'),
            total_v=Sum('unidades_vendidas'),
            avg_m2 =Avg('preco_medio_m2'),
            avg_a  =Avg('area_unidade'),
        )
        .order_by('bairro', 'fase_obra', 'construtora')
    )

    def calc(total_u, total_e, total_v, avg_m2, avg_a):
        return {
            'total_u':   total_u or 0,
            'total_e':   total_e or 0,
            'total_v':   total_v or 0,
            'pct_share': round((total_u or 0) / total_geral_u * 100, 2) if total_geral_u else 0,
            'pct_v':     round((total_v or 0) / (total_u or 1) * 100, 2),
            'avg_m2':    round(float(avg_m2 or 0), 0),
            'avg_a':     round(float(avg_a  or 0), 2),
        }

    # Agrupa em Python — zero queries adicionais
    bairro_map = defaultdict(lambda: defaultdict(list))
    for r in rows:
        bairro_map[r['bairro'] or 'Sem Bairro'][r['fase_obra'] or 'Sem Fase'].append(r)

    tabela = []
    for bairro_nome in sorted(bairro_map.keys()):
        fases_map = bairro_map[bairro_nome]

        # Agrega bairro somando todas as linhas
        all_rows_b = [r for fase_rows in fases_map.values() for r in fase_rows]
        b_tu = sum(r['total_u'] or 0 for r in all_rows_b)
        b_te = sum(r['total_e'] or 0 for r in all_rows_b)
        b_tv = sum(r['total_v'] or 0 for r in all_rows_b)
        b_m2s = [float(r['avg_m2']) for r in all_rows_b if r['avg_m2']]
        b_as  = [float(r['avg_a'])  for r in all_rows_b if r['avg_a']]

        b = calc(b_tu, b_te, b_tv,
                 sum(b_m2s)/len(b_m2s) if b_m2s else 0,
                 sum(b_as) /len(b_as)  if b_as  else 0)
        b['bairro'] = bairro_nome

        fases = []
        for fase_nome in sorted(fases_map.keys()):
            fase_rows = fases_map[fase_nome]

            f_tu = sum(r['total_u'] or 0 for r in fase_rows)
            f_te = sum(r['total_e'] or 0 for r in fase_rows)
            f_tv = sum(r['total_v'] or 0 for r in fase_rows)
            f_m2s = [float(r['avg_m2']) for r in fase_rows if r['avg_m2']]
            f_as  = [float(r['avg_a'])  for r in fase_rows if r['avg_a']]

            f = calc(f_tu, f_te, f_tv,
                     sum(f_m2s)/len(f_m2s) if f_m2s else 0,
                     sum(f_as) /len(f_as)  if f_as  else 0)
            f['nome'] = fase_nome

            construtoras = []
            for r in sorted(fase_rows, key=lambda x: x['construtora'] or ''):
                c = calc(r['total_u'], r['total_e'], r['total_v'], r['avg_m2'], r['avg_a'])
                c['nome'] = r['construtora'] or 'Não informado'
                construtoras.append(c)

            f['construtoras'] = construtoras
            fases.append(f)

        b['fases'] = fases
        tabela.append(b)

    return tabela