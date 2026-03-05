from django.shortcuts import render, redirect
from django.db.models import Avg, Sum
from .models import Empreendimento
from .utils import mapear_colunas_com_ia, limpar_valor, buscar_coordenadas, analisar_dados_com_gemini
import pandas as pd

def dashboard(request):
    dados = Empreendimento.objects.all().order_by('-data_importacao')
    
    # --- Aplicar os Filtros da URL ---
    if request.GET.get('construtora'):
        dados = dados.filter(construtora=request.GET.get('construtora'))
    if request.GET.get('bairro'):
        dados = dados.filter(bairro=request.GET.get('bairro'))
    if request.GET.get('quartos'):
        dados = dados.filter(quartos=request.GET.get('quartos'))
    if request.GET.get('preco_max'):
        dados = dados.filter(preco_unidade__lte=request.GET.get('preco_max'))

    # --- Cálculos para os Cards ---
    total_unidades = dados.aggregate(Sum('unidades_totais'))['unidades_totais__sum'] or 0
    total_estoque = dados.aggregate(Sum('estoque'))['estoque__sum'] or 0
    total_vendidas = dados.aggregate(Sum('unidades_vendidas'))['unidades_vendidas__sum'] or 0
    media_m2 = dados.aggregate(Avg('preco_medio_m2'))['preco_medio_m2__avg'] or 0

    # --- Listas para os Filtros do BI ---
    construtoras = Empreendimento.objects.values_list('construtora', flat=True).distinct().exclude(construtora__isnull=True)
    bairros = Empreendimento.objects.values_list('bairro', flat=True).distinct()
    quartos_list = Empreendimento.objects.values_list('quartos', flat=True).distinct().exclude(quartos__isnull=True)

    context = {
        'dados': dados,
        'total_unidades': total_unidades,
        'total_estoque': total_estoque,
        'total_vendidas': total_vendidas,
        'media_m2': media_m2,
        'construtoras': sorted(construtoras),
        'bairros': sorted(bairros),
        'quartos_list': sorted(quartos_list),
        'insight': request.session.get('ultimo_insight', 'Faça upload para análise.')
    }
    return render(request, 'app/dashboard.html', context)

from django.shortcuts import render, redirect
from .models import Empreendimento
from .utils import mapear_colunas_com_ia, limpar_valor, buscar_coordenadas, analisar_dados_com_gemini
import pandas as pd

def upload_planilha(request):
    if request.method == 'POST' and request.FILES.get('planilha'):
        arquivo = request.FILES['planilha']
        
        # 1. Leitura do arquivo (Aceita Excel e CSV)
        df = pd.read_excel(arquivo) if arquivo.name.endswith('.xlsx') else pd.read_csv(arquivo)
        
        # 2. IA identifica as colunas reais
        mapeamento = mapear_colunas_com_ia(df.columns.tolist())
        
        objetos = []
        for _, row in df.iterrows():
            nome_val = row.get(mapeamento.get('nome'))
            if not nome_val: continue

            # --- Tratamento Especial para DATA ---
            data_raw = row.get(mapeamento.get('data_entrega'))
            data_final = None
            if pd.notna(data_raw):
                try:
                    # Converte diversos formatos de data automaticamente
                    data_final = pd.to_datetime(data_raw).date()
                except:
                    data_final = None

            # --- Geolocalização ---
            rua = str(row.get(mapeamento.get('endereco'), ''))
            bairro = str(row.get(mapeamento.get('bairro'), ''))
            cidade = str(row.get(mapeamento.get('cidade'), 'Recife'))
            lat, lon = buscar_coordenadas(rua, bairro, cidade)

            # Pega o que a IA mapeou, mas garante que se vier vazio use 'VA'
            cat_temp = row.get(mapeamento.get('categoria'), 'VA')

            # Se o que veio da planilha for muito longo (ex: "Apartamento Residencial"), 
            # pegamos apenas os primeiros 20 caracteres para não estourar o banco
            categoria_final = str(cat_temp)[:20]

            # 3. Criação do Objeto com todos os campos do BI
            obj = Empreendimento(
                nome=nome_val,
                categoria=row.get(mapeamento.get('categoria'), 'VA'),
                construtora=row.get(mapeamento.get('construtora')),
                endereco=rua,
                bairro=bairro,
                cidade=cidade,
                data_entrega=data_final,
                unidades_totais=int(row.get(mapeamento.get('unidades_totais'), 0) or 0),
                unidades_vendidas=int(row.get(mapeamento.get('unidades_vendidas'), 0) or 0),
                preco_medio_m2=limpar_valor(row.get(mapeamento.get('preco_m2'))),
                preco_unidade=limpar_valor(row.get(mapeamento.get('preco_unidade'))),
                area_unidade=limpar_valor(row.get(mapeamento.get('area_unidade'))),
                estoque=int(row.get(mapeamento.get('estoque'), 0) or 0),
                quartos=int(row.get(mapeamento.get('quartos'), 0) or 0),
                vagas_garagem=row.get(mapeamento.get('vagas_garagem')),
                fase_obra=row.get(mapeamento.get('fase_obra')),
                latitude=lat,
                longitude=lon
            )
            objetos.append(obj)
        
        # 4. Salvamento em Massa
        if objetos:
            Empreendimento.objects.bulk_create(objetos)

        # 5. Insight da IA (Enviando dados mais ricos)
        colunas_ia = [c for c in [mapeamento.get('nome'), mapeamento.get('preco_m2'), mapeamento.get('bairro')] if c in df.columns]
        amostra = df[colunas_ia].head(20).to_string()
        request.session['ultimo_insight'] = analisar_dados_com_gemini(amostra)
        
        return redirect('dashboard')

    return render(request, 'app/upload.html')

def limpar_banco(request):
    Empreendimento.objects.all().delete()
    # Limpa também o insight da IA na sessão para não confundir
    if 'ultimo_insight' in request.session:
        del request.session['ultimo_insight']
    return redirect('dashboard')