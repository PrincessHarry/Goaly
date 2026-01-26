from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm

User = get_user_model()


class UserRegistrationForm(UserCreationForm):
    """Custom registration form. Uses email as identifier (no username)."""
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            "class": "w-full bg-slate-50 border border-slate-200 rounded-2xl py-3 px-4 focus:outline-none focus:ring-2 focus:ring-sage-500/20 focus:border-sage-500 transition-all",
            "placeholder": "you@example.com",
        }),
    )
    first_name = forms.CharField(
        max_length=150,
        required=True,
        widget=forms.TextInput(attrs={
            "class": "w-full bg-slate-50 border border-slate-200 rounded-2xl py-3 px-4 focus:outline-none focus:ring-2 focus:ring-sage-500/20 focus:border-sage-500 transition-all",
            "placeholder": "John Doe",
        }),
    )
    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={
            "class": "w-full bg-slate-50 border border-slate-200 rounded-2xl py-3 px-4 focus:outline-none focus:ring-2 focus:ring-sage-500/20 focus:border-sage-500 transition-all",
            "placeholder": "••••••••",
        }),
    )
    password2 = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput(attrs={
            "class": "w-full bg-slate-50 border border-slate-200 rounded-2xl py-3 px-4 focus:outline-none focus:ring-2 focus:ring-sage-500/20 focus:border-sage-500 transition-all",
            "placeholder": "••••••••",
        }),
    )

    class Meta:
        model = User
        fields = ("first_name", "email", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].help_text = None
        self.fields["password2"].help_text = None

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if email and User.objects.filter(email=email).exists():
            raise forms.ValidationError("A user with this email already exists.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = user.email
        if commit:
            user.save()
        return user


class UserLoginForm(forms.Form):
    """Login form. Email + password."""
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            "class": "w-full bg-slate-50 border border-slate-200 rounded-2xl py-3 px-4 focus:outline-none focus:ring-2 focus:ring-sage-500/20 focus:border-sage-500 transition-all",
            "placeholder": "you@example.com",
        }),
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            "class": "w-full bg-slate-50 border border-slate-200 rounded-2xl py-3 px-4 focus:outline-none focus:ring-2 focus:ring-sage-500/20 focus:border-sage-500 transition-all",
            "placeholder": "••••••••",
        }),
    )
