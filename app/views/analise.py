from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Sum, Avg, Min, Max
from collections import defaultdict
from ..models import Dashboard, AcessoDashboard, Empreendimento
from .helpers import aplicar_filtros, get_listas_sidebar, get_ranges, FAIXAS_AREA
import json
from django.http import JsonResponse

def _validar_aba_ativa(dash, slug_procurado):
    """
    Retorna True se o slug da aba estiver na lista de abas ativas do dashboard.
    """
    abas_ativas = dash.get_abas_ativas()
    # Debug temporário: imprima no console para ver o que o banco está retornando
    print(f"DEBUG: Procurando {slug_procurado} em {abas_ativas}")
    return slug_procurado in abas_ativas

def _verificar_acesso(request, dash):
    if not request.user.is_admin():
        if not AcessoDashboard.objects.filter(usuario=request.user, dashboard=dash).exists():
            messages.error(request, 'Você não tem acesso a este dashboard.')
            return False
    return True


def graficos(request, dashboard_id):
    dash = get_object_or_404(Dashboard, id=dashboard_id)
    if not _verificar_acesso(request, dash):
        return redirect('lista_dashboards')
    
        # Bloqueio se a aba estiver desativada pelo "Editar Dashboard"
    if not _validar_aba_ativa(dash, 'graficos'):
        messages.warning(request, 'Esta funcionalidade está desativada para este dashboard.')
        return redirect('dashboard', dashboard_id=dash.id)

    dados_qs = aplicar_filtros(Empreendimento.objects.filter(dashboard=dash), request)

    # ── 1 query agrupada para KPIs e tabela ──
    rows = list(
        dados_qs.values('bairro', 'fase_obra', 'nome', 'construtora')
        .annotate(
            total_u=Sum('unidades_totais'),
            total_e=Sum('estoque'),
            total_v=Sum('unidades_vendidas'),
            avg_m2 =Avg('preco_medio_m2'),
            avg_a  =Avg('area_unidade'),
        )
        .order_by('bairro', 'fase_obra', 'construtora')
    )

    # ── KPIs ──
    total_unidades    = sum(r['total_u'] or 0 for r in rows)
    total_estoque     = sum(r['total_e'] or 0 for r in rows)
    total_vendidas    = sum(r['total_v'] or 0 for r in rows)
    pct_vendido_total = round(total_vendidas / total_unidades * 100, 2) if total_unidades else 0
    m2s   = [float(r['avg_m2']) for r in rows if r['avg_m2']]
    areas = [float(r['avg_a'])  for r in rows if r['avg_a']]
    media_m2   = round(sum(m2s)   / len(m2s),   2) if m2s   else 0
    media_area = round(sum(areas) / len(areas), 2) if areas else 0

    # ── Gráfico 1: Preço M² por Empreendimento (top 20) ──
    emp_preco = defaultdict(list)
    for r in rows:
        if r['avg_m2']:
            emp_preco[r['nome'] or 'Sem Nome'].append(float(r['avg_m2']))
    emp_sorted = sorted(
        {k: round(sum(v)/len(v), 2) for k, v in emp_preco.items()}.items(),
        key=lambda x: x[1], reverse=True
    )

    # ── Gráfico 2: Faixas de área ──
    faixas_labels = [
        ('Até\n35,00\nm²',          0,      35),
        ('De\n35,01 a\n45,00\nm²',  35.01,  45),
        ('De\n45,01 a\n60,00\nm²',  45.01,  60),
        ('De\n60,01 a\n80,00\nm²',  60.01,  80),
        ('De\n80,01 a\n100,01\nm²', 80.01, 100),
        ('De\n100,01\na\n120,00\nm²',100.01,120),
        ('De\n120,01\na\n150,00\nm²',120.01,150),
        ('De\n150,01\na\n200,00\nm²',150.01,200),
        ('De\n200,01\na\n300,00\nm²',200.01,300),
        ('Acima\nde\n300,01\nm²',   300.01,9999),
    ]

    # query única para faixas
    registros_area = list(
        dados_qs.values('area_unidade', 'unidades_vendidas', 'estoque', 'preco_medio_m2')
    )
    met_labels, met_vendidas, met_estoque, met_preco = [], [], [], []
    for label, fmin, fmax in faixas_labels:
        grupo = [
            r for r in registros_area
            if r['area_unidade'] and fmin <= float(r['area_unidade']) <= fmax
        ]
        if not grupo:
            continue
        met_labels.append(label)
        met_vendidas.append(sum(r['unidades_vendidas'] or 0 for r in grupo))
        met_estoque.append(sum(r['estoque'] or 0 for r in grupo))
        pm2s = [float(r['preco_medio_m2']) for r in grupo if r['preco_medio_m2']]
        met_preco.append(round(sum(pm2s)/len(pm2s), 0) if pm2s else 0)

    # ── Tabela hierárquica: agrupamento em Python ──
    def media(lst):
        return round(sum(lst) / len(lst), 2) if lst else 0

    def agg_rows(rws):
        tu = sum(r['total_u'] or 0 for r in rws)
        tv = sum(r['total_v'] or 0 for r in rws)
        return {
            'total':    tu,
            'estoque':  sum(r['total_e'] or 0 for r in rws),
            'vendidas': tv,
            'share':    round(tu / total_unidades * 100, 2) if total_unidades else 0,
            'pct_vend': round(tv / tu * 100, 2) if tu else 0,
            'm2':       media([float(r['avg_m2']) for r in rws if r['avg_m2']]),
            'area':     media([float(r['avg_a'])  for r in rws if r['avg_a']]),
        }

    bairro_map = defaultdict(lambda: defaultdict(list))
    for r in rows:
        bairro_map[r['bairro'] or 'Sem Bairro'][r['fase_obra'] or 'Sem Fase'].append(r)

    tabela_dados = []
    for bn in sorted(bairro_map.keys()):
        fases_map = bairro_map[bn]
        all_b = [r for fase_rows in fases_map.values() for r in fase_rows]
        b = agg_rows(all_b); b['nome'] = bn
        b['fases'] = []
        for fn in sorted(fases_map.keys()):
            f_rows = fases_map[fn]
            f = agg_rows(f_rows); f['nome'] = fn
            const_map = defaultdict(list)
            for r in f_rows:
                const_map[r['construtora'] or 'Sem Construtora'].append(r)
            f['construtoras'] = [
                {**agg_rows(v), 'nome': k}
                for k, v in sorted(const_map.items())
            ]
            b['fases'].append(f)
        tabela_dados.append(b)

    return render(request, 'app/graficos.html', {
        'dash': dash, 'usuario': request.user,
        'total_unidades':          total_unidades,
        'total_estoque':           total_estoque,
        'total_vendidas':          total_vendidas,
        'pct_vendido_total':       pct_vendido_total,
        'media_m2':                media_m2,
        'media_area':              media_area,
        'chart_preco_emp_labels':  json.dumps([e[0] for e in emp_sorted], ensure_ascii=False),
        'chart_preco_emp_valores': json.dumps([e[1] for e in emp_sorted]),
        'chart_metragem_labels':   json.dumps(met_labels, ensure_ascii=False),
        'chart_metragem_vendidas': json.dumps(met_vendidas),
        'chart_metragem_estoque':  json.dumps(met_estoque),
        'chart_metragem_preco':    json.dumps(met_preco),
        'tabela_dados':            tabela_dados,
        **get_listas_sidebar(dash, Empreendimento),
    })


