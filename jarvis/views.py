from django.shortcuts import render

from .models import Location


def home(request):
    """Home page showing a gallery of location screenshots."""
    locations = Location.objects.exclude(screenshot='').exclude(screenshot__isnull=True)
    return render(request, 'jarvis/home.html', {'locations': locations})
