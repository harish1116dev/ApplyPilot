"""Plugin registry — routes platform name to the correct plugin module."""
from modules.plugins import (
    email_plugin,
    google_form_plugin,
    linkedin_plugin,
    lever_plugin,
    greenhouse_plugin,
    workday_plugin,
    generic_plugin,
)

_REGISTRY = {
    "email": email_plugin,
    "google_form": google_form_plugin,
    "linkedin": linkedin_plugin,
    "lever": lever_plugin,
    "greenhouse": greenhouse_plugin,
    "workday": workday_plugin,
    "naukri": generic_plugin,
    "indeed": generic_plugin,
    "wellfound": generic_plugin,
    "careers_page": generic_plugin,
    "generic": generic_plugin,
}


def get_plugin(platform: str):
    """Return the plugin module for the given platform string."""
    return _REGISTRY.get(platform, generic_plugin)