def share_estoque(request, dashboard_id):
    dash = get_object_or_404(Dashboard, id=dashboard_id)
    if not _verificar_acesso(request, dash):
        return redirect('lista_dashboards')
    
        # Bloqueio se a aba estiver desativada pelo "Editar Dashboard"
    if not _validar_aba_ativa(dash, 'share_estoque'):
        messages.warning(request, 'Esta funcionalidade está desativada para este dashboard.')
        return redirect('dashboard', dashboard_id=dash.id)

    qs = aplicar_filtros(Empreendimento.objects.filter(dashboard=dash), request)
    construtoras_data = qs.values('construtora').annotate(
        estoque=Sum('estoque'), total_unidades=Sum('unidades_totais')
    ).filter(estoque__gt=0).order_by('-estoque')

    total_e = sum(c['estoque'] for c in construtoras_data)
    total_u = qs.aggregate(t=Sum('unidades_totais'))['t'] or 0

    def build_list(data, nome_key):
        return [{
            'nome': d[nome_key] or 'Não informado',
            'estoque': d['estoque'],
            'pct_estoque': round(d['estoque'] / total_e * 100, 2) if total_e else 0,
            'total_unidades': d['total_unidades'],
            'pct_unidades': round(d['total_unidades'] / total_u * 100, 2) if total_u else 0,
        } for d in data]

    emp_data = qs.values('nome').annotate(
        estoque=Sum('estoque'), total_unidades=Sum('unidades_totais')
    ).filter(estoque__gt=0).order_by('-estoque')

    return render(request, 'app/share_estoque.html', {
        'dash': dash, 'usuario': request.user,
        'construtoras_list':    build_list(construtoras_data, 'construtora'),
        'empreendimentos_list': build_list(emp_data, 'nome'),
        'total_estoque_geral':  total_e,
        **get_listas_sidebar(dash, Empreendimento),
    })


