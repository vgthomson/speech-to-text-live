from django import forms

from .models import Transcription


class TranscriptionForm(forms.ModelForm):
    class Meta:
        model = Transcription
        fields = ["text"]
        widgets = {"text": forms.Textarea(attrs={"rows": 8})}

    def clean_text(self):
        text = self.cleaned_data["text"].strip()
        if not text:
            raise forms.ValidationError("Text cannot be empty.")
        return text
