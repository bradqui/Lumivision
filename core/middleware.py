from django.conf import settings
from django.http import HttpResponse

# Allow some slack over the file cap for multipart boundaries + other fields.
_SLACK = 16 * 1024 * 1024


class MaxBodySizeMiddleware:
    """Reject oversized request bodies before Django parses them.

    The per-file limit in forms only runs after the whole body has been
    read to disk; this stops abusive uploads at the Content-Length header.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            length = int(request.META.get("CONTENT_LENGTH") or 0)
        except (TypeError, ValueError):
            length = 0
        if length > settings.LUMIVISION_MAX_UPLOAD_BYTES + _SLACK:
            return HttpResponse("Request body too large.", status=413)
        return self.get_response(request)