def mapa_calor(request, dashboard_id):
    dash = get_object_or_404(Dashboard, id=dashboard_id)
    if not _verificar_acesso(request, dash):
        return redirect('lista_dashboards')
    
    # Bloqueio se a aba estiver desativada pelo "Editar Dashboard"
    if not _validar_aba_ativa(dash, 'mapa_calor'):
        messages.warning(request, 'Esta funcionalidade está desativada para este dashboard.')
        return redirect('dashboard', dashboard_id=dash.id)

    qs = aplicar_filtros(Empreendimento.objects.filter(dashboard=dash), request)

    pontos_raw = (
        qs.exclude(latitude=None).exclude(longitude=None)
        .values('nome', 'latitude', 'longitude')
        .annotate(
            total_unidades=Sum('unidades_totais'), total_vendidas=Sum('unidades_vendidas'),
            total_estoque=Sum('estoque'), preco_m2=Avg('preco_medio_m2'), area=Avg('area_unidade'),
        )
    )
    pontos = [{
        'lat': float(p['latitude']), 'lng': float(p['longitude']),
        'nome': p['nome'],
        'pct_vendido': round(p['total_vendidas'] / p['total_unidades'] * 100, 1) if p['total_unidades'] else 0,
        'total_vendidas': p['total_vendidas'], 'total_unidades': p['total_unidades'],
        'total_estoque': p['total_estoque'],
        'preco_m2': float(p['preco_m2']) if p['preco_m2'] else 0,
        'area': float(p['area']) if p['area'] else 0,
    } for p in pontos_raw]

    stats = qs.aggregate(
        total_u=Sum('unidades_totais'), total_e=Sum('estoque'),
        total_v=Sum('unidades_vendidas'), avg_area=Avg('area_unidade'), avg_m2=Avg('preco_medio_m2'),
    )

    return render(request, 'app/mapa_calor.html', {
        'dash': dash, 'usuario': request.user,
        'pontos_json':          json.dumps(pontos),
        'total_unidades':       stats['total_u'] or 0,
        'total_estoque':        stats['total_e'] or 0,
        'total_vendidas':       stats['total_v'] or 0,
        'media_area':           round(stats['avg_area'] or 0, 1),
        'media_m2':             round(float(stats['avg_m2'] or 0), 2),
        'num_empreendimentos':  qs.values('nome').distinct().count(),
        'ranges':               get_ranges(dash, Empreendimento),
        'pm2_min_val':   request.GET.get('pm2_min', ''),
        'pm2_max_val':   request.GET.get('pm2_max', ''),
        'area_min_val':  request.GET.get('area_min', ''),
        'area_max_val':  request.GET.get('area_max', ''),
        'preco_min_val': request.GET.get('preco_min', ''),
        'preco_max_val': request.GET.get('preco_max', ''),
        **get_listas_sidebar(dash, Empreendimento),
    })


