from functools import wraps

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.db.models import Avg, Count, F, Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import (
    CadastroForm,
    EstabelecimentoForm,
    FeedbackForm,
    ItemEsquecidoForm,
    PratoForm,
    ReservaForm,
)
from .models import CustomUser, Estabelecimento, Feedback, Historico, ItemEsquecido, Prato, Reserva


# ---------------------------------------------------------------------------
# Helpers e decorators de permissão
# ---------------------------------------------------------------------------

def home_para(user):
    """Nome da rota inicial de acordo com o papel do usuário."""
    if user.is_authenticated and user.role == CustomUser.COFFEEADMIN:
        return 'homepagecafe'
    return 'homepage'


def cafeteria_do_usuario(user):
    if user.cafeteria_id:
        return user.cafeteria
    return Estabelecimento.objects.filter(proprietario=user).first()


def voltar(request, padrao):
    """Redireciona para a página anterior, se ela for do próprio site."""
    destino = request.POST.get('next') or request.META.get('HTTP_REFERER')
    if destino and url_has_allowed_host_and_scheme(destino, allowed_hosts={request.get_host()}):
        return redirect(destino)
    return redirect(padrao)


def apenas_clientes(view):
    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if request.user.role != CustomUser.CLIENT:
            messages.info(request, 'Essa área é para clientes. Use o painel da sua cafeteria.')
            return redirect('homepagecafe')
        return view(request, *args, **kwargs)
    return wrapper


def apenas_donos(view):
    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if request.user.role != CustomUser.COFFEEADMIN:
            messages.info(request, 'Essa área é para donos de cafeteria.')
            return redirect('homepage')
        return view(request, *args, **kwargs)
    return wrapper


def com_cafeteria(view):
    """Dono de cafeteria com estabelecimento já cadastrado. Injeta `cafeteria`."""
    @wraps(view)
    @apenas_donos
    def wrapper(request, *args, **kwargs):
        cafeteria = cafeteria_do_usuario(request.user)
        if cafeteria is None:
            messages.info(request, 'Cadastre sua cafeteria para continuar.')
            return redirect('cadastrarEstabelecimento')
        return view(request, cafeteria, *args, **kwargs)
    return wrapper


def cafeterias_com_resumo():
    return (
        Estabelecimento.objects
        .annotate(media=Avg('feedback__rating'), total_avaliacoes=Count('feedback', distinct=True))
        .prefetch_related(
            Prefetch('prato_set', queryset=Prato.objects.filter(prato_principal=True), to_attr='destaques'),
            Prefetch(
                'prato_set',
                queryset=Prato.objects.filter(preco_promocional__isnull=False, preco_promocional__lt=F('preco')),
                to_attr='promocoes',
            ),
        )
    )


# ---------------------------------------------------------------------------
# Páginas públicas e autenticação
# ---------------------------------------------------------------------------

def Inicio(request):
    if request.user.is_authenticated:
        return redirect(home_para(request.user))
    destaques = cafeterias_com_resumo().order_by(F('media').desc(nulls_last=True))[:3]
    return render(request, 'inicio.html', {'destaques': destaques})


def _cadastro(request, role, template):
    if request.user.is_authenticated:
        return redirect(home_para(request.user))
    form = CadastroForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save(commit=False)
        user.role = role
        user.save()
        login(request, user)
        if role == CustomUser.COFFEEADMIN:
            messages.success(request, 'Conta criada. Agora cadastre sua cafeteria.')
            return redirect('cadastrarEstabelecimento')
        messages.success(request, f'Bem-vindo(a), {user.username}!')
        return redirect('homepage')
    papel = 'dono' if role == CustomUser.COFFEEADMIN else 'cliente'
    return render(request, template, {'form': form, 'papel': papel})


def SignupPage(request):
    return _cadastro(request, CustomUser.CLIENT, 'signup.html')


def SignupCafePage(request):
    return _cadastro(request, CustomUser.COFFEEADMIN, 'signupCafe.html')


