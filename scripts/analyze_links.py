import json
import csv
import re
import sys
from collections import Counter

def load_json(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: File {filepath} not found.")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"Error: Failed to decode JSON from {filepath}.")
        sys.exit(1)

def extract_django_url_name(url_string):
    # Matches {% url 'app:name' ... %} or {% url "app:name" ... %}
    # We want to capture the name inside the quotes
    pattern = r"{%\s*url\s+['\"]([\w:-]+)['\"]"
    match = re.search(pattern, url_string)
    if match:
        return match.group(1)
    return None

def analyze_links(links_path, routes_path):
    links_data = load_json(links_path)
    routes_data = load_json(routes_path)

    # Create a set of valid route names for quick lookup
    # Assuming routes_list.json is a list of dicts with a "name" key
    valid_routes = set()
    for route in routes_data:
        if 'name' in route:
            valid_routes.add(route['name'])

    analyzed_links = []
    
    # Statistics counters
    stats = Counter()

    for entry in links_data:
        url = entry.get('url', '').strip()
        source = entry.get('source', '')
        attribute = entry.get('attribute', '')
        
        link_type = "Unknown"
        resolution = "Non résolue"
        http_test_needed = False

        # 1. Detect Django URL tags
        django_route_name = extract_django_url_name(url)
        
        if django_route_name:
            link_type = "Django Tag"
            if django_route_name in valid_routes:
                resolution = f"Resolved ({django_route_name})"
                http_test_needed = True # Ideally we test the resolved URL, but here we flag it as testable
                stats['internal_resolved'] += 1
            else:
                resolution = f"Failed (Route '{django_route_name}' not found)"
                http_test_needed = False
                stats['unresolved'] += 1
        
        # 2. Absolute URLs
        elif url.startswith('http://') or url.startswith('https://'):
            link_type = "Absolute URL"
            resolution = "Resolved (External)"
            http_test_needed = True
            stats['external'] += 1

        # 3. Relative Paths
        elif url.startswith('/'):
            link_type = "Relative Path"
            resolution = "Resolved (Internal)"
            http_test_needed = True
            stats['internal_resolved'] += 1
        
        # 4. Fragments
        elif url.startswith('#'):
            link_type = "Fragment"
            resolution = "Ignored"
            http_test_needed = False
            stats['ignored'] += 1
            
        # 5. Javascript
        elif url.lower().startswith('javascript:'):
            link_type = "JavaScript"
            resolution = "Ignored"
            http_test_needed = False
            stats['ignored'] += 1

        # 6. Template Variables (simple heuristic)
        elif '{{' in url and '}}' in url:
            link_type = "Template Variable"
            resolution = "Non résolue (Dynamic)"
            http_test_needed = False
            stats['unresolved'] += 1
            
        else:
            link_type = "Other"
            resolution = "Non résolue"
            http_test_needed = False
            stats['unresolved'] += 1

        analyzed_links.append({
            'Type': link_type,
            'URL': url,
            'Source': source,
            'Attribute': attribute,
            'Resolution': resolution,
            'http_test_needed': http_test_needed
        })

    # Sort by Type then URL
    analyzed_links.sort(key=lambda x: (x['Type'], x['URL']))

    # Write to CSV
    output_file = 'links_analysis.csv'
    headers = ['Type', 'URL', 'Source', 'Attribute', 'Resolution', 'http_test_needed']
    
    try:
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(analyzed_links)
        print(f"Successfully generated {output_file}")
    except IOError as e:
        print(f"Error writing CSV: {e}")

    # Print Summary
    print("\n--- Summary ---")
    print(f"Total Links Processed: {len(analyzed_links)}")
    print(f"Internal Links (Resolved): {stats['internal_resolved']}")
    print(f"External Links: {stats['external']}")
    print(f"Unresolved Links: {stats['unresolved']}")
    print(f"Ignored (Fragment/JS): {stats['ignored']}")

if __name__ == "__main__":
    analyze_links('links_report.json', 'routes_list.json')
