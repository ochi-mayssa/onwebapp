"""Seed default questionnaire templates for each design phase."""
from django.core.management.base import BaseCommand


TEMPLATES = [
    {
        'name': 'Brand Discovery',
        'description': 'Comprehensive brand discovery questionnaire covering mission, values, audience, and competitors.',
        'phase': 'discovery',
        'questions_data': [
            {'text': 'What is your company mission statement?', 'type': 'long_text', 'category': 'direction', 'importance': 'critical', 'required': True, 'placeholder': 'Describe your mission in 2-3 sentences...'},
            {'text': 'What are your core brand values?', 'type': 'multiple_choice', 'category': 'direction', 'importance': 'critical', 'required': True, 'options': ['Innovation', 'Trust', 'Quality', 'Simplicity', 'Luxury', 'Sustainability', 'Community', 'Excellence'], 'allow_multiple': True},
            {'text': 'Who is your primary target audience?', 'type': 'short_text', 'category': 'general', 'importance': 'critical', 'required': True, 'placeholder': 'e.g., Young professionals aged 25-40'},
            {'text': 'Describe your brand personality in 3 adjectives.', 'type': 'short_text', 'category': 'tone', 'importance': 'important', 'required': True, 'placeholder': 'e.g., Bold, Modern, Approachable'},
            {'text': 'Who are your main competitors?', 'type': 'long_text', 'category': 'general', 'importance': 'important', 'required': False, 'placeholder': 'List 3-5 competitors and what makes them stand out...'},
            {'text': 'What problem does your business solve?', 'type': 'long_text', 'category': 'direction', 'importance': 'critical', 'required': True, 'placeholder': 'Describe the core problem you address...'},
            {'text': 'How would you rate your current brand on a scale of 1-10?', 'type': 'preference_scale', 'category': 'direction', 'importance': 'nice_to_know', 'required': False, 'scale_min': 1, 'scale_max': 10, 'scale_labels': {'1': 'Needs complete overhaul', '10': 'Already perfect'}},
            {'text': 'What are your top 3 business goals for the next year?', 'type': 'long_text', 'category': 'general', 'importance': 'important', 'required': True, 'placeholder': '1. Goal one\n2. Goal two\n3. Goal three'},
        ],
    },
    {
        'name': 'Concept Direction',
        'description': 'Help narrow down the design direction with preference questions.',
        'phase': 'concept_direction',
        'questions_data': [
            {'text': 'Which design style resonates most with your brand?', 'type': 'multiple_choice', 'category': 'direction', 'importance': 'critical', 'required': True, 'options': ['Modern & Minimalist', 'Classic & Timeless', 'Bold & Dynamic', 'Elegant & Luxurious', 'Playful & Creative', 'Corporate & Professional']},
            {'text': 'Do you prefer more whitespace or more visual density?', 'type': 'yes_no', 'category': 'layout', 'importance': 'important', 'required': True},
            {'text': 'Should the design feel more corporate or more creative?', 'type': 'preference_scale', 'category': 'tone', 'importance': 'important', 'required': True, 'scale_min': 1, 'scale_max': 10, 'scale_labels': {'1': 'Very Corporate', '10': 'Very Creative'}},
            {'text': 'Upload any reference designs or inspiration images.', 'type': 'image_upload', 'category': 'imagery', 'importance': 'nice_to_know', 'required': False, 'max_file_size_mb': 10},
            {'text': 'Are there any designs or brands you specifically do NOT want to emulate?', 'type': 'long_text', 'category': 'direction', 'importance': 'important', 'required': False, 'placeholder': 'Describe styles or brands to avoid...'},
            {'text': 'Do you want the design to include photographic elements or purely graphic?', 'type': 'multiple_choice', 'category': 'imagery', 'importance': 'important', 'required': True, 'options': ['Photography-focused', 'Graphic/illustration-focused', 'Mixed both']},
        ],
    },
    {
        'name': 'Color & Typography',
        'description': 'Gather preferences for color palette and typography choices.',
        'phase': 'color_typography',
        'questions_data': [
            {'text': 'Pick your preferred primary color.', 'type': 'color_picker', 'category': 'colors', 'importance': 'critical', 'required': True},
            {'text': 'Pick your preferred secondary color.', 'type': 'color_picker', 'category': 'colors', 'importance': 'important', 'required': True},
            {'text': 'Which color palette direction appeals to you?', 'type': 'multiple_choice', 'category': 'colors', 'importance': 'critical', 'required': True, 'options': ['Warm tones (reds, oranges, yellows)', 'Cool tones (blues, greens, purples)', 'Neutral tones (grays, beiges, whites)', 'Vibrant & saturated', 'Muted & desaturated', 'Monochromatic']},
            {'text': 'Do you prefer serif or sans-serif fonts?', 'type': 'multiple_choice', 'category': 'typography', 'importance': 'critical', 'required': True, 'options': ['Sans-serif (modern, clean)', 'Serif (traditional, elegant)', 'No preference']},
            {'text': 'Select your preferred font style.', 'type': 'font_selection', 'category': 'typography', 'importance': 'important', 'required': True},
            {'text': 'How should the typography feel?', 'type': 'preference_scale', 'category': 'typography', 'importance': 'important', 'required': True, 'scale_min': 1, 'scale_max': 10, 'scale_labels': {'1': 'Very Formal', '10': 'Very Casual'}},
            {'text': 'Do you want accent colors or a strict two-color palette?', 'type': 'yes_no', 'category': 'colors', 'importance': 'nice_to_know', 'required': False},
        ],
    },
    {
        'name': 'Layout & Structure',
        'description': 'Questions about layout preferences and structural decisions.',
        'phase': 'layout_structure',
        'questions_data': [
            {'text': 'Do you prefer a centered or asymmetric layout?', 'type': 'multiple_choice', 'category': 'layout', 'importance': 'important', 'required': True, 'options': ['Centered & balanced', 'Asymmetric & dynamic', 'No preference']},
            {'text': 'How important is visual hierarchy in your design?', 'type': 'preference_scale', 'category': 'layout', 'importance': 'important', 'required': True, 'scale_min': 1, 'scale_max': 10, 'scale_labels': {'1': 'Not important', '10': 'Extremely important'}},
            {'text': 'Should the layout be grid-based or freeform?', 'type': 'multiple_choice', 'category': 'layout', 'importance': 'nice_to_know', 'required': False, 'options': ['Strict grid', 'Loose grid', 'Freeform', 'No preference']},
            {'text': 'What is the primary call-to-action for your audience?', 'type': 'short_text', 'category': 'direction', 'importance': 'critical', 'required': True, 'placeholder': 'e.g., Sign up, Buy now, Contact us'},
            {'text': 'Do you need the design to be responsive across devices?', 'type': 'yes_no', 'category': 'layout', 'importance': 'critical', 'required': True},
            {'text': 'Upload any layout references or wireframes.', 'type': 'image_upload', 'category': 'layout', 'importance': 'nice_to_know', 'required': False},
        ],
    },
    {
        'name': 'Final Polish',
        'description': 'Final review questions before wrapping up the design process.',
        'phase': 'final_polish',
        'questions_data': [
            {'text': 'On a scale of 1-10, how satisfied are you with the current design?', 'type': 'preference_scale', 'category': 'direction', 'importance': 'critical', 'required': True, 'scale_min': 1, 'scale_max': 10, 'scale_labels': {'1': 'Not satisfied', '10': 'Extremely satisfied'}},
            {'text': 'Are there any final adjustments needed?', 'type': 'long_text', 'category': 'general', 'importance': 'important', 'required': False, 'placeholder': 'Describe any last-minute changes...'},
            {'text': 'Does the final design accurately represent your brand?', 'type': 'yes_no', 'category': 'direction', 'importance': 'critical', 'required': True},
            {'text': 'Would you recommend this design process to others?', 'type': 'rating', 'category': 'general', 'importance': 'nice_to_know', 'required': False},
            {'text': 'Any additional feedback or comments?', 'type': 'long_text', 'category': 'general', 'importance': 'nice_to_know', 'required': False, 'placeholder': 'Share your thoughts on the overall experience...'},
        ],
    },
]


class Command(BaseCommand):
    help = 'Seed default questionnaire templates for each design phase'

    def handle(self, *args, **options):
        from branding.models import QuestionnaireTemplate

        created_count = 0
        updated_count = 0

        for data in TEMPLATES:
            obj, created = QuestionnaireTemplate.objects.update_or_create(
                name=data['name'],
                defaults={
                    'description': data['description'],
                    'phase': data['phase'],
                    'questions_data': data['questions_data'],
                    'is_active': True,
                },
            )
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f'Created: {obj.name}'))
            else:
                updated_count += 1
                self.stdout.write(self.style.WARNING(f'Updated: {obj.name}'))

        self.stdout.write(self.style.SUCCESS(
            f'Done! Created: {created_count}, Updated: {updated_count}'
        ))
