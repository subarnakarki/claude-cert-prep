from django import forms

from .models import Domain
from .practice import MODES


class PracticeSetupForm(forms.Form):
    domain = forms.ChoiceField(required=False, label="Domain")
    mode = forms.ChoiceField(
        choices=list(MODES.items()), initial="all", widget=forms.RadioSelect, label="Questions"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["domain"].choices = [("", "All domains")] + [
            (d.slug, f"{d.slug} · {d.name}") for d in Domain.objects.all()
        ]

    def clean_domain(self) -> Domain | None:
        slug = self.cleaned_data["domain"]
        return Domain.objects.get(slug=slug) if slug else None
