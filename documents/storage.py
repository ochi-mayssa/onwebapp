"""Private file storage for generated documents and client signatures.

These files must never be reachable through ``MEDIA_URL``. They are only
served by the authenticated/token-gated views in ``documents.views``.
"""
import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage


class PrivateDocumentStorage(FileSystemStorage):
    """File system storage rooted outside the public media directory.

    ``base_location`` is resolved lazily so test overrides of
    ``PRIVATE_MEDIA_ROOT`` are respected instead of leaking files into the
    project directory.
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('base_url', None)
        super().__init__(*args, **kwargs)

    @property
    def base_location(self):
        return settings.PRIVATE_MEDIA_ROOT

    @property
    def location(self):
        return os.path.abspath(self.base_location)


private_document_storage = PrivateDocumentStorage()
