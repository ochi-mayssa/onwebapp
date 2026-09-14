
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "websity_project.settings")
django.setup()

from django.test import Client


client = Client(HTTP_HOST='127.0.0.1:8000')
response = client.get('/seo/')
print(f"Index Page Status Code: {response.status_code}")

if response.status_code == 200:
    print("Index Page Loaded Successfully!")

with open('index-output.html', 'w', encoding='utf-8') as f:
    f.write(response.content.decode('utf-8'))