def comparativo(request, dashboard_id):
    dash = get_object_or_404(Dashboard, id=dashboard_id)
    if not _verificar_acesso(request, dash):
        return redirect('lista_dashboards')
    
        # Bloqueio se a aba estiver desativada pelo "Editar Dashboard"
    if not _validar_aba_ativa(dash, 'comparativo'):
        messages.warning(request, 'Esta funcionalidade está desativada para este dashboard.')
        return redirect('dashboard', dashboard_id=dash.id)

    data_corte_a = request.GET.get('data_corte_a', '')
    data_corte_b = request.GET.get('data_corte_b', '')
    base = aplicar_filtros(Empreendimento.objects.filter(dashboard=dash), request)

    qs_a = base.filter(data_comercializacao__lte=data_corte_a) if data_corte_a else base
    qs_b = base.filter(data_comercializacao__lte=data_corte_b) if data_corte_b else base

    def calcular_kpis(qs):
        s = qs.aggregate(
            total_u=Sum('unidades_totais'), total_e=Sum('estoque'), total_v=Sum('unidades_vendidas'),
            avg_area=Avg('area_unidade'), avg_m2=Avg('preco_medio_m2'), avg_preco=Avg('preco_unidade'),
        )
        tu = s['total_u'] or 0; tv = s['total_v'] or 0
        vgv_total   = sum((e.unidades_totais or 0) * float(e.preco_unidade or 0) for e in qs)
        vgv_estoque = sum((e.estoque         or 0) * float(e.preco_unidade or 0) for e in qs)
        return {
            'total_u': tu, 'total_e': s['total_e'] or 0, 'total_v': tv,
            'pct_vendido': round(tv / tu * 100, 2) if tu else 0,
            'avg_area': round(float(s['avg_area'] or 0), 2),
            'avg_m2':   round(float(s['avg_m2']   or 0), 2),
            'avg_preco':round(float(s['avg_preco'] or 0), 2),
            'vgv_total':   round(vgv_total   / 1_000_000_000, 2),
            'vgv_estoque': round(vgv_estoque / 1_000_000_000, 2),
        }

    def calcular_faixas(qs):
        resultado = []
        for label, fmin, fmax in FAIXAS_AREA:
            q = qs
            if fmin: q = q.filter(area_unidade__gte=fmin)
            if fmax: q = q.filter(area_unidade__lte=fmax)
            s = q.aggregate(total_u=Sum('unidades_totais'), total_e=Sum('estoque'), avg_m2=Avg('preco_medio_m2'))
            avg_preco   = float(q.aggregate(p=Avg('preco_unidade'))['p'] or 0)
            vgv_total   = sum((e.unidades_totais or 0) * float(e.preco_unidade or 0) for e in q)
            vgv_estoque = sum((e.estoque         or 0) * float(e.preco_unidade or 0) for e in q)
            resultado.append({
                'label': label,
                'vgv_total':   round(vgv_total   / 1_000_000_000, 3),
                'vgv_estoque': round(vgv_estoque / 1_000_000_000, 3),
                'avg_m2':      round(float(s['avg_m2'] or 0), 2),
            })
        return resultado

    datas = base.aggregate(dmin=Min('data_comercializacao'), dmax=Max('data_comercializacao'))

    return render(request, 'app/comparativo.html', {
        'dash': dash, 'usuario': request.user,
        'kpis_a': calcular_kpis(qs_a), 'kpis_b': calcular_kpis(qs_b),
        'faixas_a_json': json.dumps(calcular_faixas(qs_a)),
        'faixas_b_json': json.dumps(calcular_faixas(qs_b)),
        'data_corte_a': data_corte_a, 'data_corte_b': data_corte_b,
        'data_min': datas['dmin'].strftime('%Y-%m-%d') if datas['dmin'] else '',
        'data_max': datas['dmax'].strftime('%Y-%m-%d') if datas['dmax'] else '',
        **get_listas_sidebar(dash, Empreendimento),
    })


