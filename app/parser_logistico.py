"""

Lê uma planilha logística e cria os registros EmpreendimentoLogistico.
Estrutura esperada da planilha:
  - Linha com Nº preenchido = empreendimento-raiz
  - Linhas seguintes com Nº vazio = tipologias do mesmo empreendimento
"""

import math
import logging
from decimal import Decimal, InvalidOperation

from openpyxl import load_workbook

from app.models import Dashboard, EmpreendimentoLogistico
from app.utils import buscar_coordenadas

logger = logging.getLogger(__name__)


# ── Colunas esperadas (índice 0-based) ──────────────────────────────────────
COL = {
    'numero':       0,
    'nome':         1,
    'endereco':     2,
    'cidade':       3,
    'construtora':  4,
    'proprietario': 5,
    'fase_obra':    6,
    'num_galpoes':  7,
    'num_modulos':  8,
    'modulos_ocupados':    9,
    'modulos_disponiveis': 10,
    'preco_m2_locacao':    11,
    'preco_m2_condominio': 12,
    'preco_m2_iptu':       13,
    'preco_locacao':       14,
    'preco_condominio':    15,
    'preco_iptu':          16,
    'area_modulo_m2':      17,
    'abl_m2':              18,
    'vacancia':            19,
}


def _safe_decimal(val):
    """Converte valor para Decimal, retorna None se inválido/NI."""
    if val is None or str(val).strip().upper() in ('NI', '', 'N/A', '-'):
        return None
    try:
        return Decimal(str(val))
    except InvalidOperation:
        return None


def _safe_float(val):
    """Converte valor para float, retorna None se inválido/NI."""
    if val is None or str(val).strip().upper() in ('NI', '', 'N/A', '-'):
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _safe_int(val):
    """Converte valor para int, retorna None se inválido/NI."""
    if val is None or str(val).strip().upper() in ('NI', '', 'N/A', '-'):
        return None
    try:
        return int(float(str(val)))
    except (ValueError, TypeError):
        return None


