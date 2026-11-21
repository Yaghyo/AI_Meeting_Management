from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailBackend(ModelBackend):
    """Authenticate accounts by their unique email while keeping usernames for display."""

    def authenticate(self, request, username=None, password=None, email=None, **kwargs):
        address = (email or username or '').strip()
        if not address or password is None:
            return None
        user_model = get_user_model()
        try:
            user = user_model.objects.get(email__iexact=address)
        except user_model.DoesNotExist:
            user_model().set_password(password)
            return None
        return user if user.check_password(password) and self.user_can_authenticate(user) else None
