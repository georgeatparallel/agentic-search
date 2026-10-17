"""Select the configured async search backend."""

import config


def get_search_fn():
    """Return a provider without importing optional backends until selected."""
    provider = config.SEARCH_PROVIDER.lower()
    if provider == "parallel":
        from search.parallel import search
    elif provider == "duckduckgo":
        from search.fallback import search
    else:
        from search.brave import search
    return search
