from .models import SiteSettings


def site_settings(request):
    """Expose the SiteSettings singleton to every template (base nav)."""
    return {"site_settings": SiteSettings.load()}
