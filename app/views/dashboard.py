from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Avg, Sum
from collections import defaultdict
from ..models import Dashboard, AcessoDashboard, Empreendimento
from .helpers import (
    admin_required, aplicar_filtros, get_listas_sidebar,
    tratar_quartos, tratar_inteiro
)
from ..utils import mapear_colunas_com_ia, limpar_valor, buscar_coordenadas
import pandas as pd
import json


def lista_dashboards(request):
    # 1. Se for admin, pega todos os dashboards
    if request.user.is_admin():
        dashboards = Dashboard.objects.all().order_by('-criado_em')
    else:
        # 2. Se for viewer (como o Silvestre), filtra apenas os que ele tem acesso
        ids_permitidos = AcessoDashboard.objects.filter(usuario=request.user).values_list('dashboard_id', flat=True)
        dashboards = Dashboard.objects.filter(id__in=ids_permitidos).order_by('-criado_em')

    # ── DEFINIÇÃO EXATA CONFORME SEU PRINT ──
    abas_disponiveis = [
        {'slug': 'dashboard',    'label': 'Mapa & KPIs'},
        {'slug': 'tabela',       'label': 'Tabela Analítica'},
        {'slug': 'graficos',     'label': 'Gráficos & Análise'},
        {'slug': 'pricing',      'label': 'Pricing'},
        {'slug': 'share_estoque','label': 'Share de Estoque'},
        {'slug': 'mapa_calor',   'label': 'Mapa de Calor'},
        {'slug': 'comparativo',  'label': 'Comparativo'},
        {'slug': 'evolucao',     'label': 'Evolução'},
        {'slug': 'analise_preco','label': 'Análise de Preço'},
    ]

    return render(request, 'app/lista_dashboards.html', {
        'dashboards': dashboards,
        'abas_disponiveis': abas_disponiveis,
        'abas_disponiveis_json': json.dumps(abas_disponiveis),
        'usuario': request.user
    })

def _verificar_acesso(request, dash):
    if not request.user.is_admin():
        if not AcessoDashboard.objects.filter(usuario=request.user, dashboard=dash).exists():
            messages.error(request, 'Você não tem acesso a este dashboard.')
            return False
    return True


def dashboard(request, dashboard_id):
    dash = get_object_or_404(Dashboard, id=dashboard_id)
    if not _verificar_acesso(request, dash):
        return redirect('lista_dashboards')

    dados_queryset = aplicar_filtros(
        Empreendimento.objects.filter(dashboard=dash).order_by('-data_importacao'), request
    )

    stats = dados_queryset.aggregate(
        total_u=Sum('unidades_totais'), total_e=Sum('estoque'),
        total_v=Sum('unidades_vendidas'), avg_area=Avg('area_unidade'), avg_m2=Avg('preco_medio_m2')
    )
    fases_lista = sorted(
        Empreendimento.objects.filter(dashboard=dash)
        .values_list('fase_obra', flat=True).distinct().exclude(fase_obra__isnull=True)
    )

    return render(request, 'app/dashboard.html', {
        'dash': dash, 'dados': dados_queryset,
        'total_unidades':      stats['total_u'] or 0,
        'total_estoque':       stats['total_e'] or 0,
        'total_vendidas':      stats['total_v'] or 0,
        'media_area':          stats['avg_area'] or 0,
        'media_m2':            stats['avg_m2'] or 0,
        'num_empreendimentos': dados_queryset.values('nome').distinct().count(),
        'lista_fases':         fases_lista,
        'lista_contagem_fases': [dados_queryset.filter(fase_obra=f).count() for f in fases_lista],
        'usuario': request.user,
        **get_listas_sidebar(dash, Empreendimento),
    })


