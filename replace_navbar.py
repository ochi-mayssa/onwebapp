#!/usr/bin/env python
"""Find and replace navbar section in base.html"""

with open('templates/base.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the navbar section
start = content.find('<ul class="navbar-nav ms-auto">')
if start < 0:
    print("Navbar not found!")
    exit(1)

# Find closing </ul>
closing_count = 0
opening_count = 1
pos = start + len('<ul class="navbar-nav ms-auto">')

for i, char in enumerate(content[pos:pos+50000]):
    if content[pos+i:pos+i+4] == '<ul ':
        opening_count += 1
    elif content[pos+i:pos+i+5] == '</ul>':
        closing_count += 1
        if closing_count == opening_count:
            end = pos + i + 5
            print(f"Found navbar section from position {start} to {end}")
            print(f"Length: {end - start} characters")
            
            # Get line numbers (approximate)
            lines_before = content[:start].count('\n')
            lines_nav = content[start:end].count('\n')
            print(f"Approximately lines {lines_before+1} to {lines_before + lines_nav + 1}")
            
            # Show last 300 chars of navbar
            print("\nLast 300 chars of navbar:")
            print(content[end-300:end])
            print("\nFirst 300 chars after navbar:")
            print(content[end:end+300])
            
            # Read the replacement content
            with open('simplified_base_navbar.html', 'r', encoding='utf-8') as f:
                replacement = f.read()
            
            # Remove the HTML comments
            replacement_clean = replacement.split('-->')[1].strip()
            
            # Replace it
            new_content = content[:start] + replacement_clean + content[end:]
            
            # Save
            with open('templates/base.html', 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            print("\n✅ Navbar replaced successfully!")
            print(f"Removed {end - start} characters")
            print(f"Added {len(replacement_clean)} characters")
            
            break
else:
    print("Could not find closing </ul> tag")
