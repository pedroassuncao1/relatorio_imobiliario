from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Sum, Avg, Min, Max
from ..models import Dashboard, AcessoDashboard, Empreendimento
from .helpers import aplicar_filtros, get_listas_sidebar, get_ranges, FAIXAS_AREA, tabela_hierarquica_bairro_fase_construtora
import json


def _verificar_acesso(request, dash):
    if not request.user.is_admin():
        if not AcessoDashboard.objects.filter(usuario=request.user, dashboard=dash).exists():
            messages.error(request, 'Você não tem acesso a este dashboard.')
            return False
    return True


def _grafico1(base):
    emp_preco = base.values('nome').annotate(avg_m2=Avg('preco_medio_m2')).filter(avg_m2__isnull=False).order_by('-avg_m2')
    return [{'nome': e['nome'], 'avg_m2': round(float(e['avg_m2']), 0)} for e in emp_preco]


def _grafico2(base):
    resultado = []
    for label, fmin, fmax in FAIXAS_AREA:
        q = base
        if fmin: q = q.filter(area_unidade__gte=fmin)
        if fmax: q = q.filter(area_unidade__lte=fmax)
        s = q.aggregate(total_v=Sum('unidades_vendidas'), total_e=Sum('estoque'), avg_m2=Avg('preco_medio_m2'))
        resultado.append({
            'label': label, 'vendidas': s['total_v'] or 0,
            'estoque': s['total_e'] or 0, 'avg_m2': round(float(s['avg_m2'] or 0), 0),
        })
    return resultado


def _total_geral(base):
    sg = base.aggregate(
        total_u=Sum('unidades_totais'), total_e=Sum('estoque'),
        total_v=Sum('unidades_vendidas'), avg_m2=Avg('preco_medio_m2'), avg_a=Avg('area_unidade'),
    )
    tu = sg['total_u'] or 0; tv = sg['total_v'] or 0
    return {
        'total_e': sg['total_e'] or 0, 'total_u': tu, 'pct_share': 100.0, 'total_v': tv,
        'pct_v': round(tv / tu * 100, 2) if tu else 0,
        'avg_m2': round(float(sg['avg_m2'] or 0), 0),
        'avg_a':  round(float(sg['avg_a']  or 0), 2),
    }


def _render_pricing_view(request, dash, template):
    base         = aplicar_filtros(Empreendimento.objects.filter(dashboard=dash), request)
    total_geral_u = base.aggregate(t=Sum('unidades_totais'))['t'] or 1

    return render(request, template, {
        'dash': dash, 'usuario': request.user,
        'grafico1_json': json.dumps(_grafico1(base)),
        'grafico2_json': json.dumps(_grafico2(base)),
        'tabela':        tabela_hierarquica_bairro_fase_construtora(base, total_geral_u),
        'total_geral':   _total_geral(base),
        'ranges':        get_ranges(dash, Empreendimento),
        'pm2_min_val':   request.GET.get('pm2_min', ''),
        'pm2_max_val':   request.GET.get('pm2_max', ''),
        'area_min_val':  request.GET.get('area_min', ''),
        'area_max_val':  request.GET.get('area_max', ''),
        'preco_min_val': request.GET.get('preco_min', ''),
        'preco_max_val': request.GET.get('preco_max', ''),
        **get_listas_sidebar(dash, Empreendimento),
    })


def analise_preco(request, dashboard_id):
    dash = get_object_or_404(Dashboard, id=dashboard_id)
    if not _verificar_acesso(request, dash):
        return redirect('lista_dashboards')
    return _render_pricing_view(request, dash, 'app/analise_preco.html')


def pricing(request, dashboard_id):
    dash = get_object_or_404(Dashboard, id=dashboard_id)
    if not _verificar_acesso(request, dash):
        return redirect('lista_dashboards')
    return _render_pricing_view(request, dash, 'app/pricing.html')