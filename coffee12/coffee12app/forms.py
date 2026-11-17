from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.utils import timezone

from .models import CustomUser, Estabelecimento, Feedback, ItemEsquecido, Prato, Reserva


class EstiloBootstrap:
    """Aplica as classes do Bootstrap nos widgets automaticamente."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, (forms.CheckboxInput, forms.RadioSelect)):
                classe = 'form-check-input'
            elif isinstance(widget, forms.Select):
                classe = 'form-select'
            else:
                classe = 'form-control'
            widget.attrs['class'] = (widget.attrs.get('class', '') + ' ' + classe).strip()


class CadastroForm(EstiloBootstrap, UserCreationForm):
    email = forms.EmailField(label='E-mail')
    phone_number = forms.CharField(label='Telefone', max_length=15, required=False)

    class Meta(UserCreationForm.Meta):
        model = CustomUser
        fields = ('username', 'email', 'phone_number')
        labels = {'username': 'Nome de usuário'}
        help_texts = {'username': 'Letras, números e @ . + - _'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password1'].help_text = 'Pelo menos 8 caracteres, sem ser só números.'
        self.fields['password2'].help_text = ''
        self.fields['password2'].label = 'Repita a senha'

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        if CustomUser.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('Já existe uma conta com esse e-mail.')
        return email


class EstabelecimentoForm(EstiloBootstrap, forms.ModelForm):
    class Meta:
        model = Estabelecimento
        fields = ['nome', 'endereco', 'telefone', 'descricao_horario']
        labels = {
            'nome': 'Nome da cafeteria',
            'endereco': 'Endereço',
            'telefone': 'Telefone',
            'descricao_horario': 'Horário de funcionamento',
        }
        widgets = {
            'descricao_horario': forms.TextInput(attrs={'placeholder': 'Ex.: Seg a Sex, 7h às 19h'}),
            'endereco': forms.TextInput(attrs={'placeholder': 'Rua, número, bairro'}),
        }


class PratoForm(EstiloBootstrap, forms.ModelForm):
    class Meta:
        model = Prato
        fields = ['nome', 'descricao', 'preco', 'preco_promocional', 'prato_principal']
        labels = {
            'nome': 'Nome do item',
            'descricao': 'Descrição',
            'preco': 'Preço (R$)',
            'preco_promocional': 'Preço promocional (R$)',
            'prato_principal': 'Destacar como prato principal',
        }
        help_texts = {'preco_promocional': 'Deixe em branco se o item não está em promoção.'}
        widgets = {'descricao': forms.Textarea(attrs={'rows': 3})}

    def clean(self):
        data = super().clean()
        preco = data.get('preco')
        promo = data.get('preco_promocional')
        if preco is not None and preco <= 0:
            self.add_error('preco', 'O preço precisa ser maior que zero.')
        if promo is not None and preco is not None and promo >= preco:
            self.add_error('preco_promocional', 'O preço promocional precisa ser menor que o preço normal.')
        return data


class FeedbackForm(EstiloBootstrap, forms.ModelForm):
    rating = forms.TypedChoiceField(
        label='Nota',
        choices=[(i, str(i)) for i in range(5, 0, -1)],
        coerce=int,
        widget=forms.RadioSelect,
    )

    class Meta:
        model = Feedback
        fields = ['rating', 'comment']
        labels = {'comment': 'Comentário'}
        widgets = {'comment': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Como foi o café, o atendimento, o ambiente?'})}


class ReservaForm(EstiloBootstrap, forms.ModelForm):
    data_hora = forms.DateTimeField(
        label='Data e horário',
        input_formats=['%Y-%m-%dT%H:%M'],
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
    )
    numero_pessoas = forms.IntegerField(label='Número de pessoas', min_value=1, max_value=30)

    class Meta:
        model = Reserva
        fields = ['data_hora', 'numero_pessoas']

    def clean_data_hora(self):
        data_hora = self.cleaned_data['data_hora']
        if data_hora <= timezone.now():
            raise forms.ValidationError('Escolha um horário no futuro.')
        return data_hora


class ItemEsquecidoForm(EstiloBootstrap, forms.ModelForm):
    class Meta:
        model = ItemEsquecido
        fields = ['descricao']
        labels = {'descricao': 'O que você esqueceu?'}
        widgets = {'descricao': forms.TextInput(attrs={'placeholder': 'Ex.: guarda-chuva preto, perto da janela'})}
