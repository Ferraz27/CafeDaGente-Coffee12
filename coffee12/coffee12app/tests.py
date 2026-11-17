from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import CustomUser, Estabelecimento, Feedback, Historico, ItemEsquecido, Prato, Reserva

SENHA = 'Senha-de-teste-123'


class Base(TestCase):
    def setUp(self):
        self.cliente = CustomUser.objects.create_user('ana', 'ana@ex.com', SENHA)
        self.dono = CustomUser.objects.create_user('bruno', 'bruno@ex.com', SENHA, role='CM')
        self.cafe = Estabelecimento.objects.create(
            nome='Café Azulejo', endereco='Rua da Aurora, 10', telefone='81999990000', proprietario=self.dono)
        self.dono.cafeteria = self.cafe
        self.dono.possui_estabelecimento = True
        self.dono.save()
        self.prato = Prato.objects.create(
            nome='Cappuccino', descricao='Com canela', preco=Decimal('12.00'),
            preco_promocional=Decimal('9.90'), prato_principal=True, estabelecimento=self.cafe)

        self.outro_dono = CustomUser.objects.create_user('carla', 'carla@ex.com', SENHA, role='CM')
        self.outro_cafe = Estabelecimento.objects.create(
            nome='Outro Café', endereco='Rua do Sol', telefone='81', proprietario=self.outro_dono)
        self.outro_dono.cafeteria = self.outro_cafe
        self.outro_dono.save()

    def entrar(self, user):
        self.client.force_login(user)


