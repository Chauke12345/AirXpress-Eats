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
