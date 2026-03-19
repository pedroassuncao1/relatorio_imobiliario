import os
import pandas as pd
from google import genai
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import json
import googlemaps

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

geolocator = Nominatim(
    user_agent="meu_app_imobiliario_final",
    timeout=10  
)
geocode = RateLimiter(
    geolocator.geocode,
    min_delay_seconds=1,
    max_retries=2,
    error_wait_seconds=3
)

# ==============================
# FUNÇÕES
# ==============================

_gmaps_client = None
_cache_coordenadas = {}

def get_gmaps():
    global _gmaps_client
    if _gmaps_client is None:
        import os
        api_key = os.getenv('GOOGLE_MAPS_API_KEY')
        if api_key:
            _gmaps_client = googlemaps.Client(key=api_key)
            print("✅ GEOCODER: Google Maps API ativado")
        else:
            print("⚠️  GEOCODER: Google Maps API key não encontrada — usando Nominatim como fallback")
    return _gmaps_client


def buscar_coordenadas(rua, bairro, cidade):
    try:
        if not rua and not bairro:
            return None, None

        rua    = str(rua or "").strip()
        bairro = str(bairro or "").strip()
        cidade = str(cidade or "").strip()

        cache_key = f"{rua}|{bairro}|{cidade}"
        if cache_key in _cache_coordenadas:
            print(f"📦 CACHE HIT: {cache_key}")
            return _cache_coordenadas[cache_key]

        gmaps = get_gmaps()

        if gmaps:
            endereco = f"{rua}, {bairro}, {cidade}"
            print(f"🗺️  GOOGLE: {endereco}")

            result = gmaps.geocode(endereco, language='pt-BR')

            if result:
                lat = result[0]['geometry']['location']['lat']
                lng = result[0]['geometry']['location']['lng']
                tipo = result[0]['geometry']['location_type']
                print(f"✅ OK ({tipo}): {lat}, {lng}")
                _cache_coordenadas[cache_key] = (lat, lng)
                return lat, lng

            # Fallback bairro+cidade
            fallback_key = f"|{bairro}|{cidade}"
            if fallback_key in _cache_coordenadas:
                print(f"📦 CACHE HIT FALLBACK: {fallback_key}")
                return _cache_coordenadas[fallback_key]

            print(f"⚠️  GOOGLE sem resultado — tentando só bairro: {bairro}, {cidade}")
            result = gmaps.geocode(f"{bairro}, {cidade}", language='pt-BR')
            if result:
                lat = result[0]['geometry']['location']['lat']
                lng = result[0]['geometry']['location']['lng']
                print(f"✅ FALLBACK OK: {lat}, {lng}")
                _cache_coordenadas[fallback_key] = (lat, lng)
                return lat, lng

            print(f"❌ GOOGLE: nenhum resultado para {endereco}")

        else:
            # Nominatim
            from geopy.geocoders import Nominatim
            from geopy.extra.rate_limiter import RateLimiter

            geolocator = Nominatim(user_agent="core_bi", timeout=10)
            geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1)

            endereco = f"{rua}, {bairro}, {cidade}"
            print(f"🔍 NOMINATIM: {endereco}")
            location = geocode(endereco)

            if location:
                print(f"✅ OK: {location.latitude}, {location.longitude}")
                _cache_coordenadas[cache_key] = (location.latitude, location.longitude)
                return location.latitude, location.longitude

            print(f"⚠️  NOMINATIM sem resultado — tentando fallback: {bairro}, {cidade}")
            location = geocode(f"{bairro}, {cidade}")
            if location:
                print(f"✅ FALLBACK OK: {location.latitude}, {location.longitude}")
                return location.latitude, location.longitude

            print(f"❌ NOMINATIM: nenhum resultado")

    except Exception as e:
        print(f"❌ ERRO GEOCODE: {e}")

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
    - inicio_comercializacao

    IMPORTANTE: Na coluna de 'quartos', podem existir valores como 'STUDIO'. 
    Apenas identifique a coluna correta.
    
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