class CadastroLoginTests(Base):
    def test_cadastro_cliente_faz_login_e_vai_para_home(self):
        resp = self.client.post(reverse('signup'), {
            'username': 'novo', 'email': 'novo@ex.com', 'phone_number': '81',
            'password1': SENHA, 'password2': SENHA,
        })
        self.assertRedirects(resp, reverse('homepage'))
        self.assertEqual(CustomUser.objects.get(username='novo').role, 'CL')

    def test_cadastro_dono_vai_para_cadastro_da_cafeteria(self):
        resp = self.client.post(reverse('signupCafe'), {
            'username': 'dona', 'email': 'dona@ex.com',
            'password1': SENHA, 'password2': SENHA,
        })
        self.assertRedirects(resp, reverse('cadastrarEstabelecimento'))
        self.assertEqual(CustomUser.objects.get(username='dona').role, 'CM')

    def test_senhas_diferentes_mostram_erro_no_formulario(self):
        resp = self.client.post(reverse('signup'), {
            'username': 'x', 'email': 'x@ex.com', 'password1': SENHA, 'password2': 'outra',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(CustomUser.objects.filter(username='x').exists())

    def test_usuario_duplicado_nao_quebra(self):
        resp = self.client.post(reverse('signup'), {
            'username': 'ana', 'email': 'outra@ex.com', 'password1': SENHA, 'password2': SENHA,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(CustomUser.objects.filter(username='ana').count(), 1)

    def test_login_redireciona_conforme_papel(self):
        resp = self.client.post(reverse('login'), {'username': 'bruno', 'password': SENHA})
        self.assertRedirects(resp, reverse('homepagecafe'))
        self.client.logout()
        resp = self.client.post(reverse('login'), {'username': 'ana', 'password': SENHA})
        self.assertRedirects(resp, reverse('homepage'))

    def test_login_errado_continua_na_pagina(self):
        resp = self.client.post(reverse('login'), {'username': 'ana', 'password': 'errada'})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'incorretos')


class PaginasRenderizamTests(Base):
    def test_paginas_do_cliente(self):
        Historico.objects.create(user=self.cliente, cafeteria=self.cafe)
        Feedback.objects.create(user=self.cliente, cafeteria=self.cafe, rating=5, comment='Ótimo')
        self.entrar(self.cliente)
        urls = [
            reverse('homepage'), reverse('homepage') + '?q=capp', reverse('favoritos'), reverse('historico'),
            reverse('reserva_list'), reverse('listar_requisicoes_cliente'),
            reverse('perfilCafeteria', args=[self.cafe.id]), reverse('feedback', args=[self.cafe.id]),
            reverse('verFeedbacks', args=[self.cafe.id]), reverse('reserva_create', args=[self.cafe.id]),
            reverse('solicitaritem', args=[self.cafe.id]),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_paginas_do_dono(self):
        self.entrar(self.dono)
        urls = [
            reverse('homepagecafe'), reverse('editarEstabelecimento'), reverse('cadastrarPrato'),
            reverse('editarPrato', args=[self.prato.id]), reverse('excluirPrato'),
            reverse('reserva_listar'), reverse('solicitacoes'), reverse('verFeedbacks', args=[self.cafe.id]),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_paginas_publicas(self):
        for nome in ['inicio', 'login', 'signup', 'signupCafe']:
            with self.subTest(nome=nome):
                self.assertEqual(self.client.get(reverse(nome)).status_code, 200)

    def test_dono_sem_cafeteria_ve_convite_para_cadastrar(self):
        novo = CustomUser.objects.create_user('dani', 'd@ex.com', SENHA, role='CM')
        self.entrar(novo)
        self.assertContains(self.client.get(reverse('homepagecafe')), 'Cadastre sua cafeteria')
        self.assertRedirects(self.client.get(reverse('excluirPrato')), reverse('cadastrarEstabelecimento'))


class PermissoesTests(Base):
    def test_anonimo_vai_para_login(self):
        resp = self.client.get(reverse('homepage'))
        self.assertRedirects(resp, reverse('login') + '?next=' + reverse('homepage'))

    def test_cliente_nao_acessa_area_do_dono(self):
        self.entrar(self.cliente)
        self.assertRedirects(self.client.get(reverse('homepagecafe')), reverse('homepage'))
        self.assertRedirects(self.client.get(reverse('reserva_listar')), reverse('homepage'))

    def test_dono_nao_exclui_prato_de_outra_cafeteria(self):
        self.entrar(self.outro_dono)
        resp = self.client.post(reverse('excluirPrato'), {'prato_id': self.prato.id})
        self.assertEqual(resp.status_code, 404)
        self.assertTrue(Prato.objects.filter(id=self.prato.id).exists())

    def test_cliente_nao_remove_visita_de_outro(self):
        outro = CustomUser.objects.create_user('edu', 'e@ex.com', SENHA)
        visita = Historico.objects.create(user=outro, cafeteria=self.cafe)
        self.entrar(self.cliente)
        self.assertEqual(self.client.post(reverse('remove_visit', args=[visita.id])).status_code, 404)

    def test_exclusoes_exigem_post(self):
        self.entrar(self.dono)
        self.assertEqual(self.client.get(reverse('excluirEstabelecimento')).status_code, 405)
        self.assertTrue(Estabelecimento.objects.filter(id=self.cafe.id).exists())


class FluxoReservaTests(Base):
    def futuro(self, dias=2):
        return (timezone.localtime() + timedelta(days=dias)).strftime('%Y-%m-%dT%H:%M')

    def test_cliente_reserva_e_dono_confirma(self):
        self.entrar(self.cliente)
        resp = self.client.post(reverse('reserva_create', args=[self.cafe.id]),
                                {'data_hora': self.futuro(), 'numero_pessoas': 2})
        self.assertRedirects(resp, reverse('reserva_list'))
        reserva = Reserva.objects.get()
        self.assertEqual(reserva.status, Reserva.PENDENTE)

        self.entrar(self.dono)
        self.client.post(reverse('reserva_aceitar', args=[reserva.id]))
        reserva.refresh_from_db()
        self.assertEqual(reserva.status, Reserva.ACEITO)

    def test_dono_recusa_reserva(self):
        reserva = Reserva.objects.create(cafe=self.cafe, cliente=self.cliente,
                                         data_hora=timezone.now() + timedelta(days=1), numero_pessoas=3)
        self.entrar(self.dono)
        self.client.post(reverse('reserva_recusar', args=[reserva.id]))
        reserva.refresh_from_db()
        self.assertEqual(reserva.status, Reserva.RECUSADO)

    def test_outro_dono_nao_mexe_na_reserva(self):
        reserva = Reserva.objects.create(cafe=self.cafe, cliente=self.cliente,
                                         data_hora=timezone.now() + timedelta(days=1), numero_pessoas=3)
        self.entrar(self.outro_dono)
        self.assertEqual(self.client.post(reverse('reserva_aceitar', args=[reserva.id])).status_code, 404)

    def test_reserva_no_passado_e_recusada(self):
        self.entrar(self.cliente)
        resp = self.client.post(reverse('reserva_create', args=[self.cafe.id]),
                                {'data_hora': self.futuro(-1), 'numero_pessoas': 2})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'futuro')
        self.assertFalse(Reserva.objects.exists())

    def test_cliente_cancela(self):
        reserva = Reserva.objects.create(cafe=self.cafe, cliente=self.cliente,
                                         data_hora=timezone.now() + timedelta(days=1), numero_pessoas=1)
        self.entrar(self.cliente)
        self.client.post(reverse('reserva_cancel', args=[reserva.id]))
        reserva.refresh_from_db()
        self.assertEqual(reserva.status, Reserva.CANCELADO)


class CardapioEAvaliacaoTests(Base):
    def test_promocao_precisa_ser_menor_que_preco(self):
        self.entrar(self.dono)
        resp = self.client.post(reverse('cadastrarPrato'), {
            'nome': 'Bolo', 'descricao': 'De rolo', 'preco': '10', 'preco_promocional': '15'})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Prato.objects.filter(nome='Bolo').exists())

    def test_prato_sem_promocao(self):
        self.entrar(self.dono)
        resp = self.client.post(reverse('cadastrarPrato'), {'nome': 'Bolo', 'descricao': 'De rolo', 'preco': '10'})
        self.assertRedirects(resp, reverse('homepagecafe'))
        self.assertIsNone(Prato.objects.get(nome='Bolo').preco_promocional)

    def test_avaliacao_publicada_e_media(self):
        self.entrar(self.cliente)
        self.client.post(reverse('feedback', args=[self.cafe.id]), {'rating': '4', 'comment': 'Bom'})
        self.client.post(reverse('feedback', args=[self.cafe.id]), {'rating': '5', 'comment': 'Ótimo'})
        self.assertEqual(self.cafe.rating_average, 4.5)

    def test_nota_fora_do_intervalo(self):
        self.entrar(self.cliente)
        resp = self.client.post(reverse('feedback', args=[self.cafe.id]), {'rating': '9', 'comment': 'x'})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Feedback.objects.exists())

    def test_favoritar_e_desfavoritar(self):
        self.entrar(self.cliente)
        self.client.post(reverse('favoritarCafeteria', args=[self.cafe.id]))
        self.assertTrue(self.cliente.cafeteria_favorita.filter(id=self.cafe.id).exists())
        self.client.post(reverse('desfavoritarCafeteria', args=[self.cafe.id]))
        self.assertFalse(self.cliente.cafeteria_favorita.filter(id=self.cafe.id).exists())


class ItemEsquecidoTests(Base):
    def test_fluxo_completo(self):
        self.entrar(self.cliente)
        self.client.post(reverse('solicitaritem', args=[self.cafe.id]), {'descricao': 'Guarda-chuva'})
        item = ItemEsquecido.objects.get()

        self.entrar(self.dono)
        self.client.post(reverse('marcar_item_achado', args=[item.id]))
        item.refresh_from_db()
        self.assertEqual(item.status, ItemEsquecido.ACHADO)
        self.assertEqual(item.get_status_display(), 'Achado')

        self.client.post(reverse('marcar_item_nao_achado', args=[item.id]))
        item.refresh_from_db()
        self.assertEqual(item.status, ItemEsquecido.NAO_ENCONTRADO)

    def test_outra_cafeteria_nao_ve_o_item(self):
        item = ItemEsquecido.objects.create(cliente=self.cliente, cafeteria=self.cafe, descricao='Óculos')
        self.entrar(self.outro_dono)
        self.assertEqual(self.client.post(reverse('remover_requisicao', args=[item.id])).status_code, 404)


class DistribuicaoNotasTests(Base):
    def test_total_e_distribuicao(self):
        for nota in (5, 5, 4):
            Feedback.objects.create(user=self.cliente, cafeteria=self.cafe, rating=nota, comment='x')
        self.entrar(self.cliente)
        resp = self.client.get(reverse('verFeedbacks', args=[self.cafe.id]))
        self.assertEqual(resp.context['total'], 3)
        self.assertEqual(resp.context['distribuicao'][0]['qtd'], 2)
