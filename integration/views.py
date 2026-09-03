from django.views.generic import TemplateView


class IntegrationHomepageView(TemplateView):
    template_name = 'integration/integration homepage.html'


class DataIntegrationView(TemplateView):
    template_name = 'integration/dataintegration.html'


class B2BIntegrationView(TemplateView):
    template_name = 'services/b2b_integration.html'


class SystemIntegrationView(TemplateView):
    template_name = 'integration/system_integration.html'


class SocialMediaIntegrationView(TemplateView):
    template_name = 'integration/social_media_integration.html'
