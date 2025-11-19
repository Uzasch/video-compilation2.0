from supabase import create_client, Client
from api.config import get_settings
from functools import lru_cache

@lru_cache()
def get_supabase_client() -> Client:
    """Get Supabase client (cached)"""
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_key)
