"""Cria dados de demonstração: cafeterias de Recife, cardápios, avaliações e reservas.

Uso:  python manage.py popular_demo
Contas criadas (senha: cafe-demo-2024):
  cliente_demo  -> cliente
  dono_demo     -> dono da "Café Azulejo"
Rodar de novo não duplica nada.
"""
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from coffee12app.models import CustomUser, Estabelecimento, Feedback, Historico, ItemEsquecido, Prato, Reserva

SENHA_DEMO = 'cafe-demo-2024'

CAFES = [
    {
        'nome': 'Café Azulejo', 'endereco': 'Rua da Aurora, 325, Boa Vista', 'telefone': '(81) 3222-1010',
        'horario': 'Seg a Sáb, 7h às 20h', 'dono': 'dono_demo',
        'pratos': [
            ('Cappuccino da casa', 'Espresso, leite vaporizado e canela.', '12.00', '9.90', True),
            ('Bolo de rolo', 'Fatia com goiabada, receita pernambucana.', '9.50', None, True),
            ('Espresso', 'Grãos do Sul de Minas, torra média.', '6.00', None, False),
            ('Tapioca de coco', 'Com leite condensado.', '14.00', '11.50', False),
        ],
    },
    {
        'nome': 'Torra do Recife Antigo', 'endereco': 'Rua do Bom Jesus, 140, Recife Antigo', 'telefone': '(81) 3224-2020',
        'horario': 'Ter a Dom, 9h às 22h', 'dono': 'dono_torra',
        'pratos': [
            ('Coado no V60', 'Café especial do dia, preparado na hora.', '11.00', None, True),
            ('Pão de queijo', 'Porção com 6 unidades.', '10.00', None, False),
            ('Cold brew', 'Extração a frio por 18 horas.', '15.00', '12.00', True),
        ],
    },
    {
        'nome': 'Varanda de Olinda', 'endereco': 'Rua do Amparo, 88, Olinda', 'telefone': '(81) 3429-3030',
        'horario': 'Todos os dias, 8h às 19h', 'dono': 'dono_varanda',
        'pratos': [
            ('Mocha', 'Espresso, chocolate e leite.', '13.00', None, True),
            ('Cartola', 'Banana, queijo, açúcar e canela.', '18.00', None, True),
        ],
    },
    {
        'nome': 'Grão de Casa Forte', 'endereco': 'Praça de Casa Forte, 45, Casa Forte', 'telefone': '(81) 3268-4040',
        'horario': 'Seg a Sex, 7h às 18h', 'dono': 'dono_grao',
        'pratos': [
            ('Latte', 'Espresso duplo e bastante leite.', '12.50', None, False),
            ('Croissant', 'Manteiga, folhado na casa.', '9.00', '7.50', True),
        ],
    },
]

AVALIACOES = {
    'Café Azulejo': [(5, 'O bolo de rolo é o melhor da cidade, e o cappuccino em promoção vale muito.'),
                     (4, 'Ambiente bonito e tranquilo para estudar. Fica cheio no fim da tarde.')],
    'Torra do Recife Antigo': [(5, 'Café especial de verdade. O barista explica cada grão.'),
                               (5, 'O cold brew salvou minha tarde de calor.'),
                               (4, 'Ótimo, só demorou um pouco no domingo.')],
    'Varanda de Olinda': [(4, 'Vista linda e a cartola é muito boa.')],
}


class Command(BaseCommand):
    help = 'Popula o banco com cafeterias, cardápios e avaliações de demonstração.'

    def usuario(self, username, role):
        user, criado = CustomUser.objects.get_or_create(
            username=username, defaults={'email': f'{username}@exemplo.com', 'role': role})
        if criado:
            user.set_password(SENHA_DEMO)
            user.save()
        return user

    @transaction.atomic
    def handle(self, *args, **options):
        cliente = self.usuario('cliente_demo', CustomUser.CLIENT)
        outros = [self.usuario(n, CustomUser.CLIENT) for n in ('marina_cafe', 'joao.pe', 'lu_olinda')]

        for dados in CAFES:
            dono = self.usuario(dados['dono'], CustomUser.COFFEEADMIN)
            cafe, criado = Estabelecimento.objects.get_or_create(
                nome=dados['nome'],
                defaults={'endereco': dados['endereco'], 'telefone': dados['telefone'],
                          'descricao_horario': dados['horario'], 'proprietario': dono})
            if not criado:
                continue
            dono.cafeteria = cafe
            dono.possui_estabelecimento = True
            dono.save()
            for nome, desc, preco, promo, principal in dados['pratos']:
                Prato.objects.create(nome=nome, descricao=desc, preco=Decimal(preco),
                                     preco_promocional=Decimal(promo) if promo else None,
                                     prato_principal=principal, estabelecimento=cafe)
            for i, (nota, texto) in enumerate(AVALIACOES.get(cafe.nome, [])):
                Feedback.objects.create(user=outros[i % len(outros)], cafeteria=cafe, rating=nota, comment=texto,
                                        created_at=timezone.now() - timedelta(days=3 * i + 1))

        azulejo = Estabelecimento.objects.get(nome='Café Azulejo')
        if not Reserva.objects.filter(cliente=cliente).exists():
            amanha = timezone.localtime().replace(hour=16, minute=0, second=0, microsecond=0) + timedelta(days=1)
            Reserva.objects.create(cafe=azulejo, cliente=cliente, data_hora=amanha, numero_pessoas=2)
            Reserva.objects.create(cafe=azulejo, cliente=outros[0], data_hora=amanha + timedelta(days=2, hours=-6),
                                   numero_pessoas=4, status=Reserva.ACEITO)
            Historico.objects.create(user=cliente, cafeteria=azulejo, visit_date=timezone.now() - timedelta(days=5))
            ItemEsquecido.objects.create(cliente=cliente, cafeteria=azulejo, descricao='Guarda-chuva azul')
            cliente.cafeteria_favorita.add(azulejo)

        self.stdout.write(self.style.SUCCESS(
            f'Dados de demonstração prontos. Entre com cliente_demo ou dono_demo (senha: {SENHA_DEMO}).'))
