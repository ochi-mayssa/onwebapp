from django.shortcuts import render

# Create your views here.

def index(request):
    """Blog landing page"""
    return render(request, 'blog/index.html')
