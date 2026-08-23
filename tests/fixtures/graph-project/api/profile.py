PROFILE_FIELD = "profile.displayName"
PROFILE_CHANGED_EVENT = "profile.changed"


def serialize_profile(display_name):
    return {PROFILE_FIELD: display_name, "event": PROFILE_CHANGED_EVENT}
