from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, TemplateView, UpdateView

from .forms import TranscriptionForm
from .groq import LANGUAGES
from .models import Transcription


class LiveView(TemplateView):
    template_name = "transcriber/live.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["languages"] = [(key, value["label"]) for key, value in LANGUAGES.items()]
        return context


class TranscriptionListView(ListView):
    model = Transcription
    template_name = "transcriber/list.html"
    context_object_name = "transcriptions"
    paginate_by = 20


class TranscriptionCreateView(CreateView):
    model = Transcription
    form_class = TranscriptionForm
    template_name = "transcriber/form.html"
    success_url = reverse_lazy("transcriber:list")


class TranscriptionUpdateView(UpdateView):
    model = Transcription
    form_class = TranscriptionForm
    template_name = "transcriber/form.html"
    success_url = reverse_lazy("transcriber:list")


class TranscriptionDeleteView(DeleteView):
    model = Transcription
    template_name = "transcriber/confirm_delete.html"
    success_url = reverse_lazy("transcriber:list")
