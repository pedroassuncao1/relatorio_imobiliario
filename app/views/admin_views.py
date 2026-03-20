from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from ..models import Usuario, Dashboard, AcessoDashboard
from .helpers import admin_required


@admin_required
def gerenciar_usuarios(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'criar':
            username = request.POST.get('username', '').strip()
            password = request.POST.get('password', '').strip()
            role     = request.POST.get('role', 'viewer')
            if Usuario.objects.filter(username=username).exists():
                messages.error(request, f'Usuário "{username}" já existe.')
            else:
                u = Usuario.objects.create_user(username=username, password=password, role=role)
                messages.success(request, f'Usuário "{u.username}" criado com sucesso.')
        elif action == 'deletar':
            uid = request.POST.get('usuario_id')
            try:
                u = Usuario.objects.get(id=uid)
                if u == request.user:
                    messages.error(request, 'Você não pode deletar a si mesmo.')
                else:
                    u.delete()
                    messages.success(request, 'Usuário removido.')
            except Usuario.DoesNotExist:
                messages.error(request, 'Usuário não encontrado.')
        return redirect('gerenciar_usuarios')

    usuarios = Usuario.objects.all().order_by('username')
    return render(request, 'app/gerenciar_usuarios.html', {
        'usuarios': usuarios, 'usuario': request.user,
    })


@admin_required
def gerenciar_acessos(request):
    if request.method == 'POST':
        usuario_id    = request.POST.get('usuario_id')
        dashboard_ids = request.POST.getlist('dashboards')
        try:
            usuario_alvo = Usuario.objects.get(id=usuario_id)
            AcessoDashboard.objects.filter(usuario=usuario_alvo).delete()
            for did in dashboard_ids:
                AcessoDashboard.objects.create(
                    usuario=usuario_alvo,
                    dashboard=Dashboard.objects.get(id=did)
                )
            messages.success(request, f'Acessos de "{usuario_alvo.username}" atualizados.')
        except Exception as e:
            messages.error(request, f'Erro: {e}')
        return redirect('gerenciar_acessos')

    usuarios   = Usuario.objects.filter(role='viewer').order_by('username')
    dashboards = Dashboard.objects.all().order_by('-criado_em')
    usuarios_com_acessos = []
    for u in usuarios:
        ids_liberados = list(AcessoDashboard.objects.filter(usuario=u).values_list('dashboard_id', flat=True))
        usuarios_com_acessos.append({'usuario': u, 'ids_liberados': ids_liberados})

    return render(request, 'app/gerenciar_acessos.html', {
        'usuarios_com_acessos': usuarios_com_acessos,
        'dashboards': dashboards,
        'usuario': request.user,
    })


@admin_required
def deletar_dashboard(request, dashboard_id):
    if request.method == 'POST':
        dash = get_object_or_404(Dashboard, id=dashboard_id)
        nome = dash.nome
        dash.delete()
        messages.success(request, f'Dashboard "{nome}" removido.')
    return redirect('lista_dashboards')