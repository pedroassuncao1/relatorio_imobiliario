import os
import pandas as pd
from google import genai
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import json

# ==============================
# CONFIGURAÇÕES GLOBAIS
# ==============================

MODEL_NAME = "gemini-2.0-flash"

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)

# ==============================
# TESTE DE CONEXÃO (AO INICIAR)
# ==============================

try:
    test_response = client.models.generate_content(
        model=MODEL_NAME,
        contents="Teste de conexão"
    )
    print("✅ CONEXÃO GEMINI ESTABELECIDA.")
except Exception as e:
    print(f"❌ ERRO NA IA: {e}")

# ==============================
# CONFIGURAÇÃO DO GEOCODER
# ==============================

geolocator = Nominatim(user_agent="meu_app_imobiliario_final")
geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1)

# ==============================
# FUNÇÕES
# ==============================

def buscar_coordenadas(rua, bairro, cidade):
    try:
        if not rua and not bairro:
            return None, None

        # Normalização leve (sem forçar estado)
        rua = str(rua or "").replace("nº", "").replace("Nº", "").replace("°", "").strip()
        bairro = str(bairro or "").strip()
        cidade = str(cidade or "").strip()

        # Remove possíveis siglas duplicadas tipo Recife/PE ou Recife-PE
        cidade = cidade.replace("/", " ").replace("-", " ")

        endereco_formatado = f"{rua}, {bairro}, {cidade}, Brasil"

        print("GEOCODING:", endereco_formatado)

        location = geocode(endereco_formatado)

        if location:
            print("OK:", location.latitude, location.longitude)
            return location.latitude, location.longitude

        # 🔁 Fallback inteligente
        endereco_fallback = f"{bairro}, {cidade}, Brasil"
        print("FALLBACK:", endereco_fallback)

        location = geocode(endereco_fallback)

        if location:
            return location.latitude, location.longitude

    except Exception as e:
        print("Erro geocode:", e)

    return None, None


def limpar_valor(valor):
    if pd.isna(valor) or valor == "":
        return 0

    if isinstance(valor, str):
        valor = (
            valor.replace('R$', '')
            .replace('.', '')
            .replace(',', '.')
            .replace('\xa0', '')
            .strip()
        )

    try:
        return float(valor)
    except Exception:
        return 0


def mapear_colunas_com_ia(colunas):
    prompt = f"""
    Analise estas colunas de uma planilha imobiliária: {colunas}
    
    Seu objetivo é mapear essas colunas para os seguintes campos do sistema:
    - nome, categoria, construtora, endereco, bairro, cidade
    - unidades_totais, unidades_vendidas, preco_m2, preco_unidade
    - area_unidade, estoque, quartos, vagas_garagem, fase_obra, data_entrega
    
    REGRAS CRÍTICAS:
    1. Retorne APENAS o objeto JSON puro.
    2. Use exatamente os nomes dos campos listados acima como chaves.
    3. Se não encontrar uma correspondência óbvia para um campo, use null como valor.
    4. Para 'data_entrega', procure colunas como 'Previsão', 'Entrega' ou 'Data'.
    
    Exemplo de formato:
    {{
        "nome": "Nome do Empreendimento",
        "preco_m2": "Valor m2",
        "data_entrega": "Data de Lançamento",
        "vagas_garagem": null
    }}
    """

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt
        )

        # Limpeza de markdown
        txt = (
            response.text
            .replace('```json', '')
            .replace('```', '')
            .strip()
        )

        mapeamento = json.loads(txt)

        # SE a IA retornar uma lista com um dicionário dentro [{}], pegamos o primeiro item
        if isinstance(mapeamento, list) and len(mapeamento) > 0:
            mapeamento = mapeamento[0]
        
        # Garante que retornamos um dicionário, mesmo que vazio
        return mapeamento if isinstance(mapeamento, dict) else {}

    except Exception as e:
        print(f"Erro no processamento do JSON da IA: {e}")
        return {}


def analisar_dados_com_gemini(resumo_texto):
    prompt = f"""
    Resuma estes dados imobiliários em 3 pontos chave:
    {resumo_texto}
    """

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt
        )

        return response.text

    except Exception:
        return "Insight indisponível."