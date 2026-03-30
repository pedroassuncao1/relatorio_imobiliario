from django.db import models
from django.contrib.auth.models import AbstractUser


# ==============================
# USUÁRIO CUSTOMIZADO
# ==============================

class Usuario(AbstractUser):
    ROLE_CHOICES = [
        ('admin', 'Administrador'),
        ('viewer', 'Visualizador'),
    ]
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='viewer')

    def is_admin(self):
        return self.role == 'admin'

    def __str__(self):
        return f"{self.username} ({self.role})"


# ==============================
# DASHBOARD
# ==============================

class Dashboard(models.Model):
    TIPO_CHOICES = [
        ('residencial', 'Residencial'),
        ('logistico',   'Logístico'),
    ]

    TODAS_ABAS_RESIDENCIAL = [
        ('dashboard',   'Mapa & KPIs'),
        ('tabela',      'Tabela Analítica'),
        ('graficos',    'Gráficos & Análise'),
        ('pricing',     'Pricing'),
        ('share',       'Share de Estoque'),
        ('mapa_calor',  'Mapa de Calor'),
        ('comparativo', 'Comparativo'),
        ('evolucao',    'Evolução'),
        ('analise',     'Análise de Preço'),
    ]

    TODAS_ABAS_LOGISTICO = [
        ('dashboard',  'Mapa & KPIs'),
        ('abl',        'ABL & Estoque'),
        ('precos',     'Preços'),
        ('distancias', 'Distâncias'),
        ('share',      'Share / Participação'),
    ]

    nome       = models.CharField(max_length=255)
    descricao  = models.TextField(null=True, blank=True)
    tipo       = models.CharField(max_length=20, choices=TIPO_CHOICES, default='residencial')
    criado_por = models.ForeignKey(
        'Usuario',
        on_delete=models.SET_NULL,
        null=True,
        related_name='dashboards_criados'
    )
    criado_em   = models.DateTimeField(auto_now_add=True)
    abas_ativas = models.JSONField(default=list, blank=True)

    # Ponto de referência para cálculo de distâncias (logístico)
    ref_nome      = models.CharField(max_length=255, null=True, blank=True)
    ref_latitude  = models.FloatField(null=True, blank=True)
    ref_longitude = models.FloatField(null=True, blank=True)

    def get_todas_abas(self):
        if self.tipo == 'logistico':
            return self.TODAS_ABAS_LOGISTICO
        return self.TODAS_ABAS_RESIDENCIAL

    def get_abas_ativas(self):
        if not self.abas_ativas:
            return [slug for slug, _ in self.get_todas_abas()]
        return self.abas_ativas

    def aba_ativa(self, slug):
        return slug in self.get_abas_ativas()

    def __str__(self):
        return f"{self.nome} [{self.get_tipo_display()}] — {self.criado_em.strftime('%d/%m/%Y')}"


# ==============================
# ACESSO: usuário <-> dashboard
# ==============================

class AcessoDashboard(models.Model):
    usuario   = models.ForeignKey('Usuario',   on_delete=models.CASCADE, related_name='acessos')
    dashboard = models.ForeignKey('Dashboard', on_delete=models.CASCADE, related_name='acessos')
    liberado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('usuario', 'dashboard')

    def __str__(self):
        return f"{self.usuario.username} → {self.dashboard.nome}"


# ==============================
# EMPREENDIMENTO RESIDENCIAL
# ==============================

class Empreendimento(models.Model):
    CATEGORIA_CHOICES = [
        ('VA', 'Vertical (Apartamento)'),
        ('LO', 'Loteamento / Cond. Fechado'),
    ]

    dashboard   = models.ForeignKey('Dashboard', on_delete=models.CASCADE, related_name='empreendimentos', null=True)
    nome        = models.CharField(max_length=255)
    categoria   = models.CharField(max_length=20, choices=CATEGORIA_CHOICES)
    construtora = models.CharField(max_length=255, null=True, blank=True)
    endereco    = models.TextField()
    bairro      = models.CharField(max_length=100)
    cidade      = models.CharField(max_length=100)
    data_entrega         = models.DateField(null=True, blank=True)
    data_comercializacao = models.DateField(null=True, blank=True)

    unidades_totais    = models.IntegerField(default=0)
    unidades_vendidas  = models.IntegerField(default=0)
    percentual_vendido = models.FloatField(default=0.0)

    preco_medio_m2 = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    preco_unidade  = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    area_unidade   = models.FloatField(null=True)
    estoque        = models.IntegerField(default=0)

    quartos       = models.IntegerField(null=True, blank=True)
    vagas_garagem = models.CharField(max_length=100, null=True, blank=True)
    fase_obra     = models.CharField(max_length=100, null=True, blank=True)
    lazer         = models.TextField(null=True, blank=True)

    latitude  = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    data_importacao = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.nome} - {self.bairro}"


# ==============================
# EMPREENDIMENTO LOGÍSTICO
# ==============================

class EmpreendimentoLogistico(models.Model):
    """
    Cada registro pode ser:
    - Empreendimento-raiz (empreendimento_principal=None): tem numero, galpoes, vacancia, lat/lng
    - Tipologia de módulo (empreendimento_principal preenchido): sub-linha com área/preço específico
    """
    dashboard = models.ForeignKey(
        'Dashboard',
        on_delete=models.CASCADE,
        related_name='empreendimentos_logisticos',
        null=True
    )

    empreendimento_principal = models.ForeignKey(
        'self',
        null=True, blank=True,
        on_delete=models.CASCADE,
        related_name='tipologias'
    )

    # Identificação
    numero       = models.IntegerField(null=True, blank=True)
    nome         = models.CharField(max_length=255)
    endereco     = models.TextField(null=True, blank=True)
    cidade       = models.CharField(max_length=100, null=True, blank=True)
    construtora  = models.CharField(max_length=255, null=True, blank=True)
    proprietario = models.CharField(max_length=500, null=True, blank=True)
    fase_obra    = models.CharField(max_length=100, null=True, blank=True)

    # Quantitativos
    num_galpoes         = models.IntegerField(null=True, blank=True)
    num_modulos         = models.IntegerField(null=True, blank=True)
    modulos_ocupados    = models.IntegerField(null=True, blank=True)
    modulos_disponiveis = models.IntegerField(null=True, blank=True)

    # Preços por M²
    preco_m2_locacao    = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    preco_m2_condominio = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    preco_m2_iptu       = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    # Preços totais mensais
    preco_locacao    = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    preco_condominio = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    preco_iptu       = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    # Área
    area_modulo_m2 = models.FloatField(null=True, blank=True)
    abl_m2         = models.FloatField(null=True, blank=True)

    # Vacância (0.0 a 1.0) — preenchida só no empreendimento-raiz
    vacancia = models.FloatField(null=True, blank=True)

    # Geocoding — preenchido só no empreendimento-raiz
    latitude  = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    # Distância até ponto de referência em km (calculada no upload)
    distancia_ref_km = models.FloatField(null=True, blank=True)

    data_importacao = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['numero', 'nome']

    def is_tipologia(self):
        return self.empreendimento_principal_id is not None

    def pct_vacancia(self):
        if self.vacancia is not None:
            return round(self.vacancia * 100, 1)
        return None

    def pct_ocupacao(self):
        v = self.pct_vacancia()
        return round(100 - v, 1) if v is not None else None

    def __str__(self):
        prefix = "  └ " if self.is_tipologia() else ""
        return f"{prefix}{self.nome} — {self.cidade}"