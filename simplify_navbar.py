#!/usr/bin/env python
"""
Simplify the navbar by grouping items into dropdowns and reducing clutter
"""
import re

# Read the file
with open('templates/base.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Find and replace the navigation section
# Pattern: from navbar-nav ms-auto to before the closing </ul>
navbar_pattern = r'(<ul class="navbar-nav ms-auto">)(.*?)(<li class="nav-item">\s*{% if user\.is_authenticated %}<a class="nav-link")'

new_navbar = r'''<ul class="navbar-nav ms-auto" style="gap: 0.5rem;">
                <!-- Main Navigation (Condensed) -->
                <li class="nav-item">
                    <a class="nav-link" href="{% url 'home:home' %}" title="{% trans 'Home' %}">
                        <i class="fas fa-home"></i>
                    </a>
                </li>
                <li class="nav-item">
                    <a class="nav-link" href="{% url 'projects:team_member_projects' user.username %}" title="{% trans 'Projects' %}">
                        <i class="fas fa-project-diagram"></i>
                    </a>
                </li>
                <!-- Tools Dropdown -->
                <li class="nav-item dropdown">
                    <a class="nav-link dropdown-toggle" href="#" id="toolsDropdown" role="button" data-bs-toggle="dropdown" aria-expanded="false" title="{% trans 'Tools' %}">
                        <i class="fas fa-tools"></i>
                    </a>
                    <ul class="dropdown-menu dropdown-menu-end" aria-labelledby="toolsDropdown">
                        <li><a class="dropdown-item" href="{% url 'seo_analyzer:index' %}"><i class="fas fa-search me-2"></i>{% trans 'SEO Analyzer' %}</a></li>
                        <li><a class="dropdown-item" href="{% url 'services:crawlers_hub' %}"><i class="fas fa-spider me-2"></i>{% trans 'Services' %}</a></li>
                        <li><a class="dropdown-item" href="{% url 'rpa_dashboard:index' %}"><i class="fas fa-robot me-2"></i>{% trans 'RPA' %}</a></li>
                        <li><hr class="dropdown-divider"></li>
                        <li><a class="dropdown-item" href="{% url 'analytics:index' %}"><i class="fas fa-chart-bar me-2"></i>{% trans 'Analytics' %}</a></li>
                    </ul>
                </li>
                <!-- Apps Dropdown -->
                <li class="nav-item dropdown">
                    <a class="nav-link dropdown-toggle" href="#" id="appsDropdown" role="button" data-bs-toggle="dropdown" aria-expanded="false" title="{% trans 'Apps' %}">
                        <i class="fas fa-th-large"></i>
                    </a>
                    <ul class="dropdown-menu dropdown-menu-end" aria-labelledby="appsDropdown">
                        <li><a class="dropdown-item" href="{% url 'community:home' %}"><i class="fas fa-users me-2"></i>{% trans 'Community' %}</a></li>
                        <li><a class="dropdown-item" href="{% url 'crm:dashboard' %}"><i class="fas fa-address-book me-2"></i>{% trans 'CRM' %}</a></li>
                    </ul>
                </li>
                
                <li class="nav-item">\n                    {% if user.is_authenticated %}<a class="nav-link"'''

# Apply the replacement
new_content = re.sub(navbar_pattern, new_navbar, content, flags=re.DOTALL)

# Check if replacement was made
if new_content == content:
    print("❌ Pattern not found, trying alternative approach...")
    # Find the section manually
    start_marker = '<ul class="navbar-nav ms-auto">'
    end_marker = '{% if user.is_authenticated %}<a class="nav-link"'
    
    start_idx = content.find(start_marker)
    end_idx = content.find(end_marker)
    
    if start_idx > 0 and end_idx > start_idx:
        print(f"Found section from {start_idx} to {end_idx}")
        # Extract the old navbar content
        old_navbar = content[start_idx:end_idx]
        print(f"\nOld navbar length: {len(old_navbar)} chars")
        
        # Replace it
        simplified = content[:start_idx] + '''<ul class="navbar-nav ms-auto" style="gap: 0.5rem;">
                <!-- Home -->
                <li class="nav-item">
                    <a class="nav-link" href="{% url 'home:home' %}" title="{% trans 'Home' %}">
                        <i class="fas fa-home"></i>
                    </a>
                </li>
                <!-- Projects -->
                <li class="nav-item">
                    <a class="nav-link" href="{% url 'projects:team_member_projects' user.username %}" title="{% trans 'Projects' %}">
                        <i class="fas fa-project-diagram"></i>
                    </a>
                </li>
                <!-- Tools -->
                <li class="nav-item dropdown">
                    <a class="nav-link dropdown-toggle" href="#" id="toolsDropdown" role="button" data-bs-toggle="dropdown" aria-expanded="false" title="{% trans 'Tools' %}">
                        <i class="fas fa-tools"></i>
                    </a>
                    <ul class="dropdown-menu dropdown-menu-end" aria-labelledby="toolsDropdown">
                        <li><a class="dropdown-item" href="{% url 'seo_analyzer:index' %}"><i class="fas fa-search me-2"></i>SEO Analyzer</a></li>
                        <li><a class="dropdown-item" href="{% url 'services:crawlers_hub' %}"><i class="fas fa-spider me-2"></i>Services</a></li>
                        <li><a class="dropdown-item" href="{% url 'rpa_dashboard:index' %}"><i class="fas fa-robot me-2"></i>RPA</a></li>
                        <li><hr class="dropdown-divider"></li>
                        <li><a class="dropdown-item" href="{% url 'analytics:index' %}"><i class="fas fa-chart-bar me-2"></i>Analytics</a></li>
                    </ul>
                </li>
                <!-- Apps -->
                <li class="nav-item dropdown">
                    <a class="nav-link dropdown-toggle" href="#" id="appsDropdown" role="button" data-bs-toggle="dropdown" aria-expanded="false" title="{% trans 'Apps' %}">
                        <i class="fas fa-th-large"></i>
                    </a>
                    <ul class="dropdown-menu dropdown-menu-end" aria-labelledby="appsDropdown">
                        <li><a class="dropdown-item" href="{% url 'community:home' %}"><i class="fas fa-users me-2"></i>Community</a></li>
                        <li><a class="dropdown-item" href="{% url 'crm:dashboard' %}"><i class="fas fa-address-book me-2"></i>CRM</a></li>
                    </ul>
                </li>
                
                <li class="nav-item">''' + content[end_idx:]
        
        new_content = simplified
        print("✅ Simplified navbar applied!")
    else:
        print(f"Could not find navbar section (start={start_idx}, end={end_idx})")
else:
    print("✅ Pattern replacement successful!")

# Write the updated file
with open('templates/base.html', 'w', encoding='utf-8') as f:
    f.write(new_content)

print("✅ File saved successfully!")
