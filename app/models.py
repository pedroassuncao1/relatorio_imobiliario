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
# DASHBOARD (cada upload vira um)
# ==============================

class Dashboard(models.Model):
    nome = models.CharField(max_length=255)
    descricao = models.TextField(null=True, blank=True)
    criado_por = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        related_name='dashboards_criados'
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.nome} — {self.criado_em.strftime('%d/%m/%Y')}"


# ==============================
# ACESSO: usuário <-> dashboard
# ==============================

class AcessoDashboard(models.Model):
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        related_name='acessos'
    )
    dashboard = models.ForeignKey(
        Dashboard,
        on_delete=models.CASCADE,
        related_name='acessos'
    )
    liberado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('usuario', 'dashboard')  # sem duplicatas

    def __str__(self):
        return f"{self.usuario.username} → {self.dashboard.nome}"


# ==============================
# EMPREENDIMENTO (agora vinculado a um Dashboard)
# ==============================

class Empreendimento(models.Model):
    CATEGORIA_CHOICES = [
        ('VA', 'Vertical (Apartamento)'),
        ('LO', 'Loteamento / Cond. Fechado'),
    ]

    # ← FK nova: cada empreendimento pertence a um dashboard
    dashboard = models.ForeignKey(
        Dashboard,
        on_delete=models.CASCADE,
        related_name='empreendimentos',
        null=True
    )

    nome = models.CharField(max_length=255)
    categoria = models.CharField(max_length=20, choices=CATEGORIA_CHOICES)
    construtora = models.CharField(max_length=255, null=True, blank=True)
    endereco = models.TextField()
    bairro = models.CharField(max_length=100)
    cidade = models.CharField(max_length=100)
    data_entrega = models.DateField(null=True, blank=True)
    data_comercializacao = models.DateField(null=True, blank=True)

    unidades_totais = models.IntegerField(default=0)
    unidades_vendidas = models.IntegerField(default=0)
    percentual_vendido = models.FloatField(default=0.0)

    preco_medio_m2 = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    preco_unidade = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    area_unidade = models.FloatField(null=True)
    estoque = models.IntegerField(default=0)

    quartos = models.IntegerField(null=True, blank=True)
    vagas_garagem = models.CharField(max_length=100, null=True, blank=True)
    fase_obra = models.CharField(max_length=100, null=True, blank=True)
    lazer = models.TextField(null=True, blank=True)

    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    data_importacao = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.nome} - {self.bairro}"