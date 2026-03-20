from .auth import login_view, logout_view
from .admin_views import gerenciar_usuarios, gerenciar_acessos, deletar_dashboard
from .dashboard import lista_dashboards, dashboard, tabela, upload_planilha
from .analise import graficos, share_estoque, mapa_calor, comparativo, evolucao
from .pricing_views import analise_preco, pricing