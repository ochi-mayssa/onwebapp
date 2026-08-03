"""Seed the Brand Collection library with curated collections + generated covers."""
import os
import random

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from branding.models import BrandCollection

PALETTES = {
    'manufacturing': (('#1e293b', '#f59e0b'), ('#0f172a', '#e11d48')),
    'healthcare': (('#0ea5e9', '#f0f9ff'), ('#0891b2', '#164e63')),
    'restaurant': (('#b45309', '#fde68a'), ('#7f1d1d', '#fbbf24')),
    'construction': (('#f59e0b', '#451a03'), ('#57534e', '#e7e5e4')),
    'education': (('#2563eb', '#93c5fd'), ('#4338ca', '#a5b4fc')),
    'finance': (('#0f172a', '#38bdf8'), ('#14532d', '#86efac')),
    'real_estate': (('#334155', '#f1f5f9'), ('#b45309', '#ffedd5')),
    'saas': (('#6366f1', '#c7d2fe'), ('#0e7490', '#a5f3fc')),
}

COLLECTIONS = {
    'manufacturing': [
        {
            'name': 'Foundry & Forge',
            'industry': 'Industrial Manufacturing',
            'description': 'Heavy-duty identity for precision manufacturers. Bold geometry, steel tones and heat accents that signal strength and reliability.',
            'style_tags': ['Industrial', 'Bold', 'Premium'],
            'examples': ['Logo suite', 'Product labels', 'Factory signage', 'Trade-show kit'],
        },
        {
            'name': 'Precision Steel',
            'industry': 'Metal & Components',
            'description': 'Corporate identity built on clean lines and technical precision, engineered for B2B suppliers and component makers.',
            'style_tags': ['Corporate', 'Modern', 'Minimal'],
            'examples': ['Stationery', 'Catalogs', 'Certification pack', 'Website'],
        },
        {
            'name': 'NextGear Automation',
            'industry': 'Automation & Robotics',
            'description': 'Forward-thinking brand system for automation companies blending industrial heritage with a digital-first future.',
            'style_tags': ['Modern', 'Innovative', 'Corporate'],
            'examples': ['Brand book', 'Booth graphics', 'Product UI', 'Motion kit'],
        },
    ],
    'healthcare': [
        {
            'name': 'PureCare Health',
            'industry': 'Clinics & Care',
            'description': 'Calm, trustworthy identity for healthcare providers. Soft blues and airy whites that put patients at ease.',
            'style_tags': ['Friendly', 'Minimal', 'Professional'],
            'examples': ['Patient materials', 'Signage', 'Forms', 'Website'],
        },
        {
            'name': 'Vitality Med',
            'industry': 'Medical & Pharma',
            'description': 'Premium medical brand system with a confident, clinical edge for pharma and medical technology companies.',
            'style_tags': ['Premium', 'Modern', 'Professional'],
            'examples': ['Logo system', 'Packaging', 'Clinical deck', 'Brand guidelines'],
        },
        {
            'name': 'Nova Wellness',
            'industry': 'Wellness & Spas',
            'description': 'Soothing, holistic identity for wellness brands. Organic shapes and refreshing gradients.',
            'style_tags': ['Minimal', 'Friendly', 'Creative'],
            'examples': ['Spa collateral', 'App icons', 'Retail packaging', 'Social kit'],
        },
    ],
    'restaurant': [
        {
            'name': 'Ember & Oak',
            'industry': 'Fine Dining',
            'description': 'Warm, luxurious identity for upscale restaurants. Charred tones, gold accents and artisan typography.',
            'style_tags': ['Luxury', 'Premium', 'Bold'],
            'examples': ['Menu suite', 'Table signage', 'Wine labels', 'Uniform prints'],
        },
        {
            'name': 'Fresh Table',
            'industry': 'Casual Dining',
            'description': 'Bright and friendly brand identity for fast-casual concepts, built to scale from POS screens to storefronts.',
            'style_tags': ['Friendly', 'Modern', 'Minimal'],
            'examples': ['Menu boards', 'Packaging', 'Delivery kit', 'Social media'],
        },
        {
            'name': 'Maison Culinaire',
            'industry': 'Catering & Bakery',
            'description': 'Elegant identity for bakeries and caterers, balancing heritage craft with contemporary presentation.',
            'style_tags': ['Premium', 'Minimal', 'Corporate'],
            'examples': ['Boxes & bags', 'Invoice suite', 'Logo lockups', 'Website'],
        },
    ],
    'construction': [
        {
            'name': 'Solid Foundations',
            'industry': 'General Contracting',
            'description': 'Grounding, dependable identity for construction firms. Earthy neutrals and heavy-duty typography.',
            'style_tags': ['Industrial', 'Corporate', 'Bold'],
            'examples': ['Site hoarding', 'Vehicle graphics', 'Proposal template', 'Safety kit'],
        },
        {
            'name': 'Skyline Builders',
            'industry': 'Development',
            'description': 'Modern identity for property developers that pairs structural confidence with urban style.',
            'style_tags': ['Modern', 'Corporate', 'Premium'],
            'examples': ['Sales suite', 'Brochures', 'Signage', 'Render templates'],
        },
        {
            'name': 'IronWorks Group',
            'industry': 'Infrastructure',
            'description': 'Industrial-grade brand system for infrastructure and engineering groups tackling large-scale projects.',
            'style_tags': ['Industrial', 'Bold', 'Corporate'],
            'examples': ['Brand book', 'Bid documents', 'Site branding', 'Uniforms'],
        },
    ],
    'education': [
        {
            'name': 'Bright Minds Academy',
            'industry': 'Schools & Colleges',
            'description': 'Encouraging, warm identity for educational institutions, vibrant yet approachable for students and parents.',
            'style_tags': ['Friendly', 'Modern', 'Creative'],
            'examples': ['Admissions pack', 'Stationery', 'Campus signage', 'Website'],
        },
        {
            'name': "Scholar's Path",
            'industry': 'Higher Education',
            'description': 'Prestigious identity for universities with a classic crest system and refined color palette.',
            'style_tags': ['Premium', 'Corporate', 'Minimal'],
            'examples': ['Diplomas', 'Ceremony kit', 'Guild crest', 'Brand guidelines'],
        },
        {
            'name': 'NextGen Learning',
            'industry': 'EdTech & Training',
            'description': 'Innovative, playful identity for edtech startups and modern training providers.',
            'style_tags': ['Innovative', 'Modern', 'Friendly'],
            'examples': ['App design', 'Course deck', 'Social kit', 'Event visuals'],
        },
    ],
    'finance': [
        {
            'name': 'Apex Capital',
            'industry': 'Investment',
            'description': 'Commanding, luxurious identity for investment and private equity firms that demand gravitas.',
            'style_tags': ['Luxury', 'Premium', 'Corporate'],
            'examples': ['Fund decks', 'Letterhead', 'Reports', 'Brand book'],
        },
        {
            'name': 'TrustBridge Financial',
            'industry': 'Banking & Insurance',
            'description': 'Stable, reassuring identity for banks and insurers, built on navy, trust and clarity.',
            'style_tags': ['Corporate', 'Professional', 'Minimal'],
            'examples': ['Branch kit', 'Policy documents', 'Cards', 'Website'],
        },
        {
            'name': 'Vertex Banking',
            'industry': 'FinTech',
            'description': 'Sleek, digital-first identity for fintech and neo-banking products with bold color energy.',
            'style_tags': ['Modern', 'Innovative', 'Bold'],
            'examples': ['App kit', 'Card design', 'Launch campaign', 'Website'],
        },
    ],
    'real_estate': [
        {
            'name': 'Haven Estates',
            'industry': 'Residential',
            'description': 'Refined identity for premium residential brokers. Soft neutrals and architectural elegance.',
            'style_tags': ['Luxury', 'Premium', 'Minimal'],
            'examples': ['Listing kit', 'For-sale signage', 'Brochures', 'Agent cards'],
        },
        {
            'name': 'UrbanNest',
            'industry': 'Property Management',
            'description': 'Modern identity for property management and rental platforms, friendly and highly legible.',
            'style_tags': ['Modern', 'Friendly', 'Minimal'],
            'examples': ['Tenant portal', 'Lease templates', 'Wayfinding', 'Website'],
        },
        {
            'name': 'Skyline Property Group',
            'industry': 'Commercial',
            'description': 'Corporate identity for commercial real estate groups, projecting scale and authority.',
            'style_tags': ['Corporate', 'Modern', 'Premium'],
            'examples': ['Investment deck', 'Tower signage', 'Annual report', 'Brand book'],
        },
    ],
    'saas': [
        {
            'name': 'CloudPulse',
            'industry': 'SaaS Platform',
            'description': 'Crisp, modern identity for B2B SaaS, with a flexible gradient system that lives beautifully in product UI.',
            'style_tags': ['Modern', 'Minimal', 'Premium'],
            'examples': ['Dashboard UI', 'Logo suite', 'Marketing site', 'Onboarding kit'],
        },
        {
            'name': 'Nimbus Software',
            'industry': 'Cloud & DevOps',
            'description': 'Technical yet approachable identity for developer tools and infrastructure software.',
            'style_tags': ['Innovative', 'Modern', 'Bold'],
            'examples': ['Docs system', 'CLI art', 'Conference kit', 'Website'],
        },
        {
            'name': 'Quantia Analytics',
            'industry': 'Data & AI',
            'description': 'Intelligent, premium identity for analytics and AI companies, conveying precision and insight.',
            'style_tags': ['Premium', 'Modern', 'Corporate'],
            'examples': ['Report templates', 'Data viz kit', 'Brand guidelines', 'Website'],
        },
    ],
}


