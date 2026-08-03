"""Custom exception handler for the Branding API."""
from rest_framework.views import exception_handler


def custom_exception_handler(exc, context):
    """Extend DRF's default handler with a consistent error envelope."""
    response = exception_handler(exc, context)

    if response is not None:
        data = response.data
        # Wrap single errors in a list for consistency
        if isinstance(data, dict) and 'detail' in data and len(data) == 1:
            response.data = {
                'errors': [{'code': response.status_code, 'message': data['detail']}],
            }
        elif isinstance(data, dict):
            errors = []
            for field, messages in data.items():
                if isinstance(messages, list):
                    for msg in messages:
                        errors.append({'code': response.status_code, 'field': field, 'message': str(msg)})
                else:
                    errors.append({'code': response.status_code, 'field': field, 'message': str(messages)})
            response.data = {'errors': errors}

    return response