def _haversine(lat1, lon1, lat2, lon2):
    """Distância em km entre dois pontos (Haversine)."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi  = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def importar_planilha_logistica(arquivo, dashboard: Dashboard) -> dict:
    """
    Lê o arquivo xlsx e importa os dados para o banco.

    Retorna dict com:
        empreendimentos_criados: int
        tipologias_criadas: int
        erros: list[str]
    """
    wb = load_workbook(arquivo, read_only=True, data_only=True)
    ws = wb.active

    linhas = list(ws.iter_rows(min_row=2, values_only=True))  # pula cabeçalho

    empreendimentos_criados = 0
    tipologias_criadas = 0
    erros = []

    emp_atual = None  # EmpreendimentoLogistico raiz atual

    ref_lat = dashboard.ref_latitude
    ref_lon = dashboard.ref_longitude
    tem_ref = ref_lat is not None and ref_lon is not None

    for idx, row in enumerate(linhas, start=2):
        try:
            numero = _safe_int(row[COL['numero']])
            nome   = str(row[COL['nome']] or '').strip()

            if not nome:
                continue  # linha vazia

            is_raiz = numero is not None  # linha principal do empreendimento

            # ── Campos comuns ───────────────────────────────────────────
            fase_obra    = str(row[COL['fase_obra']] or '').strip() or None
            num_modulos  = _safe_int(row[COL['num_modulos']])
            preco_m2_loc = _safe_decimal(row[COL['preco_m2_locacao']])
            preco_m2_cnd = _safe_decimal(row[COL['preco_m2_condominio']])
            preco_m2_ipt = _safe_decimal(row[COL['preco_m2_iptu']])
            preco_loc    = _safe_decimal(row[COL['preco_locacao']])
            preco_cnd    = _safe_decimal(row[COL['preco_condominio']])
            preco_ipt    = _safe_decimal(row[COL['preco_iptu']])
            area_mod     = _safe_float(row[COL['area_modulo_m2']])
            abl          = _safe_float(row[COL['abl_m2']])

            if is_raiz:
                # ── Campos só do empreendimento-raiz ────────────────────
                endereco    = str(row[COL['endereco']] or '').strip() or None
                cidade      = str(row[COL['cidade']] or '').strip() or None
                construtora = str(row[COL['construtora']] or '').strip() or None
                proprietario = str(row[COL['proprietario']] or '').strip() or None
                num_galpoes  = _safe_int(row[COL['num_galpoes']])
                mod_ocupados = _safe_int(row[COL['modulos_ocupados']])
                mod_disp     = _safe_int(row[COL['modulos_disponiveis']])
                vacancia     = _safe_float(row[COL['vacancia']])

                # Geocoding
                lat, lon = None, None
                if endereco and cidade:
                    endereco_completo = f"{endereco}, {cidade}"
                    try:
                        lat, lon = buscar_coordenadas(endereco, '', cidade)
                    except Exception as e:
                        logger.warning(f"Geocoding falhou para '{nome}': {e}")

                # Distância até ponto de referência
                distancia_km = None
                if tem_ref and lat and lon:
                    distancia_km = round(_haversine(lat, lon, ref_lat, ref_lon), 2)

                emp_atual = EmpreendimentoLogistico.objects.create(
                    dashboard=dashboard,
                    empreendimento_principal=None,
                    numero=numero,
                    nome=nome,
                    endereco=endereco,
                    cidade=cidade,
                    construtora=construtora,
                    proprietario=proprietario,
                    fase_obra=fase_obra,
                    num_galpoes=num_galpoes,
                    num_modulos=num_modulos,
                    modulos_ocupados=mod_ocupados,
                    modulos_disponiveis=mod_disp,
                    preco_m2_locacao=preco_m2_loc,
                    preco_m2_condominio=preco_m2_cnd,
                    preco_m2_iptu=preco_m2_ipt,
                    preco_locacao=preco_loc,
                    preco_condominio=preco_cnd,
                    preco_iptu=preco_ipt,
                    area_modulo_m2=area_mod,
                    abl_m2=abl,
                    vacancia=vacancia,
                    latitude=lat,
                    longitude=lon,
                    distancia_ref_km=distancia_km,
                )
                empreendimentos_criados += 1

            else:
                # ── Tipologia: sub-linha do empreendimento atual ─────────
                if emp_atual is None:
                    erros.append(f"Linha {idx}: tipologia sem empreendimento-raiz anterior — ignorada.")
                    continue

                EmpreendimentoLogistico.objects.create(
                    dashboard=dashboard,
                    empreendimento_principal=emp_atual,
                    numero=None,
                    nome=nome,
                    endereco=emp_atual.endereco,
                    cidade=emp_atual.cidade,
                    construtora=emp_atual.construtora,
                    proprietario=emp_atual.proprietario,
                    fase_obra=fase_obra,
                    num_galpoes=None,
                    num_modulos=num_modulos,
                    modulos_ocupados=None,
                    modulos_disponiveis=None,
                    preco_m2_locacao=preco_m2_loc,
                    preco_m2_condominio=preco_m2_cnd,
                    preco_m2_iptu=preco_m2_ipt,
                    preco_locacao=preco_loc,
                    preco_condominio=preco_cnd,
                    preco_iptu=preco_ipt,
                    area_modulo_m2=area_mod,
                    abl_m2=abl,
                    vacancia=None,
                    latitude=emp_atual.latitude,
                    longitude=emp_atual.longitude,
                    distancia_ref_km=emp_atual.distancia_ref_km,
                )
                tipologias_criadas += 1

        except Exception as e:
            erros.append(f"Linha {idx}: erro inesperado — {e}")
            logger.exception(f"Erro na linha {idx} da planilha logística")

    return {
        'empreendimentos_criados': empreendimentos_criados,
        'tipologias_criadas': tipologias_criadas,
        'erros': erros,
    }