def LoginPage(request):
    if request.user.is_authenticated:
        return redirect(home_para(request.user))
    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.get_user()
        login(request, user)
        proximo = request.POST.get('next') or request.GET.get('next')
        if proximo and url_has_allowed_host_and_scheme(proximo, allowed_hosts={request.get_host()}):
            return redirect(proximo)
        return redirect(home_para(user))
    return render(request, 'login.html', {'form': form, 'next': request.GET.get('next', '')})


def LogoutPage(request):
    logout(request)
    messages.info(request, 'Você saiu da sua conta.')
    return redirect('login')


# ---------------------------------------------------------------------------
# Área do cliente
# ---------------------------------------------------------------------------

@login_required
def Homepage(request):
    busca = request.GET.get('q', '').strip()
    ordem = request.GET.get('ordem', 'nota')
    estabelecimentos = cafeterias_com_resumo()
    if busca:
        estabelecimentos = estabelecimentos.filter(
            Q(nome__icontains=busca) | Q(endereco__icontains=busca) | Q(prato__nome__icontains=busca)
        ).distinct()
    if ordem == 'nome':
        estabelecimentos = estabelecimentos.order_by('nome')
    else:
        ordem = 'nota'
        estabelecimentos = estabelecimentos.order_by(F('media').desc(nulls_last=True), 'nome')

    favoritos_ids = set(request.user.cafeteria_favorita.values_list('id', flat=True))
    return render(request, 'homepage.html', {
        'estabelecimentos': estabelecimentos,
        'favoritos_ids': favoritos_ids,
        'busca': busca,
        'ordem': ordem,
    })


@login_required
def PerfilCafeteria(request, id_cafeteria):
    estabelecimento = get_object_or_404(Estabelecimento, id=id_cafeteria)
    cardapio = list(Prato.objects.filter(estabelecimento=estabelecimento).order_by('-prato_principal', 'nome'))
    feedbacks = Feedback.objects.filter(cafeteria=estabelecimento).select_related('user').order_by('-created_at')
    contexto = {
        'estabelecimento': estabelecimento,
        'cardapio': cardapio,
        'destaques': [p for p in cardapio if p.prato_principal and not p.em_promocao],
        'promocoes': [p for p in cardapio if p.em_promocao],
        'outros': [p for p in cardapio if not p.prato_principal and not p.em_promocao],
        'rating_average': estabelecimento.rating_average,
        'total_avaliacoes': feedbacks.count(),
        'feedbacks': feedbacks[:3],
        'eh_favorita': request.user.cafeteria_favorita.filter(id=estabelecimento.id).exists(),
        'visitas': Historico.objects.filter(user=request.user, cafeteria=estabelecimento).count(),
        'eh_dono': estabelecimento.proprietario_id == request.user.id,
    }
    return render(request, 'perfilcafeteria.html', contexto)


@apenas_clientes
@require_POST
def FavoritarCafeteria(request, id):
    cafeteria = get_object_or_404(Estabelecimento, id=id)
    request.user.cafeteria_favorita.add(cafeteria)
    messages.success(request, f'{cafeteria.nome} foi adicionada aos favoritos.')
    return voltar(request, 'favoritos')


@apenas_clientes
@require_POST
def DesfavoritarCafeteria(request, id):
    cafeteria = get_object_or_404(Estabelecimento, id=id)
    request.user.cafeteria_favorita.remove(cafeteria)
    messages.info(request, f'{cafeteria.nome} saiu dos favoritos.')
    return voltar(request, 'favoritos')


@login_required
def VerCafeteriasFavoritas(request):
    return redirect('favoritos')


@apenas_clientes
def Favoritos(request):
    favoritas = cafeterias_com_resumo().filter(cafeterias_favoritas=request.user).order_by('nome')
    return render(request, 'favoritos.html', {
        'cafeterias_favoritas': favoritas,
        'favoritos_ids': {c.id for c in favoritas},
    })


@apenas_clientes
def feedback(request, id):
    estabelecimento = get_object_or_404(Estabelecimento, id=id)
    form = FeedbackForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        novo = form.save(commit=False)
        novo.user = request.user
        novo.cafeteria = estabelecimento
        novo.save()
        messages.success(request, 'Obrigado! Sua avaliação foi publicada.')
        return redirect('perfilCafeteria', id_cafeteria=id)
    return render(request, 'feedback.html', {'form': form, 'estabelecimento': estabelecimento})


