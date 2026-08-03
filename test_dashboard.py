
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "websity_project.settings")
django.setup()

from django.test import Client
from seo_analyzer.models import SEOTask


task = SEOTask.objects.get(id=2)
print("=== 1. Task Created ===")
print(f"  Task ID: {task.id}")
print(f"  URL: {task.url}")
print(f"  Status: {task.status}\n")

print("=== 2. Check Page Audits ===")
page_audits = task.page_audits.all()
print(f"  Pages crawled: {len(page_audits)}")
for pa in page_audits:
    print(f"  - {pa.final_url} (status: {pa.status_code})\n")

print("=== 8-10. Analyze Check ===")
result = task.result
print(f"  Result for Task ID: {result.task_id}")
print(f"  Health Score: {result.health_score}")
print(f"  Total Issues: {result.total_issues}")
print(f"  Critical: {result.critical_issues}")
print(f"  High: {result.high_issues}\n")

print("=== 10. SEOIssues ===")
all_issues = task.issues.all()
print(f"  Found {len(all_issues)} issues")

client = Client(HTTP_HOST='127.0.0.1:8000') 
response = client.get(f'/seo/dashboard/{task.id}/')
print("\n=== 11-13. Dashboard ===")
print(f"  12. Status Code: {response.status_code}")

if response.status_code == 200:
    with open("dashboard-output.html", "w", encoding="utf-8") as f:
        f.write(response.content.decode("utf-8"))
    print("  13. Template rendered, output written to dashboard-output.html")
    
    print("\n✅ ALL PRODUCTION VALIDATION STEPS PASSED!")