def tabela(request, dashboard_id):
    dash = get_object_or_404(Dashboard, id=dashboard_id)
    if not _verificar_acesso(request, dash):
        return redirect('lista_dashboards')

    dados_qs = aplicar_filtros(Empreendimento.objects.filter(dashboard=dash), request)
    todos_registros = list(dados_qs.values(
        'bairro', 'fase_obra', 'nome', 'construtora',
        'estoque', 'unidades_totais', 'unidades_vendidas',
        'preco_medio_m2', 'area_unidade'
    ))

    total_unidades = sum(r['unidades_totais'] or 0 for r in todos_registros)
    total_estoque  = sum(r['estoque'] or 0 for r in todos_registros)
    total_vendidas = sum(r['unidades_vendidas'] or 0 for r in todos_registros)
    pct_vendido_total = round((total_vendidas / total_unidades * 100), 2) if total_unidades else 0
    m2_vals   = [float(r['preco_medio_m2']) for r in todos_registros if r['preco_medio_m2']]
    area_vals = [float(r['area_unidade'])   for r in todos_registros if r['area_unidade']]
    media_m2   = round(sum(m2_vals)   / len(m2_vals),   2) if m2_vals   else 0
    media_area = round(sum(area_vals) / len(area_vals), 2) if area_vals else 0

    def agg(rows):
        tot = sum(r['unidades_totais'] or 0 for r in rows)
        est = sum(r['estoque'] or 0 for r in rows)
        ven = sum(r['unidades_vendidas'] or 0 for r in rows)
        m2s = [float(r['preco_medio_m2']) for r in rows if r['preco_medio_m2']]
        ars = [float(r['area_unidade'])   for r in rows if r['area_unidade']]
        return {
            'total': tot, 'estoque': est, 'vendidas': ven,
            'share': round(tot / total_unidades * 100, 2) if total_unidades else 0,
            'pct_vend': round(ven / tot * 100, 2) if tot else 0,
            'm2': round(sum(m2s) / len(m2s), 2) if m2s else 0,
            'area': round(sum(ars) / len(ars), 2) if ars else 0,
        }

    bairro_map = defaultdict(list)
    for r in todos_registros:
        bairro_map[r['bairro'] or 'Sem Bairro'].append(r)

    tabela_dados = []
    for bairro_nome in sorted(bairro_map.keys()):
        bairro_rows = bairro_map[bairro_nome]
        b = agg(bairro_rows); b['nome'] = bairro_nome
        fase_map = defaultdict(list)
        for r in bairro_rows:
            fase_map[r['fase_obra'] or 'Sem Fase'].append(r)
        b['fases'] = []
        for fase_nome in sorted(fase_map.keys()):
            fase_rows = fase_map[fase_nome]
            f = agg(fase_rows); f['nome'] = fase_nome
            emp_map = defaultdict(list)
            for r in fase_rows:
                emp_map[r['nome'] or 'Sem Nome'].append(r)
            f['empreendimentos'] = []
            for emp_nome in sorted(emp_map.keys()):
                emp_rows = emp_map[emp_nome]
                e = agg(emp_rows); e['nome'] = emp_nome
                const_map = defaultdict(list)
                for r in emp_rows:
                    const_map[r['construtora'] or 'Sem Construtora'].append(r)
                e['construtoras'] = []
                for const_nome in sorted(const_map.keys()):
                    c = agg(const_map[const_nome]); c['nome'] = const_nome
                    e['construtoras'].append(c)
                f['empreendimentos'].append(e)
            b['fases'].append(f)
        tabela_dados.append(b)

    return render(request, 'app/tabela.html', {
        'dash': dash, 'tabela_dados': tabela_dados,
        'total_unidades': total_unidades, 'total_estoque': total_estoque,
        'total_vendidas': total_vendidas, 'pct_vendido_total': pct_vendido_total,
        'media_m2': media_m2, 'media_area': media_area,
        'usuario': request.user,
        **get_listas_sidebar(dash, Empreendimento),
    })


@admin_required
def upload_planilha(request):
    if request.method == 'POST' and request.FILES.get('planilha'):
        arquivo       = request.FILES['planilha']
        nome_dash     = request.POST.get('nome_dashboard', arquivo.name)
        cidade_padrao = request.POST.get('cidade', '').strip()
        estado_padrao = request.POST.get('estado', '').strip().upper()

        dash = Dashboard.objects.create(nome=nome_dash, criado_por=request.user)
        df   = pd.read_excel(arquivo) if arquivo.name.endswith('.xlsx') else pd.read_csv(arquivo)
        mapeamento = mapear_colunas_com_ia(df.columns.tolist())

        objetos = []
        for _, row in df.iterrows():
            nome_val = row.get(mapeamento.get('nome'))
            if not nome_val:
                continue

            def parse_date(col):
                raw = row.get(mapeamento.get(col))
                if pd.notna(raw):
                    try: return pd.to_datetime(raw, dayfirst=True).date()
                    except: pass
                return None

            rua             = str(row.get(mapeamento.get('endereco'), ''))
            bairro          = str(row.get(mapeamento.get('bairro'), ''))
            cidade_planilha = str(row.get(mapeamento.get('cidade'), '') or '').strip()
            cidade          = cidade_planilha if cidade_planilha else cidade_padrao
            cidade_geo      = f"{cidade}, {estado_padrao}, Brasil"
            lat, lon        = buscar_coordenadas(rua, bairro, cidade_geo)

            objetos.append(Empreendimento(
                dashboard            = dash,
                nome                 = nome_val,
                categoria            = str(row.get(mapeamento.get('categoria'), 'VA'))[:20],
                construtora          = row.get(mapeamento.get('construtora')),
                endereco             = rua, bairro=bairro, cidade=cidade,
                data_entrega         = parse_date('data_entrega'),
                data_comercializacao = parse_date('inicio_comercializacao'),
                unidades_totais      = tratar_inteiro(row.get(mapeamento.get('unidades_totais'), 0)),
                unidades_vendidas    = tratar_inteiro(row.get(mapeamento.get('unidades_vendidas'), 0)),
                preco_medio_m2       = limpar_valor(row.get(mapeamento.get('preco_m2'))),
                preco_unidade        = limpar_valor(row.get(mapeamento.get('preco_unidade'))),
                area_unidade         = limpar_valor(row.get(mapeamento.get('area_unidade'))),
                estoque              = tratar_inteiro(row.get(mapeamento.get('estoque'), 0)),
                quartos              = tratar_quartos(row.get(mapeamento.get('quartos'))),
                vagas_garagem        = row.get(mapeamento.get('vagas_garagem')),
                fase_obra            = row.get(mapeamento.get('fase_obra')),
                latitude=lat, longitude=lon,
            ))

        if objetos:
            Empreendimento.objects.bulk_create(objetos)
        return redirect('lista_dashboards')

    return render(request, 'app/upload.html', {'usuario': request.user})