@login_required
def VerFeedbacks(request, id_cafeteria):
    estabelecimento = get_object_or_404(Estabelecimento, id=id_cafeteria)
    feedbacks = Feedback.objects.filter(cafeteria=estabelecimento).select_related('user').order_by('-created_at')
    contagem = dict(feedbacks.order_by().values_list('rating').annotate(n=Count('id')))
    total = sum(contagem.values())
    distribuicao = [
        {'nota': n, 'qtd': contagem.get(n, 0), 'pct': round(100 * contagem.get(n, 0) / total) if total else 0}
        for n in range(5, 0, -1)
    ]
    return render(request, 'verFeedbacks.html', {
        'feedbacks': feedbacks,
        'estabelecimento': estabelecimento,
        'rating_average': estabelecimento.rating_average,
        'distribuicao': distribuicao,
        'total': total,
        'eh_dono': estabelecimento.proprietario_id == request.user.id,
    })


@apenas_clientes
@require_POST
def add_to_historico(request, cafeteria_id):
    cafeteria = get_object_or_404(Estabelecimento, id=cafeteria_id)
    Historico.objects.create(user=request.user, cafeteria=cafeteria)
    messages.success(request, f'Visita registrada: {cafeteria.nome}.')
    return redirect('perfilCafeteria', id_cafeteria=cafeteria_id)


@apenas_clientes
def historico(request):
    visitas = Historico.objects.filter(user=request.user).select_related('cafeteria').order_by('-visit_date')
    return render(request, 'historico.html', {'historico': visitas})


@apenas_clientes
@require_POST
def remove_visit(request, visit_id):
    visita = get_object_or_404(Historico, id=visit_id, user=request.user)
    visita.delete()
    messages.info(request, 'Visita removida do histórico.')
    return redirect('historico')


@apenas_clientes
def ReservaCreateView(request, cafe_id):
    cafeteria = get_object_or_404(Estabelecimento, id=cafe_id)
    form = ReservaForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        reserva = form.save(commit=False)
        reserva.cafe = cafeteria
        reserva.cliente = request.user
        reserva.save()
        messages.success(request, f'Pedido de reserva enviado para {cafeteria.nome}. Aguarde a confirmação.')
        return redirect('reserva_list')
    return render(request, 'reservaform.html', {'form': form, 'cafeteria': cafeteria})


@apenas_clientes
def ReservaListView(request):
    agora = timezone.now()
    reservas = Reserva.objects.filter(cliente=request.user).select_related('cafe')
    proximas = reservas.filter(data_hora__gte=agora).exclude(status=Reserva.CANCELADO).order_by('data_hora')
    anteriores = reservas.filter(Q(data_hora__lt=agora) | Q(status=Reserva.CANCELADO)).order_by('-data_hora')
    return render(request, 'reservalist.html', {'proximas': proximas, 'anteriores': anteriores})


def _reserva_editavel(reserva):
    return reserva.status in (Reserva.PENDENTE, Reserva.ACEITO) and reserva.data_hora > timezone.now()


@apenas_clientes
def ReservaUpdateView(request, reserva_id):
    reserva = get_object_or_404(Reserva, id=reserva_id, cliente=request.user)
    if not _reserva_editavel(reserva):
        messages.error(request, 'Essa reserva não pode mais ser alterada.')
        return redirect('reserva_list')
    form = ReservaForm(request.POST or None, instance=reserva)
    if request.method == 'POST' and form.is_valid():
        reserva = form.save(commit=False)
        reserva.status = Reserva.PENDENTE
        reserva.save()
        messages.success(request, 'Reserva alterada. A cafeteria vai confirmar de novo.')
        return redirect('reserva_list')
    return render(request, 'reservaupdate.html', {'form': form, 'reserva': reserva})


