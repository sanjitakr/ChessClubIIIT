from django.conf import settings
from django.shortcuts import render, redirect
from django.utils.timezone import now
import json
from accounts.models import User
from tournaments.models import Tournament
from newsletters.models import Newsletter


from dotenv import load_dotenv
env_path = settings.BASE_DIR / ".env"
if env_path.exists():
    load_dotenv(env_path)


def home(request):
    from django.db.models import Avg
    from accounts.models import UserProfile

    next_tournament = (
        Tournament.objects
        .filter(start_date__gte=now().date())
        .order_by('start_date')
        .first()
    )
    # fallback: show the most recent active tournament if no future ones exist
    if not next_tournament:
        next_tournament = Tournament.objects.filter(is_active=True).order_by('-start_date').first()

    latest_newsletter = (
        Newsletter.objects
        .order_by('-published_date')
        .first()
    )
    top_users = User.objects.select_related("profile").order_by("-profile__rating")[:5]
    active_count = User.objects.count()
    avg_rating_val = UserProfile.objects.aggregate(avg=Avg('rating'))['avg']
    avg_rating = int(avg_rating_val) if avg_rating_val else 0

    return render(request, 'home.html', {
        "top_users": top_users,
        "next_tournament": next_tournament,
        "latest_newsletter": latest_newsletter,
        "active_count": active_count,
        "avg_rating": avg_rating,
    })

def login(request):
    if request.user.is_authenticated:
        return redirect('/')
    return render(request, 'login.html')

def match(request):
    return render(request, 'match.html')