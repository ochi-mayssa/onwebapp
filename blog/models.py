from django.db import models
from django.utils.text import slugify
from django.conf import settings


class Article(models.Model):
    TAG_CHOICES = [
        ('Data', 'Data'),
        ('Integration', 'Integration'),
        ('Automation', 'Automation'),
        ('ERP & CRM', 'ERP & CRM'),
        ('IoT', 'IoT'),
    ]

    title = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, blank=True)
    tag = models.CharField(max_length=50, choices=TAG_CHOICES, default='Integration')
    image = models.ImageField(upload_to='blog/articles/', blank=True, null=True)
    service_url = models.CharField(max_length=255, blank=True, help_text='Django URL name for CTA link')
    description = models.TextField(max_length=300)
    content = models.TextField(help_text='HTML content for the article body')
    read_time = models.CharField(max_length=20, default='5 min read')
    is_published = models.BooleanField(default=True)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
            base_slug = self.slug
            counter = 1
            while Article.objects.filter(slug=self.slug).exclude(pk=self.pk).exists():
                self.slug = f'{base_slug}-{counter}'
                counter += 1
        super().save(*args, **kwargs)

    @property
    def formatted_date(self):
        return self.created_at.strftime('%b %d, %Y')


class BlogPost(models.Model):
    TAG_CHOICES = [
        ('Tips', 'Tips'),
        ('Update', 'Update'),
        ('How-To', 'How-To'),
        ('News', 'News'),
    ]

    TAG_CLASSES = {
        'Tips': 'blog-tag--tips',
        'Update': 'blog-tag--update',
        'How-To': 'blog-tag--howto',
        'News': 'blog-tag--news',
    }

    title = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, blank=True)
    tag = models.CharField(max_length=50, choices=TAG_CHOICES, default='Tips')
    image = models.ImageField(upload_to='blog/posts/', blank=True, null=True)
    description = models.TextField(max_length=300)
    content = models.TextField(help_text='HTML content for the blog post body')
    read_time = models.CharField(max_length=20, default='3 min')
    is_published = models.BooleanField(default=True)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
            base_slug = self.slug
            counter = 1
            while BlogPost.objects.filter(slug=self.slug).exclude(pk=self.pk).exists():
                self.slug = f'{base_slug}-{counter}'
                counter += 1
        super().save(*args, **kwargs)

    @property
    def tag_class(self):
        return self.TAG_CLASSES.get(self.tag, 'blog-tag--tips')

    @property
    def formatted_date(self):
        return self.created_at.strftime('%b %d, %Y')