@apenas_clientes
@require_POST
def ReservaCancelView(request, reserva_id):
    reserva = get_object_or_404(Reserva, id=reserva_id, cliente=request.user)
    if reserva.status in (Reserva.PENDENTE, Reserva.ACEITO):
        reserva.status = Reserva.CANCELADO
        reserva.save()
        messages.info(request, f'Reserva cancelada: {reserva.cafe.nome}.')
    return redirect('reserva_list')


@apenas_clientes
def solicitar_item(request, id_cafeteria):
    cafeteria = get_object_or_404(Estabelecimento, id=id_cafeteria)
    form = ItemEsquecidoForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        item = form.save(commit=False)
        item.cliente = request.user
        item.cafeteria = cafeteria
        item.save()
        messages.success(request, f'Solicitação enviada para {cafeteria.nome}.')
        return redirect('listar_requisicoes_cliente')
    return render(request, 'solicitaritem.html', {'form': form, 'cafeteria': cafeteria})


@apenas_clientes
def listar_requisicoes_cliente(request):
    requisicoes = ItemEsquecido.objects.filter(cliente=request.user).select_related('cafeteria').order_by('-id')
    return render(request, 'minhassolicitacoes.html', {'requisicoes': requisicoes})


# ---------------------------------------------------------------------------
# Área do dono de cafeteria
# ---------------------------------------------------------------------------

@apenas_donos
def HomepageCafe(request):
    cafeteria = cafeteria_do_usuario(request.user)
    contexto = {'cafeteria': cafeteria}
    if cafeteria:
        contexto.update({
            'pratos': Prato.objects.filter(estabelecimento=cafeteria).order_by('-prato_principal', 'nome'),
            'rating_average': cafeteria.rating_average,
            'total_avaliacoes': Feedback.objects.filter(cafeteria=cafeteria).count(),
            'reservas_pendentes': Reserva.objects.filter(
                cafe=cafeteria, status=Reserva.PENDENTE, data_hora__gte=timezone.now()).count(),
            'itens_pendentes': ItemEsquecido.objects.filter(
                cafeteria=cafeteria, status=ItemEsquecido.PENDENTE).count(),
            'ultimos_feedbacks': Feedback.objects.filter(cafeteria=cafeteria)
                .select_related('user').order_by('-created_at')[:3],
        })
    return render(request, 'homepagecafe.html', contexto)


@apenas_donos
def CadastrarEstabelecimento(request):
    if cafeteria_do_usuario(request.user):
        return redirect('editarEstabelecimento')
    form = EstabelecimentoForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        cafeteria = form.save(commit=False)
        cafeteria.proprietario = request.user
        cafeteria.save()
        request.user.cafeteria = cafeteria
        request.user.possui_estabelecimento = True
        request.user.save(update_fields=['cafeteria', 'possui_estabelecimento'])
        messages.success(request, f'{cafeteria.nome} está no ar! Agora monte seu cardápio.')
        return redirect('cadastrarPrato')
    return render(request, 'cadastrarEstabelecimento.html', {'form': form})


@com_cafeteria
def EditarEstabelecimento(request, cafeteria):
    form = EstabelecimentoForm(request.POST or None, instance=cafeteria)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Dados da cafeteria salvos.')
        return redirect('homepagecafe')
    return render(request, 'editarEstabelecimento.html', {'form': form, 'cafeteria': cafeteria})


@com_cafeteria
@require_POST
def ExcluirEstabelecimento(request, cafeteria):
    nome = cafeteria.nome
    request.user.cafeteria = None
    request.user.possui_estabelecimento = False
    request.user.save(update_fields=['cafeteria', 'possui_estabelecimento'])
    Estabelecimento.objects.filter(proprietario=request.user).delete()
    messages.info(request, f'{nome} foi excluída da plataforma.')
    return redirect('homepagecafe')


@com_cafeteria
def CadastrarPrato(request, cafeteria):
    form = PratoForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        prato = form.save(commit=False)
        prato.estabelecimento = cafeteria
        prato.save()
        messages.success(request, f'{prato.nome} entrou no cardápio.')
        if 'adicionar_outro' in request.POST:
            return redirect('cadastrarPrato')
        return redirect('homepagecafe')
    return render(request, 'cadastrarPrato.html', {'form': form, 'cafeteria': cafeteria})


