import os, re
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "websity_project.settings")
import django
django.setup()
from django.template.loader import get_template
t = get_template("home/index.html")
html = t.render({})
def c(pat): return len(re.findall(pat, html))
checks = {
    "svcWrap": c('id="svcWrap"'),
    "svcPin": c('id="svcPin"'),
    "svcSlide": c('oh-svc-slide'),
    "svcDot": c('oh-svc-dot'),
    "svcFill": c('id="svcFill"'),
    "svcNum": c('id="svcNum"'),
    "svcJS": c('Scroll-pinned services'),
    "webDev": c('web_development'),
    "erp": c('erp_integration'),
    "branding": c('branding:landing'),
    "automation": c('platform_monitoring:automation'),
    "oldSvcRow": c('oh-svc-row'),
    "oldSvcBlock": c('oh-svc-block'),
}
print("STATUS OK")
for k,v in checks.items(): print(k,v)
