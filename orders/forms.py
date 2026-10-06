from django import forms

from .models import Order


# =========================================================
# CUSTOMER ONLINE ORDER FORM
# =========================================================

class CustomerOrderForm(forms.ModelForm):

    class Meta:
        model = Order

        fields = [
            "customer_name",
            "whatsapp_number",
            "delivery_address",
            "notes",
        ]

        widgets = {

            "customer_name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Your name",
                }
            ),

            "whatsapp_number": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "WhatsApp or contact number",
                }
            ),
"notes": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Any special instructions?",
                }
            ),
        }

    def __init__(self, *args, **kwargs):

        kwargs.pop("shop", None)

        super().__init__(
            *args,
            **kwargs
        )

        self.fields[
            "whatsapp_number"
        ].required = True

# =========================================================
# CUSTOMER REGISTRATION FORM
# =========================================================

from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import CustomerProfile


class CustomerRegistrationForm(UserCreationForm):

    full_name = forms.CharField(
        max_length=150,
        required=True,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Your full name",
            }
        ),
    )

    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "placeholder": "Your email address",
            }
        ),
    )

    whatsapp_number = forms.CharField(
        max_length=20,
        required=True,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "WhatsApp or contact number",
            }
        ),
    )

    class Meta:
        model = User
        fields = [
            "username",
            "email",
            "password1",
            "password2",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["username"].widget.attrs.update({
            "class": "form-control",
            "placeholder": "Choose a username",
        })

        self.fields["password1"].widget.attrs.update({
            "class": "form-control",
            "placeholder": "Create a password",
        })

        self.fields["password2"].widget.attrs.update({
            "class": "form-control",
            "placeholder": "Confirm your password",
        })

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()

        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                "An account with this email address already exists."
            )

        return email

    def save(self, commit=True):
        user = super().save(commit=False)

        user.first_name = self.cleaned_data["full_name"]
        user.email = self.cleaned_data["email"]

        if commit:
            user.save()

            CustomerProfile.objects.create(
                user=user,
                whatsapp_number=self.cleaned_data["whatsapp_number"],
            )

        return user
