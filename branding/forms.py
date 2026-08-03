from django import forms

from .models import (
    BRAND_VALUES,
    CURRENT_BRANDING_CHOICES,
    INDUSTRY_CHOICES,
    PREFERRED_COLORS,
    CONCEPT_TAGS,
    RATING_ELEMENTS,
    ANNOTATION_TYPES,
    REFINEMENT_STATUSES,
    SESSION_STATUSES,
    BrandingRequest,
    DesignConcept,
    ConceptImage,
    ConceptElementRating,
    ConceptAnnotation,
    ConceptFeedback,
    ConceptStickyNote,
    ConceptRefinement,
    ConceptRefinementIteration,
    ConceptComparison,
    ConceptPresentationSession,
    Questionnaire,
    Question,
    QuestionCondition,
    Answer,
    QuestionnaireTemplate,
    DecisionPoint,
    ClientPreferenceProfile,
    QUESTION_TYPES,
    QUESTION_IMPORTANCE,
    DESIGN_PHASES,
    QUESTION_CATEGORIES,
    DECISION_STATUSES,
    CollectionTemplate,
    COLLECTION_TEMPLATE_TYPES,
)


class BrandingRequestForm(forms.ModelForm):
    """Full edit form used by staff on the request detail / dashboard."""

    brand_values = forms.MultipleChoiceField(
        choices=BRAND_VALUES,
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )
    preferred_colors = forms.MultipleChoiceField(
        choices=PREFERRED_COLORS,
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )
    current_branding = forms.MultipleChoiceField(
        choices=CURRENT_BRANDING_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )

    class Meta:
        model = BrandingRequest
        fields = [
            'company_name',
            'industry',
            'website',
            'country',
            'business_description',
            'company_description',
            'target_audience',
            'brand_values',
            'preferred_colors',
            'current_branding',
            'additional_notes',
            'collection',
            'status',
            'designer',
            'priority',
            'estimated_delivery_date',
            'internal_notes',
        ]
        widgets = {
            'business_description': forms.Textarea(attrs={'rows': 4}),
            'company_description': forms.Textarea(attrs={'rows': 4}),
            'target_audience': forms.Textarea(attrs={'rows': 4}),
            'internal_notes': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['industry'].widget = forms.Select(choices=INDUSTRY_CHOICES)
        # Priority defaults to MEDIUM at the model level; never require it in forms.
        self.fields['priority'].required = False
        instance = kwargs.get('instance')
        if instance:
            for field, values in (
                ('brand_values', instance.brand_values or []),
                ('preferred_colors', instance.preferred_colors or []),
                ('current_branding', instance.current_branding or []),
            ):
                self.fields[field].initial = values

    def clean(self):
        cleaned = super().clean()
        for field in ('brand_values', 'preferred_colors', 'current_branding'):
            cleaned[field] = list(cleaned.get(field) or [])
        if not cleaned.get('priority'):
            cleaned['priority'] = self.instance.priority or 'MEDIUM'
        return cleaned


# ═══════════════════════════════════════════════════════════════════════════
# Concept Presentation Forms
# ═══════════════════════════════════════════════════════════════════════════

class DesignConceptForm(forms.ModelForm):
    tags = forms.MultipleChoiceField(
        choices=CONCEPT_TAGS,
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )

    class Meta:
        model = DesignConcept
        fields = [
            'title', 'description', 'preview_image', 'color_palette',
            'fonts', 'tags', 'layout_description', 'pros', 'cons',
            'feature_checklist', 'designer_ranking',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'layout_description': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = kwargs.get('instance')
        if instance:
            self.fields['tags'].initial = instance.tags or []
            self.fields['color_palette'].widget = forms.HiddenInput()
            self.fields['fonts'].widget = forms.HiddenInput()
            self.fields['pros'].widget = forms.HiddenInput()
            self.fields['cons'].widget = forms.HiddenInput()
            self.fields['feature_checklist'].widget = forms.HiddenInput()

    def clean(self):
        cleaned = super().clean()
        cleaned['tags'] = list(cleaned.get('tags') or [])
        for field in ('color_palette', 'fonts', 'pros', 'cons', 'feature_checklist'):
            val = cleaned.get(field)
            if isinstance(val, str):
                import json
                try:
                    cleaned[field] = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    cleaned[field] = []
        return cleaned


class ConceptImageForm(forms.ModelForm):
    class Meta:
        model = ConceptImage
        fields = ['image', 'caption', 'image_type', 'sort_order']


class ConceptElementRatingForm(forms.ModelForm):
    class Meta:
        model = ConceptElementRating
        fields = ['element', 'score']
        widgets = {
            'score': forms.NumberInput(attrs={'min': 1, 'max': 5}),
        }


class ConceptAnnotationForm(forms.ModelForm):
    class Meta:
        model = ConceptAnnotation
        fields = ['annotation_type', 'text', 'x_position', 'y_position']
        widgets = {
            'text': forms.Textarea(attrs={'rows': 3}),
            'x_position': forms.HiddenInput(),
            'y_position': forms.HiddenInput(),
        }


class ConceptFeedbackForm(forms.ModelForm):
    class Meta:
        model = ConceptFeedback
        fields = ['overall_rating', 'title', 'feedback_text', 'strengths', 'improvements']
        widgets = {
            'overall_rating': forms.NumberInput(attrs={'min': 1, 'max': 5}),
            'feedback_text': forms.Textarea(attrs={'rows': 4}),
            'strengths': forms.Textarea(attrs={'rows': 3}),
            'improvements': forms.Textarea(attrs={'rows': 3}),
        }


class ConceptStickyNoteForm(forms.ModelForm):
    class Meta:
        model = ConceptStickyNote
        fields = ['text', 'color', 'x_position', 'y_position']
        widgets = {
            'text': forms.Textarea(attrs={'rows': 3}),
            'x_position': forms.HiddenInput(),
            'y_position': forms.HiddenInput(),
        }


class ConceptRefinementForm(forms.ModelForm):
    class Meta:
        model = ConceptRefinement
        fields = ['title', 'description', 'priority']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
        }


class ConceptRefinementIterationForm(forms.ModelForm):
    class Meta:
        model = ConceptRefinementIteration
        fields = ['description', 'before_image', 'after_image']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }


