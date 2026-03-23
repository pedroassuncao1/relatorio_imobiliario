from django.contrib import admin
from django.urls import path
from app import views
from app.views import admin_views

urlpatterns = [

    # ── Django Admin nativo ──
    path('admin/', admin.site.urls),

    # ── Auth ──
    path('login/',  views.login_view,  name='login'),
    path('logout/', views.logout_view, name='logout'),

    # ── Lista de dashboards (página inicial após login) ──
    path('dashboards/', views.lista_dashboards, name='lista_dashboards'),

    # ── BI por dashboard ──
    path('dashboard/<int:dashboard_id>/', views.dashboard, name='dashboard'),

    # ── Upload (só admin) ──
    path('upload/', views.upload_planilha, name='upload_planilha'),

    # ── Gestão de usuários (só admin) ──
    path('admin-panel/usuarios/', views.gerenciar_usuarios, name='gerenciar_usuarios'),

    # ── Gestão de acessos (só admin) ──
    path('admin-panel/acessos/', views.gerenciar_acessos, name='gerenciar_acessos'),

    # ── Deletar dashboard (só admin) ──
    path('dashboard/<int:dashboard_id>/deletar/', views.deletar_dashboard, name='deletar_dashboard'),

    # ── Redireciona raiz para dashboards ──
    path('', views.lista_dashboards, name='home'),

    # Página de tabela analitica (exibe tabela filtrada e geocodificada)
    path('dashboard/<int:dashboard_id>/tabela/', views.tabela, name='tabela'),

    # Página de gráficos (exibe gráficos dinâmicos baseados nos dados)
    path('dashboard/<int:dashboard_id>/graficos/', views.graficos, name='graficos'),

    # Página de insights (exibe insights gerados pela IA)
    path('dashboard/<int:dashboard_id>/share-estoque/', views.share_estoque, name='share_estoque'),

    # Página de mapa de calor (exibe mapa de calor geocodificado)
    path('dashboard/<int:dashboard_id>/mapa-calor/', views.mapa_calor, name='mapa_calor'),

    # Página de comparativo (exibe comparação entre empreendimentos)
    path('dashboard/<int:dashboard_id>/comparativo/', views.comparativo, name='comparativo'),

    # Página de evolução (exibe evolução temporal das vendas)
    path('dashboard/<int:dashboard_id>/evolucao/', views.evolucao, name='evolucao'),

    # Página de análise de preço (exibe análise de preço por m2 e unidade)
    path('dashboard/<int:dashboard_id>/analise-preco/', views.analise_preco, name='analise_preco'),

    # Página de análise de estoque (exibe análise de estoque e vendas)
    path('dashboard/<int:dashboard_id>/pricing/', views.pricing, name='pricing'),

    # Página de edição de abas (só admin)
    path('dashboard/<int:dashboard_id>/editar-abas/', admin_views.editar_abas_dashboard, name='editar_abas_dashboard'),
]