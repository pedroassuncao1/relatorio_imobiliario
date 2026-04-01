from django import template

register = template.Library()


@register.filter
def fmt_m2(value):
    """Formata um número como inteiro com separador de milhar pt-BR (ponto).
    Retorna string vazia para valores nulos/inválidos (compatível com |default:'—').
    Exemplo: 141455 → '141.455'
    """
    try:
        n = int(round(float(value)))
        return f"{n:,}".replace(",", ".")
    except (TypeError, ValueError):
        return ""
