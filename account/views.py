from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.utils.http import url_has_allowed_host_and_scheme

from .forms import UserRegistrationForm, UserLoginForm

User = get_user_model()


def _get_safe_next(request, default="landing"):
    """Get and validate 'next' redirect URL from GET or POST."""
    next_url = request.POST.get("next") or request.GET.get("next", default)
    if next_url == default or not next_url:
        return default
    if not next_url.startswith("/"):
        return default
    full_url = request.build_absolute_uri(next_url)
    if not url_has_allowed_host_and_scheme(full_url, request.get_host()):
        return default
    return next_url


def register_view(request):
    """Handle user registration."""
    if request.user.is_authenticated:
        return redirect("landing")

    if request.method == "POST":
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            name = (user.first_name or "").strip() or user.email.split("@")[0]
            messages.success(
                request,
                f"Welcome to Goaly, {name}! Your account has been created successfully.",
            )
            return redirect("landing")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = UserRegistrationForm()

    return render(request, "account/register.html", {"form": form})


def login_view(request):
    """Handle user login. User model uses email as USERNAME_FIELD."""
    if request.user.is_authenticated:
        return redirect("landing")

    if request.method == "POST":
        form = UserLoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]
            password = form.cleaned_data["password"]
            user = authenticate(request, username=email, password=password)

            if user is not None:
                login(request, user)
                name = (user.first_name or "").strip() or user.email.split("@")[0]
                messages.success(request, f"Welcome back, {name}!")
                next_url = _get_safe_next(request)
                return redirect(next_url)
            else:
                messages.error(request, "Invalid email or password.")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = UserLoginForm()

    return render(request, "account/login.html", {"form": form})


@login_required
def logout_view(request):
    """Handle user logout."""
    logout(request)
    messages.success(request, "You have been logged out successfully.")
    return redirect("landing")
