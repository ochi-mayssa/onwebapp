"""Rebuild the chatbot's search index from the site's own content."""
import time

from django.core.management.base import BaseCommand

from chatbot.indexer import build_and_save, index_stats
from chatbot.search import answer


class Command(BaseCommand):
    help = ('Rebuild the chatbot index so it can answer questions about every '
            'page and database record on the site.')

    def add_arguments(self, parser):
        parser.add_argument(
            '--query', action='append', default=[], dest='queries',
            help='Ask a sample question after building. May be repeated.')

    def handle(self, *args, **options):
        started = time.time()
        index = build_and_save()

        stats = index_stats(index)
        self.stdout.write(self.style.SUCCESS('Chatbot index rebuilt in %.1fs' % (time.time() - started)))
        self.stdout.write('  chunks : %d' % stats['chunks'])
        self.stdout.write('  sources: %d' % stats['sources'])
        self.stdout.write('  terms  : %d' % stats['terms'])
        self.stdout.write('  live pages: %d' % len(index.get('live_paths', [])))

        access_counts = {}
        for chunk in index['chunks']:
            access_counts[chunk['access']] = access_counts.get(chunk['access'], 0) + 1
        for level in ('public', 'auth', 'staff'):
            if level in access_counts:
                self.stdout.write('  %-6s chunks: %d' % (level, access_counts[level]))

        for question in options['queries']:
            result = answer(question, index=index)
            self.stdout.write('')
            self.stdout.write('Q: %s' % question)
            self.stdout.write('A [%s]: %s' % (result['confidence'], result['response']))
            for link in result['links']:
                self.stdout.write('   -> %s' % link['url'])
