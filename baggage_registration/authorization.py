from rest_framework import permissions
from django.contrib.auth.models import User
from .redis import session_storage
from rest_framework import authentication
from rest_framework import exceptions


class AuthBySessionID(authentication.BaseAuthentication):
    def authenticate(self, request):
        session_id = request.COOKIES.get("session_id")
        print(f"Session ID: {session_id}")
        if session_id is None:
            raise exceptions.AuthenticationFailed("Нет сессии")
        try:
            username = session_storage.get(session_id).decode("utf-8")
        except Exception as e:
            raise exceptions.AuthenticationFailed("Сессия с таким ID не найдена в хранилище сессий")
        user = User.objects.get(username=username)
        if user is None:
            raise exceptions.AuthenticationFailed("Нет пользователя с именем, соответствующим сессии, в БД")
        return user, None


class AuthBySessionIDIfExists(authentication.BaseAuthentication):
    def authenticate(self, request):
        session_id = request.COOKIES.get("session_id")

        if session_id is None:
            return None, None

        try:
            username = session_storage.get(session_id).decode("utf-8")

            user = User.objects.get(username=username)
            return user, None
        except (User.DoesNotExist, AttributeError, TypeError) as e:
            return None, None


class IsAuth(permissions.BasePermission):
    def has_permission(self, request, view):
        session_id = request.COOKIES.get("session_id")
        if session_id is None:
            return False
        try:
            session_storage.get(session_id).decode("utf-8")
        except Exception as e:
            return False
        return True


class IsManagerAuth(permissions.BasePermission):
    def has_permission(self, request, view):
        session_id = request.COOKIES.get("session_id")
        print(f"🔍 Session ID from request: {session_id}")  # Логируем session_id

        if session_id is None:
            return False

        try:
            username = session_storage.get(session_id).decode("utf-8")
            print(f"🔍 Username from session storage: {username}")  # Логируем имя пользователя
        except Exception as e:
            print(f"❌ Session error: {e}")
            return False

        user = User.objects.filter(username=username).first()
        print(f"🔍 Found user: {user} (ID: {user.id if user else 'N/A'})")  # Логируем пользователя

        if user is None:
            return False

        has_access = user.is_superuser or user.is_staff
        print(f"🔍 User is_superuser: {user.is_superuser}, is_staff: {user.is_staff}, Access: {has_access}")  # Логируем права

        return has_access