class ConceptComparisonForm(forms.ModelForm):
    class Meta:
        model = ConceptComparison
        fields = ['title', 'concepts', 'notes']
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 3}),
            'concepts': forms.CheckboxSelectMultiple,
        }


class ConceptPresentationSessionForm(forms.ModelForm):
    class Meta:
        model = ConceptPresentationSession
        fields = [
            'title', 'description', 'scheduled_at', 'duration_minutes',
            'meeting_url', 'attendees',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'scheduled_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'attendees': forms.CheckboxSelectMultiple,
        }


class QuestionnaireForm(forms.ModelForm):
    class Meta:
        model = Questionnaire
        fields = [
            'title', 'description', 'phase', 'client', 'send_email', 'expires_at',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'expires_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['client'].widget = forms.Select()
        self.fields['send_email'].required = False
        self.fields['expires_at'].required = False


class QuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = [
            'text', 'description', 'question_type', 'category', 'phase',
            'importance', 'is_required', 'sort_order', 'options', 'scale_min',
            'scale_max', 'scale_labels', 'allow_multiple', 'placeholder',
            'help_text',
        ]
        widgets = {
            'text': forms.Textarea(attrs={'rows': 3}),
            'description': forms.Textarea(attrs={'rows': 2}),
            'options': forms.HiddenInput(),
            'scale_labels': forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].widget = forms.Select(choices=QUESTION_CATEGORIES)
        self.fields['phase'].widget = forms.Select(choices=DESIGN_PHASES)
        self.fields['importance'].widget = forms.Select(choices=QUESTION_IMPORTANCE)
        self.fields['description'].required = False
        self.fields['sort_order'].required = False
        self.fields['scale_min'].required = False
        self.fields['scale_max'].required = False
        self.fields['placeholder'].required = False
        self.fields['help_text'].required = False

    def clean_options(self):
        value = self.cleaned_data.get('options')
        if isinstance(value, str):
            import json
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return []
        return value

    def clean_scale_labels(self):
        value = self.cleaned_data.get('scale_labels')
        if isinstance(value, str):
            import json
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return []
        return value


class QuestionConditionForm(forms.ModelForm):
    class Meta:
        model = QuestionCondition
        fields = ['question', 'depends_on', 'condition_type', 'condition_value']
        widgets = {
            'condition_value': forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['depends_on'].required = False
        self.fields['condition_type'].required = False

    def clean_condition_value(self):
        value = self.cleaned_data.get('condition_value')
        if isinstance(value, str):
            import json
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return {}
        return value


class AnswerForm(forms.ModelForm):
    class Meta:
        model = Answer
        fields = [
            'text_value', 'selected_options', 'rank_order', 'color_value',
            'font_choice', 'scale_value', 'boolean_value', 'image',
        ]
        widgets = {
            'selected_options': forms.HiddenInput(),
            'rank_order': forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['text_value'].required = False
        self.fields['color_value'].required = False
        self.fields['font_choice'].required = False
        self.fields['scale_value'].required = False
        self.fields['boolean_value'].required = False
        self.fields['image'].required = False

    def clean_selected_options(self):
        value = self.cleaned_data.get('selected_options')
        if isinstance(value, str):
            import json
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return []
        return value

    def clean_rank_order(self):
        value = self.cleaned_data.get('rank_order')
        if isinstance(value, str):
            import json
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return []
        return value


class QuestionnaireTemplateForm(forms.ModelForm):
    class Meta:
        model = QuestionnaireTemplate
        fields = [
            'name', 'description', 'phase', 'industry', 'collection',
            'questions_data', 'is_active',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'questions_data': forms.Textarea(attrs={'rows': 6}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['industry'].widget = forms.Select(choices=INDUSTRY_CHOICES)
        self.fields['phase'].widget = forms.Select(choices=DESIGN_PHASES)
        self.fields['is_active'].required = False

    def clean_questions_data(self):
        value = self.cleaned_data.get('questions_data')
        if isinstance(value, str):
            import json
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return []
        return value


class DecisionPointForm(forms.ModelForm):
    class Meta:
        model = DecisionPoint
        fields = ['title', 'description', 'category', 'importance', 'options', 'deadline']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'deadline': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'options': forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].widget = forms.Select(choices=QUESTION_CATEGORIES)
        self.fields['importance'].widget = forms.Select(choices=QUESTION_IMPORTANCE)
        self.fields['deadline'].required = False

    def clean_options(self):
        value = self.cleaned_data.get('options')
        if isinstance(value, str):
            import json
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return []
        return value


class ClientAnswerForm(forms.Form):
    text_value = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}), required=False)
    selected_options = forms.Field(widget=forms.HiddenInput(), required=False)
    scale_value = forms.IntegerField(required=False)
    boolean_value = forms.NullBooleanField(required=False)
    color_value = forms.CharField(widget=forms.TextInput(attrs={'type': 'color'}), required=False)
    font_choice = forms.CharField(widget=forms.Select(), required=False)
    image = forms.ImageField(required=False)

    def clean_selected_options(self):
        value = self.cleaned_data.get('selected_options')
        if isinstance(value, str):
            import json
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return []
        return value


class BulkQuestionForm(forms.Form):
    questions_text = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 10, 'placeholder': 'One question per line, separated by double newlines'}),
        help_text='Enter questions separated by double newlines.',
    )

    def parse_questions(self):
        text = self.cleaned_data.get('questions_text', '')
        blocks = text.strip().split('\n\n')
        questions = []
        for block in blocks:
            lines = block.strip().split('\n')
            if not lines or not lines[0].strip():
                continue
            q = {
                'text': lines[0].strip(),
                'description': lines[1].strip() if len(lines) > 1 else '',
                'question_type': 'TEXT',
                'is_required': True,
                'sort_order': len(questions) + 1,
            }
            questions.append(q)
        return questions


class SmartSuggestionForm(forms.Form):
    industry = forms.ChoiceField(
        choices=[('', '---------')] + list(INDUSTRY_CHOICES),
        required=True,
    )
    collection = forms.CharField(widget=forms.Select(), required=False)
    phase = forms.ChoiceField(
        choices=[('', '---------')] + list(DESIGN_PHASES),
        required=True,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['collection'].widget = forms.Select(choices=[])
        self.fields['phase'].widget = forms.Select(choices=[('', '---------')] + list(DESIGN_PHASES))


class CollectionTemplateForm(forms.ModelForm):
    class Meta:
        model = CollectionTemplate
        fields = ['name', 'description', 'template_type', 'file', 'thumbnail', 'is_active', 'sort_order']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }
