from django.conf import settings
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from buffalo.forms import StyledPasswordResetForm, StyledSetPasswordForm, TribeAuthenticationForm

urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(authentication_form=TribeAuthenticationForm),
        name="login",
    ),
    path(
        "accounts/password_reset/",
        auth_views.PasswordResetView.as_view(
            form_class=StyledPasswordResetForm,
            email_template_name="registration/password_reset_email.txt",
            extra_email_context={"support_email": settings.SUPPORT_EMAIL},
        ),
        name="password_reset",
    ),
    path(
        "accounts/reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(form_class=StyledSetPasswordForm),
        name="password_reset_confirm",
    ),
    path("accounts/", include("django.contrib.auth.urls")),
    path("", include("buffalo.urls")),
]