def _hex_to_rgb(value):
    value = value.lstrip('#')
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def _lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _generate_cover(category, name, palette, path):
    """Render a premium gradient cover with a subtle geometric pattern."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return False

    W, H = 1200, 800
    top, bottom = _hex_to_rgb(palette[0]), _hex_to_rgb(palette[1])

    img = Image.new('RGB', (W, H))
    draw = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        draw.line([(0, y), (W, y)], fill=_lerp(top, bottom, t))

    overlay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    rng = random.Random(name)
    for _ in range(14):
        cx = rng.randint(-100, W + 100)
        cy = rng.randint(-100, H + 100)
        r = rng.randint(120, 340)
        alpha = rng.randint(12, 40)
        odraw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 255, 255, alpha))
    img = Image.alpha_composite(img.convert('RGBA'), overlay)

    draw = ImageDraw.Draw(img)
    mono = top
    mono = tuple(max(0, int(x * 0.55)) for x in mono)
    font_paths = [
        'C:/Windows/Fonts/arialbd.ttf',
        'C:/Windows/Fonts/segoeuib.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
    ]
    font = None
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                font = ImageFont.truetype(fp, 96)
                break
            except Exception:
                continue
    if font is None:
        font = ImageFont.load_default()

    initials = ''.join(w[0] for w in name.split()[:2]).upper()
    draw.ellipse([80, 80, 230, 230], fill=(255, 255, 255, 40), outline=(255, 255, 255, 120), width=3)
    draw.text((155, 155), initials, font=font, anchor='mm', fill=(255, 255, 255, 235))
    draw.text((80, 640), name, font=font, fill=(255, 255, 255, 240))
    try:
        small = ImageFont.truetype(font_paths[0] if os.path.exists(font_paths[0]) else font_paths[-1], 36)
    except Exception:
        small = font
    draw.text((82, 750), category.title(), font=small, fill=(255, 255, 255, 170))

    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.convert('RGB').save(path, 'JPEG', quality=88)
    return True


class Command(BaseCommand):
    help = 'Seed the branding collection library with curated collections and generated covers.'

    def handle(self, *args, **options):
        cover_dir = os.path.join(settings.MEDIA_ROOT, 'branding', 'collections')
        created = updated = 0
        with transaction.atomic():
            for category, items in COLLECTIONS.items():
                palettes = PALETTES.get(category, (('#6366f1', '#c7d2fe'),))
                for idx, item in enumerate(items):
                    palette = palettes[idx % len(palettes)]
                    rel_path = f'branding/collections/{category}_{idx+1}.jpg'
                    abs_path = os.path.join(settings.MEDIA_ROOT, rel_path)
                    if _generate_cover(category, item['name'], palette, abs_path):
                        image_field = rel_path
                    else:
                        image_field = None

                    obj, created_flag = BrandCollection.objects.update_or_create(
                        slug=item['name'].lower().replace(' ', '-').replace('&', 'and'),
                        defaults={
                            'category': category,
                            'name': item['name'],
                            'industry': item['industry'],
                            'description': item['description'],
                            'style_tags': item['style_tags'],
                            'examples': item['examples'],
                            'preview_image': image_field,
                            'accent_color': palette[1],
                            'is_active': True,
                            'sort_order': idx,
                        },
                    )
                    if created_flag:
                        created += 1
                    else:
                        updated += 1
        self.stdout.write(self.style.SUCCESS(
            f'Brand collections seeded: {created} created, {updated} updated.'
        ))
