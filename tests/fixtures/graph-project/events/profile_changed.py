PROFILE_CHANGED = "profile.changed"
CACHE_REFRESH = "profile/cache/refresh"


def publish_profile_changed():
    return {"event": PROFILE_CHANGED, "target": CACHE_REFRESH}
