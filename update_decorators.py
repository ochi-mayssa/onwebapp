#!/usr/bin/env python
import re

file_path = 'services/decorators.py'

with open(file_path, 'r') as f:
    content = f.read()

# Replace monthly with daily
replacements = [
    ("'max_queries_per_month': 5", "'max_queries_per_day': 1"),
    ("'max_queries_per_month': 3", "'max_queries_per_day': 1"),
    ("Get the number of times a user has used a specific feature this month", 
     "Get the number of times a user has used a specific feature today"),
    ("Count queries for this feature in the current month",
     "Count queries for this feature in the current day"),
    ("month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)",
     "day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)"),
    ("timestamp__gte=month_start",
     "timestamp__gte=day_start"),
    ("Check if they've reached their limit for this month",
     "Check if they've reached their daily limit"),
    ("max_queries = usage_limit.get('max_queries_per_month', 5)",
     "max_queries = usage_limit.get('max_queries_per_day', 1"),
]

for old, new in replacements:
    content = content.replace(old, new)

with open(file_path, 'w') as f:
    f.write(content)

print('decorators.py updated successfully with daily limits')
