from django import forms
from django.utils.text import slugify
from .models import ForumPost, ForumComment, ForumReport, ForumJob, ForumEvent


class ForumPostForm(forms.ModelForm):
    tags_input = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'wizard-input',
            'placeholder': 'e.g. django, react, seo',
            'data-role': 'tagsinput',
        }),
        help_text='Comma-separated tags',
    )

    class Meta:
        model = ForumPost
        fields = [
            'title', 'category', 'content', 'featured_image',
            'status', 'is_showcase', 'project_name', 'tech_stack',
            'github_link', 'live_demo',
        ]
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'wizard-input', 'placeholder': 'Give your post a clear title',
            }),
            'category': forms.Select(attrs={'class': 'wizard-input'}),
            'content': forms.Textarea(attrs={
                'class': 'wizard-input', 'rows': 15,
                'placeholder': 'Write your post content here... Markdown supported.',
                'data-provider': 'markdown',
            }),
            'featured_image': forms.URLInput(attrs={
                'class': 'wizard-input', 'placeholder': 'https://example.com/image.jpg',
            }),
            'status': forms.Select(attrs={'class': 'wizard-input'}),
            'project_name': forms.TextInput(attrs={
                'class': 'wizard-input', 'placeholder': 'Your project name',
            }),
            'tech_stack': forms.TextInput(attrs={
                'class': 'wizard-input', 'placeholder': 'e.g. Django, React, PostgreSQL',
            }),
            'github_link': forms.URLInput(attrs={
                'class': 'wizard-input', 'placeholder': 'https://github.com/your/repo',
            }),
            'live_demo': forms.URLInput(attrs={
                'class': 'wizard-input', 'placeholder': 'https://your-demo.com',
            }),
        }

    def clean_title(self):
        title = self.cleaned_data['title']
        if len(title) < 10:
            raise forms.ValidationError('Title must be at least 10 characters.')
        return title

    def clean_content(self):
        content = self.cleaned_data['content']
        if len(content) < 50:
            raise forms.ValidationError('Content must be at least 50 characters.')
        return content

    def save(self, commit=True):
        instance = super().save(commit=False)
        tags_input = self.cleaned_data.get('tags_input', '')
        if commit:
            instance.save()
            self._save_tags(instance, tags_input)
        return instance

    def _save_tags(self, instance, tags_input):
        from .models import ForumTag
        instance.tags.clear()
        if tags_input:
            for name in [t.strip() for t in tags_input.split(',') if t.strip()]:
                tag, _ = ForumTag.objects.get_or_create(
                    slug=slugify(name),
                    defaults={'name': name},
                )
                instance.tags.add(tag)


class ForumCommentForm(forms.ModelForm):
    class Meta:
        model = ForumComment
        fields = ['content']
        widgets = {
            'content': forms.Textarea(attrs={
                'class': 'wizard-input', 'rows': 4,
                'placeholder': 'Write a comment... Markdown supported.',
            }),
        }

    def clean_content(self):
        content = self.cleaned_data['content']
        if len(content) < 2:
            raise forms.ValidationError('Comment is too short.')
        return content


class ForumReportForm(forms.ModelForm):
    class Meta:
        model = ForumReport
        fields = ['reason', 'description']
        widgets = {
            'reason': forms.Select(attrs={'class': 'wizard-input'}),
            'description': forms.Textarea(attrs={
                'class': 'wizard-input', 'rows': 3,
                'placeholder': 'Additional details...',
            }),
        }


class ForumJobForm(forms.ModelForm):
    class Meta:
        model = ForumJob
        fields = [
            'company', 'title', 'job_type', 'description', 'requirements',
            'location', 'is_remote', 'salary_range', 'application_link', 'contact_email',
        ]
        widgets = {
            'company': forms.TextInput(attrs={'class': 'wizard-input'}),
            'title': forms.TextInput(attrs={'class': 'wizard-input'}),
            'job_type': forms.Select(attrs={'class': 'wizard-input'}),
            'description': forms.Textarea(attrs={'class': 'wizard-input', 'rows': 8}),
            'requirements': forms.Textarea(attrs={'class': 'wizard-input', 'rows': 5}),
            'location': forms.TextInput(attrs={'class': 'wizard-input'}),
            'salary_range': forms.TextInput(attrs={'class': 'wizard-input', 'placeholder': 'e.g. $50k-$80k'}),
            'application_link': forms.URLInput(attrs={'class': 'wizard-input'}),
            'contact_email': forms.EmailInput(attrs={'class': 'wizard-input'}),
        }


class ForumEventForm(forms.ModelForm):
    class Meta:
        model = ForumEvent
        fields = [
            'title', 'event_type', 'description', 'location',
            'is_online', 'meeting_link', 'start_date', 'end_date',
            'registration_link', 'is_published',
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'wizard-input'}),
            'event_type': forms.Select(attrs={'class': 'wizard-input'}),
            'description': forms.Textarea(attrs={'class': 'wizard-input', 'rows': 6}),
            'location': forms.TextInput(attrs={'class': 'wizard-input'}),
            'meeting_link': forms.URLInput(attrs={'class': 'wizard-input'}),
            'start_date': forms.DateTimeInput(attrs={'class': 'wizard-input', 'type': 'datetime-local'}),
            'end_date': forms.DateTimeInput(attrs={'class': 'wizard-input', 'type': 'datetime-local'}),
            'registration_link': forms.URLInput(attrs={'class': 'wizard-input'}),
        }


class ForumSearchForm(forms.Form):
    q = forms.CharField(required=False, widget=forms.TextInput(attrs={
        'class': 'wizard-input', 'placeholder': 'Search posts, comments, users...',
    }))
    sort = forms.ChoiceField(required=False, choices=[
        ('newest', 'Newest'),
        ('trending', 'Trending'),
        ('votes', 'Most Votes'),
        ('comments', 'Most Comments'),
    ], widget=forms.Select(attrs={'class': 'wizard-input'}))
    category = forms.ChoiceField(required=False, widget=forms.Select(attrs={'class': 'wizard-input'}))
    tags = forms.CharField(required=False, widget=forms.TextInput(attrs={
        'class': 'wizard-input', 'placeholder': 'Filter by tags',
    }))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import ForumCategory
        categories = ForumCategory.objects.filter(is_active=True)
        self.fields['category'].choices = [('', 'All Categories')] + [
            (c.slug, c.name) for c in categories
        ]