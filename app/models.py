from django.db import models

class Empreendimento(models.Model):
    CATEGORIA_CHOICES = [
        ('VA', 'Vertical (Apartamento)'),
        ('LO', 'Loteamento / Cond. Fechado'),
    ]

    nome = models.CharField(max_length=255)
    categoria = models.CharField(max_length=20, choices=CATEGORIA_CHOICES)
    construtora = models.CharField(max_length=255, null=True, blank=True)
    endereco = models.TextField()
    bairro = models.CharField(max_length=100)
    cidade = models.CharField(max_length=100)
    
    # --- AJUSTE: Data de Entrega (Para o filtro de período) ---
    data_entrega = models.DateField(null=True, blank=True) 
    
    unidades_totais = models.IntegerField(default=0)
    unidades_vendidas = models.IntegerField(default=0)  
    percentual_vendido = models.FloatField(default=0.0)
    
    # Financeiros (Dica: Use DecimalField para dinheiro, como você já fez)
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