"""File upload security for the Branding Service.

Provides:
- MIME type validation using python-magic (content-based, not extension-based)
- ClamAV virus scanning (optional, via clamd TCP socket)
- File size limits per asset type
- Filename sanitization
- Security audit logging
"""
import hashlib
import logging
import os
import re
import socket
import tempfile
import unicodedata

from django.conf import settings
from django.core.files.uploadedfile import InMemoryUploadedFile, TemporaryUploadedFile

logger = logging.getLogger('branding.security')


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Max file sizes per asset type (bytes)
ASSET_SIZE_LIMITS = {
    'logo':             5 * 1024 * 1024,       #   5 MB
    'brand_guidelines': 20 * 1024 * 1024,      #  20 MB
    'inspiration':      10 * 1024 * 1024,      #  10 MB
    'image':            10 * 1024 * 1024,      #  10 MB
    'document':         15 * 1024 * 1024,      #  15 MB
    'archive':          20 * 1024 * 1024,      #  20 MB
    'other':            15 * 1024 * 1024,      #  15 MB
}

# Global fallback limit
GLOBAL_MAX_SIZE = max(ASSET_SIZE_LIMITS.values())

# Allowed MIME types grouped by asset type
ALLOWED_MIMES = {
    'logo': {
        'image/png', 'image/jpeg', 'image/svg+xml', 'image/gif',
        'image/webp', 'image/bmp', 'application/postscript',
        'application/x-illustrator', 'application/pdf',
    },
    'brand_guidelines': {
        'application/pdf',
        'application/msword',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/vnd.ms-powerpoint',
        'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    },
    'inspiration': {
        'image/png', 'image/jpeg', 'image/gif', 'image/webp',
        'image/bmp', 'image/tiff', 'image/svg+xml',
    },
    'image': {
        'image/png', 'image/jpeg', 'image/gif', 'image/webp',
        'image/bmp', 'image/tiff', 'image/svg+xml',
    },
    'document': {
        'application/pdf',
        'application/msword',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/vnd.ms-excel',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/vnd.ms-powerpoint',
        'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        'text/plain', 'text/csv',
    },
    'archive': {
        'application/zip', 'application/x-rar-compressed',
        'application/vnd.rar', 'application/x-7z-compressed',
        'application/x-tar', 'application/gzip',
    },
}

# Dangerous MIME types that should never be uploaded
BLOCKED_MIMES = {
    'application/x-executable',
    'application/x-dosexec',
    'application/x-msdownload',
    'application/x-msdos-program',
    'application/x-elf',
    'application/x-mach-binary',
    'application/java-archive',
    'application/x-java-applet',
    'application/x-shockwave-flash',
    'application/x-httpd-php',
    'text/x-python', 'text/x-perl', 'text/x-shellscript',
    'text/x-script.php', 'text/x-bash',
}

# Filename sanitization
_SAFE_FILENAME_RE = re.compile(r'[^\w\s\-_.]', re.UNICODE)
_MULTI_DASH_RE = re.compile(r'[-_]{2,}')
_MAX_FILENAME_LEN = 200


# ---------------------------------------------------------------------------
# MIME detection (python-magic)
# ---------------------------------------------------------------------------

def detect_mime_type(uploaded_file):
    """Detect the real MIME type of a file by reading its magic bytes.

    Uses python-magic (libmagic bindings). Falls back to content_type
    if detection fails.
    """
    try:
        import magic

        # For small in-memory files, read a chunk
        if isinstance(uploaded_file, InMemoryUploadedFile):
            uploaded_file.seek(0)
            header = uploaded_file.read(8192)
            uploaded_file.seek(0)
            mime = magic.from_buffer(header, mime=True)
        elif isinstance(uploaded_file, TemporaryUploadedFile):
            mime = magic.from_file(uploaded_file.temporary_file_path(), mime=True)
        else:
            uploaded_file.seek(0)
            header = uploaded_file.read(8192)
            uploaded_file.seek(0)
            mime = magic.from_buffer(header, mime=True)

        return mime or ''
    except ImportError:
        logger.warning('python-magic not installed; falling back to content_type')
        return getattr(uploaded_file, 'content_type', '') or ''
    except Exception as exc:
        logger.error('MIME detection failed: %s', exc)
        return getattr(uploaded_file, 'content_type', '') or ''


def validate_mime_type(uploaded_file, asset_type):
    """Validate the detected MIME type against the allowed list.

    Returns (is_valid, detected_mime, reason).
    """
    detected = detect_mime_type(uploaded_file)

    # Block dangerous types unconditionally
    if detected in BLOCKED_MIMES:
        return False, detected, f'Blocked dangerous file type: {detected}'

    # Check against asset-type-specific allowlist
    allowed = ALLOWED_MIMES.get(asset_type, set())
    if allowed and detected not in allowed:
        # Also accept common variants
        base = detected.split('/')[0] if '/' in detected else ''
        if not any(detected.startswith(a.split('/')[0] + '/') for a in allowed if a.endswith('/*')):
            return False, detected, (
                f'File type "{detected}" is not allowed for {asset_type} uploads. '
                f'Expected one of: {", ".join(sorted(allowed)[:5])}'
            )

    # Extension vs MIME cross-check
    if detected and uploaded_file.name:
        ext = os.path.splitext(uploaded_file.name)[1].lower()
        if not _extension_matches_mime(ext, detected):
            return False, detected, (
                f'File extension "{ext}" does not match detected type "{detected}". '
                'Possible extension spoofing detected.'
            )

    return True, detected, ''


def _extension_matches_mime(ext, mime):
    """Check that a file extension is plausible for the given MIME type.

    Returns True if the extension is consistent, or if we can't determine.
    """
    EXTENSION_TO_MIME = {
        '.png': ['image/png'],
        '.jpg': ['image/jpeg'],
        '.jpeg': ['image/jpeg'],
        '.gif': ['image/gif'],
        '.webp': ['image/webp'],
        '.bmp': ['image/bmp'],
        '.tiff': ['image/tiff'],
        '.tif': ['image/tiff'],
        '.svg': ['image/svg+xml'],
        '.pdf': ['application/pdf'],
        '.doc': ['application/msword'],
        '.docx': ['application/vnd.openxmlformats-officedocument.wordprocessingml.document'],
        '.xls': ['application/vnd.ms-excel'],
        '.xlsx': ['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'],
        '.ppt': ['application/vnd.ms-powerpoint'],
        '.pptx': ['application/vnd.openxmlformats-officedocument.presentationml.presentation'],
        '.zip': ['application/zip'],
        '.rar': ['application/vnd.rar', 'application/x-rar-compressed'],
        '.7z': ['application/x-7z-compressed'],
        '.tar': ['application/x-tar'],
        '.gz': ['application/gzip'],
        '.txt': ['text/plain'],
        '.csv': ['text/csv'],
        '.ai': ['application/postscript', 'application/x-illustrator'],
        '.ps': ['application/postscript'],
    }

    expected_mimes = EXTENSION_TO_MIME.get(ext)
    if expected_mimes is None:
        # Unknown extension — we can't cross-check
        return True
    return mime in expected_mimes


# ---------------------------------------------------------------------------
# File size validation
# ---------------------------------------------------------------------------

def validate_file_size(uploaded_file, asset_type):
    """Validate file size against the per-type limit.

    Returns (is_valid, actual_size, limit, reason).
    """
    size = uploaded_file.size or 0
    limit = ASSET_SIZE_LIMITS.get(asset_type, GLOBAL_MAX_SIZE)

    if size > limit:
        limit_mb = limit / (1024 * 1024)
        size_mb = size / (1024 * 1024)
        return False, size, limit, (
            f'File ({size_mb:.1f}MB) exceeds the {limit_mb:.0f}MB limit for {asset_type} uploads.'
        )

    return True, size, limit, ''


# ---------------------------------------------------------------------------
# Filename sanitization
# ---------------------------------------------------------------------------

def sanitize_filename(name):
    """Sanitize a filename to remove special characters and normalize.

    - Normalizes unicode (NFKD)
    - Strips control characters
    - Replaces special characters with underscores
    - Collapses repeated dashes/underscores
    - Preserves the extension
    - Truncates to safe length
    """
    if not name:
        return 'unnamed'

    # Normalize unicode
    name = unicodedata.normalize('NFKD', name)

    # Encode to ASCII, replacing non-ASCII with _, then decode back
    name = name.encode('ascii', 'ignore').decode('ascii')

    # Split name and extension
    base, ext = os.path.splitext(name)
    ext = ext.lower()

    # Strip leading/trailing whitespace and dots
    base = base.strip().strip('.')

    # Replace special characters with underscores
    base = _SAFE_FILENAME_RE.sub('_', base)

    # Collapse repeated underscores/dashes
    base = _MULTI_DASH_RE.sub('_', base)

    # Trim to max length (preserving extension)
    max_base = _MAX_FILENAME_LEN - len(ext)
    if len(base) > max_base:
        base = base[:max_base].rstrip('_')

    if not base:
        base = 'unnamed'

    return f'{base}{ext}'


# ---------------------------------------------------------------------------
# ClamAV virus scanning
# ---------------------------------------------------------------------------

class ClamAVScanner:
    """Interface to ClamAV via clamd (TCP socket).

    Configuration (in settings.py):
        CLAMAV_HOST = '127.0.0.0.1'   # default
        CLAMAV_PORT = 3310             # default
        CLAMAV_TIMEOUT = 10            # seconds
        CLAMAV_ENABLED = True          # master switch
    """

    def __init__(self):
        self.host = getattr(settings, 'CLAMAV_HOST', '127.0.0.1')
        self.port = getattr(settings, 'CLAMAV_PORT', 3310)
        self.timeout = getattr(settings, 'CLAMAV_TIMEOUT', 10)
        self.enabled = getattr(settings, 'CLAMAV_ENABLED', False)

    def scan_file(self, uploaded_file):
        """Scan a file for viruses.

        Returns (is_clean, virus_name_or_none, error_or_none).
        If ClamAV is disabled, returns (True, None, None).
        """
        if not self.enabled:
            return True, None, None

        tmp_path = None
        try:
            # Write uploaded file to a temp location
            uploaded_file.seek(0)

            if isinstance(uploaded_file, TemporaryUploadedFile):
                tmp_path = uploaded_file.temporary_file_path()
            else:
                # InMemoryUploadedFile — write to temp
                fd, tmp_path = tempfile.mkstemp(suffix='.scan')
                try:
                    uploaded_file.seek(0)
                    chunk = uploaded_file.read(8192)
                    while chunk:
                        os.write(fd, chunk)
                        chunk = uploaded_file.read(8192)
                finally:
                    os.close(fd)
                uploaded_file.seek(0)

            # Send INSTREAM command to clamd
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            try:
                sock.connect((self.host, self.port))

                file_size = os.path.getsize(tmp_path)
                # clamd INSTREAM protocol: 'nINSTREAM' + data + zero chunk
                sock.sendall(b'nINSTREAM\r\n')

                with open(tmp_path, 'rb') as f:
                    while True:
                        chunk = f.read(65536)
                        if not chunk:
                            break
                        sock.sendall(chunk)

                # Signal end of stream (zero-length chunk)
                sock.sendall(b'\x00\x00\x00\x00')

                # Read response
                response = b''
                while True:
                    data = sock.recv(4096)
                    if not data:
                        break
                    response += data
                    if b'\r\n' in response:
                        break

                response_str = response.decode('utf-8', errors='replace').strip()

                if 'OK' in response_str:
                    return True, None, None
                elif 'FOUND' in response_str:
                    # Extract virus name
                    virus_name = response_str.replace(' FOUND', '').strip()
                    return False, virus_name, None
                else:
                    return True, None, f'Unexpected ClamAV response: {response_str}'

            finally:
                sock.close()

        except socket.timeout:
            return True, None, 'ClamAV scan timed out'
        except socket.error as exc:
            return True, None, f'ClamAV connection error: {exc}'
        except Exception as exc:
            logger.error('Virus scan failed: %s', exc)
            return True, None, f'Scan error: {exc}'
        finally:
            # Clean up temp file (but not the TemporaryUploadedFile's own file)
            if tmp_path and not isinstance(uploaded_file, TemporaryUploadedFile):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass


# Singleton
scanner = ClamAVScanner()


# ---------------------------------------------------------------------------
# Security audit log
# ---------------------------------------------------------------------------

SECURITY_LOG_PREFIX = '[SECURITY]'

def log_suspicious_upload(user, filename, reason, detected_mime='', request_meta=None):
    """Log a suspicious upload attempt with full context."""
    meta = request_meta or {}
    log_data = {
        'event': 'suspicious_upload',
        'user_id': getattr(user, 'pk', None),
        'username': getattr(user, 'username', 'anonymous'),
        'filename': filename,
        'reason': reason,
        'detected_mime': detected_mime,
        'ip': meta.get('HTTP_X_FORWARDED_FOR', meta.get('REMOTE_ADDR', 'unknown')),
        'user_agent': meta.get('HTTP_USER_AGENT', '')[:200],
    }
    logger.warning('%s Suspicious upload blocked: %s', SECURITY_LOG_PREFIX, log_data)

    # Also write to a dedicated security log file if configured
    try:
        security_logger = logging.getLogger('branding.security')
        security_logger.warning('BLOCKED | user=%s | file=%s | reason=%s | mime=%s | ip=%s',
            log_data['username'], log_data['filename'], log_data['reason'],
            log_data['detected_mime'], log_data['ip'])
    except Exception:
        pass


def log_virus_detected(user, filename, virus_name, request_meta=None):
    """Log a detected virus with full context."""
    meta = request_meta or {}
    log_data = {
        'event': 'virus_detected',
        'user_id': getattr(user, 'pk', None),
        'username': getattr(user, 'username', 'anonymous'),
        'filename': filename,
        'virus': virus_name,
        'ip': meta.get('HTTP_X_FORWARDED_FOR', meta.get('REMOTE_ADDR', 'unknown')),
        'user_agent': meta.get('HTTP_USER_AGENT', '')[:200],
    }
    logger.critical('%s Virus detected: %s', SECURITY_LOG_PREFIX, log_data)


def log_upload_success(user, filename, file_hash, detected_mime='', request_meta=None):
    """Log a successful upload for audit trail."""
    meta = request_meta or {}
    logger.info(
        '[UPLOAD] user=%s | file=%s | mime=%s | hash=%s | ip=%s',
        getattr(user, 'username', 'anonymous'),
        filename,
        detected_mime,
        file_hash[:16],
        meta.get('HTTP_X_FORWARDED_FOR', meta.get('REMOTE_ADDR', 'unknown')),
    )


# ---------------------------------------------------------------------------
# Hash helper
# ---------------------------------------------------------------------------

def compute_file_hash(uploaded_file):
    """Compute SHA-256 hash of the uploaded file content."""
    sha256 = hashlib.sha256()
    uploaded_file.seek(0)
    for chunk in iter(lambda: uploaded_file.read(8192), b''):
        sha256.update(chunk)
    uploaded_file.seek(0)
    return sha256.hexdigest()


# ---------------------------------------------------------------------------
# Combined validation entry point
# ---------------------------------------------------------------------------

def validate_upload(uploaded_file, asset_type, user):
    """Run all security checks on an uploaded file.

    Returns (is_valid, errors_list, metadata_dict).
    metadata_dict contains: detected_mime, file_hash, sanitized_name, file_size.
    """
    errors = []
    metadata = {
        'detected_mime': '',
        'file_hash': '',
        'sanitized_name': sanitize_filename(uploaded_file.name or 'unnamed'),
        'file_size': uploaded_file.size or 0,
    }

    # 1. MIME type validation
    is_valid, mime, reason = validate_mime_type(uploaded_file, asset_type)
    metadata['detected_mime'] = mime
    if not is_valid:
        errors.append(reason)
        log_suspicious_upload(
            user, uploaded_file.name, reason,
            detected_mime=mime,
        )

    # 2. File size validation
    is_valid_size, size, limit, reason = validate_file_size(uploaded_file, asset_type)
    metadata['file_size'] = size
    if not is_valid_size:
        errors.append(reason)
        log_suspicious_upload(
            user, uploaded_file.name, reason,
            detected_mime=mime,
        )

    # 3. Virus scan
    is_clean, virus_name, scan_error = scanner.scan_file(uploaded_file)
    if not is_clean:
        errors.append(f'Virus detected: {virus_name}. File cannot be uploaded.')
        log_virus_detected(user, uploaded_file.name, virus_name)
    elif scan_error:
        # Log the error but don't block (fail-open for availability)
        logger.warning('Virus scan error (non-blocking): %s', scan_error)

    # 4. Compute hash
    try:
        metadata['file_hash'] = compute_file_hash(uploaded_file)
    except Exception as exc:
        logger.error('Hash computation failed: %s', exc)
        metadata['file_hash'] = ''

    return len(errors) == 0, errors, metadata
