from django.utils import timezone

from .models import CustomUser, ItemEsquecido, Reserva


def navegacao(request):
    """Dados usados na barra de navegação em todas as páginas."""
    user = getattr(request, 'user', None)
    match = getattr(request, 'resolver_match', None)
    contexto = {'rota_atual': match.url_name if match else ''}
    if not user or not user.is_authenticated:
        return contexto

    eh_dono = user.role == CustomUser.COFFEEADMIN
    contexto['eh_dono_cafe'] = eh_dono
    if eh_dono:
        cafeteria = user.cafeteria
        contexto['minha_cafeteria'] = cafeteria
        if cafeteria:
            contexto['nav_reservas_pendentes'] = Reserva.objects.filter(
                cafe=cafeteria, status=Reserva.PENDENTE, data_hora__gte=timezone.now()).count()
            contexto['nav_itens_pendentes'] = ItemEsquecido.objects.filter(
                cafeteria=cafeteria, status=ItemEsquecido.PENDENTE).count()
    return contexto
