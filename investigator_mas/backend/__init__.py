# Re-export city registry from common so existing imports keep working.
from common import (  # noqa: F401
    get_city,
    get_city_or_none,
    list_cities,
    list_aliases,
    register_city,
    CityNotFoundError,
    CITY_ALIASES,
)