@com_cafeteria
def EditarPrato(request, cafeteria, prato_id):
    prato = get_object_or_404(Prato, id=prato_id, estabelecimento=cafeteria)
    form = PratoForm(request.POST or None, instance=prato)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f'{prato.nome} atualizado.')
        return redirect('homepagecafe')
    return render(request, 'cadastrarPrato.html', {'form': form, 'cafeteria': cafeteria, 'prato': prato})


@com_cafeteria
def ExcluirPrato(request, cafeteria):
    if request.method == 'POST':
        prato = get_object_or_404(Prato, id=request.POST.get('prato_id'), estabelecimento=cafeteria)
        nome = prato.nome
        prato.delete()
        messages.info(request, f'{nome} saiu do cardápio.')
        return voltar(request, 'excluirPrato')
    pratos = Prato.objects.filter(estabelecimento=cafeteria).order_by('nome')
    return render(request, 'excluirPrato.html', {'pratos': pratos, 'cafeteria': cafeteria})


@com_cafeteria
def listar_reservas(request, cafeteria):
    agora = timezone.now()
    reservas = Reserva.objects.filter(cafe=cafeteria, data_hora__gte=agora).select_related('cliente').order_by('data_hora')
    return render(request, 'listarreservascafe.html', {
        'cafeteria': cafeteria,
        'pendentes': reservas.filter(status=Reserva.PENDENTE),
        'confirmadas': reservas.filter(status=Reserva.ACEITO),
    })


def _mudar_status_reserva(request, cafeteria, reserva_id, novo_status, texto):
    reserva = get_object_or_404(Reserva, id=reserva_id, cafe=cafeteria)
    if reserva.status == Reserva.PENDENTE:
        reserva.status = novo_status
        reserva.save(update_fields=['status'])
        messages.success(request, f'Reserva de {reserva.cliente.username} {texto}.')
    return redirect('reserva_listar')


@com_cafeteria
@require_POST
def AceitarReservaView(request, cafeteria, reserva_id):
    return _mudar_status_reserva(request, cafeteria, reserva_id, Reserva.ACEITO, 'confirmada')


@com_cafeteria
@require_POST
def RecusarReservaView(request, cafeteria, reserva_id):
    return _mudar_status_reserva(request, cafeteria, reserva_id, Reserva.RECUSADO, 'recusada')


@com_cafeteria
def ver_solicitacoes(request, cafeteria):
    solicitacoes = ItemEsquecido.objects.filter(cafeteria=cafeteria).select_related('cliente').order_by(
        F('status').desc(), '-id')
    return render(request, 'solicitacoes.html', {
        'cafeteria': cafeteria,
        'pendentes': [s for s in solicitacoes if s.status == ItemEsquecido.PENDENTE],
        'resolvidas': [s for s in solicitacoes if s.status != ItemEsquecido.PENDENTE],
    })


def _mudar_status_item(request, cafeteria, item_id, status, texto):
    item = get_object_or_404(ItemEsquecido, id=item_id, cafeteria=cafeteria)
    item.status = status
    item.save(update_fields=['status'])
    messages.success(request, f'"{item.descricao}" marcado como {texto}.')
    return redirect('solicitacoes')


@com_cafeteria
@require_POST
def marcar_item_achado(request, cafeteria, item_id):
    return _mudar_status_item(request, cafeteria, item_id, ItemEsquecido.ACHADO, 'achado')


@com_cafeteria
@require_POST
def marcar_item_nao_achado(request, cafeteria, item_id):
    return _mudar_status_item(request, cafeteria, item_id, ItemEsquecido.NAO_ENCONTRADO, 'não encontrado')


@com_cafeteria
@require_POST
def remover_requisicao(request, cafeteria, item_id):
    item = get_object_or_404(ItemEsquecido, id=item_id, cafeteria=cafeteria)
    item.delete()
    messages.info(request, 'Solicitação removida.')
    return redirect('solicitacoes')
