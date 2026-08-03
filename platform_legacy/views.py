from django.shortcuts import render, get_object_or_404, redirect
from .models import Link
from .forms import LinkForm
from .services import PlatformService


def index(request):
    context = {
        'stats': PlatformService.get_dashboard_stats(),
        'website_tools': PlatformService.get_website_tools(),
        'automation_tools': PlatformService.get_automation_tools(),
    }
    return render(request, 'platform/index.html', context)


def dashboard(request):
    return render(request, 'platform/dashboard.html')


def link_list(request):
    links = Link.objects.all()
    return render(request, 'platform/sections/links_list.html', {'links': links})


def link_create(request):
    form = LinkForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('platform:links')
    return render(request, 'platform/sections/link_form.html', {'form': form})


def link_detail(request, pk):
    link = get_object_or_404(Link, pk=pk)
    return render(request, 'platform/sections/link_detail.html', {'link': link})
