from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def brl(valor):
    """Formata um número como moeda brasileira: 1234.5 -> R$ 1.234,50."""
    if valor is None or valor == '':
        return ''
    try:
        valor = Decimal(valor)
    except (InvalidOperation, TypeError, ValueError):
        return valor
    texto = f'{valor:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    return f'R$ {texto}'


@register.filter
def nota(valor):
    """Média com uma casa decimal e vírgula: 4.25 -> 4,3."""
    if valor is None:
        return ''
    return f'{float(valor):.1f}'.replace('.', ',')


@register.inclusion_tag('partials/estrelas.html')
def estrelas(valor, tamanho='md'):
    valor = float(valor or 0)
    cheias = int(round(valor))
    return {'cheias': range(cheias), 'vazias': range(5 - cheias), 'valor': valor, 'tamanho': tamanho}


@register.inclusion_tag('partials/campo.html')
def campo(field, classe_extra=''):
    if field.errors:
        attrs = field.field.widget.attrs
        if 'is-invalid' not in attrs.get('class', ''):
            attrs['class'] = (attrs.get('class', '') + ' is-invalid').strip()
            attrs['aria-invalid'] = 'true'
    return {'field': field, 'classe_extra': classe_extra}


@register.filter
def iniciais(nome):
    partes = [p for p in str(nome).replace('_', ' ').replace('.', ' ').split() if p]
    if not partes:
        return '?'
    if len(partes) == 1:
        return partes[0][:2].upper()
    return (partes[0][0] + partes[-1][0]).upper()


@register.filter
def azulejo(valor):
    """Escolhe, de forma estável, um dos quatro padrões de azulejo para a cafeteria."""
    return sum(ord(c) for c in str(valor)) % 4 + 1