def evolucao(request, dashboard_id):
    dash = get_object_or_404(Dashboard, id=dashboard_id)
    if not _verificar_acesso(request, dash):
        return redirect('lista_dashboards')
    
    # Bloqueio se a aba estiver desativada pelo "Editar Dashboard"
    if not _validar_aba_ativa(dash, 'evolucao'):
        messages.warning(request, 'Esta funcionalidade está desativada para este dashboard.')
        return redirect('dashboard', dashboard_id=dash.id)

    datas_corte = [request.GET.get(f'data_{i}', '') for i in ['1','2','3'] if request.GET.get(f'data_{i}')]
    base = aplicar_filtros(Empreendimento.objects.filter(dashboard=dash), request)

    def calcular_kpis(qs):
        s = qs.aggregate(
            total_u=Sum('unidades_totais'), total_e=Sum('estoque'),
            total_v=Sum('unidades_vendidas'), avg_area=Avg('area_unidade'), avg_m2=Avg('preco_medio_m2'),
        )
        tu = s['total_u'] or 0; tv = s['total_v'] or 0
        fases = {f['fase_obra']: f['n'] for f in qs.values('fase_obra').annotate(n=Sum('unidades_totais')).order_by('-n') if f['fase_obra']}
        return {
            'total_u': tu, 'total_e': s['total_e'] or 0, 'total_v': tv,
            'avg_area': round(float(s['avg_area'] or 0), 2),
            'avg_m2':   round(float(s['avg_m2']   or 0), 2),
            'num_emp':  qs.values('nome').distinct().count(),
            'pct_v':    round(tv / tu * 100, 2) if tu else 0,
            'fases':    fases,
        }

    def calcular_faixas(qs):
        resultado = []
        for label, fmin, fmax in FAIXAS_AREA:
            q = qs
            if fmin: q = q.filter(area_unidade__gte=fmin)
            if fmax: q = q.filter(area_unidade__lte=fmax)
            s = q.aggregate(
                total_u=Sum('unidades_totais'), total_e=Sum('estoque'), total_v=Sum('unidades_vendidas'),
                avg_m2=Avg('preco_medio_m2'), avg_p=Avg('preco_unidade'), avg_a=Avg('area_unidade'),
            )
            resultado.append({
                'label': label, 'total_u': s['total_u'] or 0, 'total_e': s['total_e'] or 0,
                'total_v': s['total_v'] or 0,
                'avg_m2': round(float(s['avg_m2'] or 0), 0),
                'avg_p':  round(float(s['avg_p']  or 0), 0),
                'avg_a':  round(float(s['avg_a']  or 0), 2),
            })
        return resultado

    periodos = [{'label': d, 'kpis': calcular_kpis(base.filter(data_comercializacao__lte=d)), 'faixas': calcular_faixas(base.filter(data_comercializacao__lte=d))} for d in datas_corte] or \
               [{'label': 'Total', 'kpis': calcular_kpis(base), 'faixas': calcular_faixas(base)}]

    def variacao(a, b):
        return round(((b - a) / abs(a)) * 100, 2) if a and a != 0 else 0

    var_kpis, tabela_var = {}, []
    if len(periodos) >= 2:
        ka, kb = periodos[-2]['kpis'], periodos[-1]['kpis']
        var_kpis = {k: variacao(ka[k], kb[k]) for k in ['total_u','total_e','total_v','avg_area','avg_m2','num_emp']}
        fa, fb = periodos[-2]['faixas'], periodos[-1]['faixas']
        tabela_var = [{
            'label': f['label'], 'total_e': f['total_e'], 'total_v': f['total_v'], 'total_u': f['total_u'],
            'var_u': variacao(a['total_u'], f['total_u']), 'avg_p': f['avg_p'],
            'var_p': variacao(a['avg_p'], f['avg_p']), 'avg_m2': f['avg_m2'],
            'var_m2': variacao(a['avg_m2'], f['avg_m2']), 'avg_a': f['avg_a'],
            'var_a': variacao(a['avg_a'], f['avg_a']),
        } for f, a in zip(fb, fa)]
        tabela_var.append({
            'label': 'Total', 'total_e': sum(r['total_e'] for r in tabela_var),
            'total_v': sum(r['total_v'] for r in tabela_var), 'total_u': sum(r['total_u'] for r in tabela_var),
            'var_u': var_kpis.get('total_u', 0), 'avg_p': 0, 'var_p': 0,
            'avg_m2': 0, 'var_m2': 0, 'avg_a': 0, 'var_a': 0, 'is_total': True,
        })

    datas = base.aggregate(dmin=Min('data_comercializacao'), dmax=Max('data_comercializacao'))
    return render(request, 'app/evolucao.html', {
        'dash': dash, 'usuario': request.user,
        'periodos_json': json.dumps([{'label': p['label'], 'kpis': p['kpis']} for p in periodos]),
        'kpis_atual': periodos[-1]['kpis'] if periodos else {},
        'var_kpis': var_kpis, 'tabela_var': tabela_var, 'datas_corte': datas_corte,
        'data_min': datas['dmin'].strftime('%Y-%m-%d') if datas['dmin'] else '',
        'data_max': datas['dmax'].strftime('%Y-%m-%d') if datas['dmax'] else '',
        **get_listas_sidebar(dash, Empreendimento),
    })