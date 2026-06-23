from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.views.decorators.http import require_POST
from django.utils.timezone import now
from django.utils.dateparse import parse_date
from .models import Newsletter


def _is_newsletter_admin(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser)


def newsletter_list(request):
    if request.method == "POST" and request.user.is_staff:
        title = request.POST.get("title", "").strip()
        if title:
            Newsletter.objects.create(
                title=title,
                excerpt=request.POST.get("excerpt", ""),
                content=request.POST.get("content", ""),
                author=request.user.display_name,
            )
            messages.success(request, f'Newsletter "{title}" published.')
        else:
            messages.error(request, "Newsletter title is required.")
        return redirect("newsletters")

    newsletters = Newsletter.objects.all()
    return render(request, 'newsletters.html', {
        "newsletters": newsletters
    })


@user_passes_test(_is_newsletter_admin)
def newsletter_admin(request):
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "create":
            title = request.POST.get("title", "").strip()
            if title:
                pub_date = parse_date(request.POST.get("published_date") or "") or now().date()
                Newsletter.objects.create(
                    title=title,
                    excerpt=request.POST.get("excerpt", ""),
                    content=request.POST.get("content", ""),
                    author=request.POST.get("author") or request.user.display_name,
                    published_date=pub_date,
                )
                messages.success(request, f'Newsletter "{title}" published.')
            else:
                messages.error(request, "Title is required.")
        elif action == "delete":
            nl = get_object_or_404(Newsletter, id=request.POST.get("newsletter_id"))
            title = nl.title
            nl.delete()
            messages.success(request, f'"{title}" deleted.')
        elif action == "update":
            nl = get_object_or_404(Newsletter, id=request.POST.get("newsletter_id"))
            nl.title = request.POST.get("title", nl.title).strip() or nl.title
            nl.excerpt = request.POST.get("excerpt", nl.excerpt)
            nl.content = request.POST.get("content", nl.content)
            nl.author = request.POST.get("author", nl.author)
            pub = parse_date(request.POST.get("published_date") or "")
            if pub:
                nl.published_date = pub
            nl.save()
            messages.success(request, f'"{nl.title}" updated.')
        return redirect("newsletter_admin")

    return render(request, 'newsletter-admin.html', {
        "newsletters": Newsletter.objects.all(),
    })


def newsletter_article(request, slug):
    newsletter = get_object_or_404(Newsletter, slug=slug)
    return render(request, 'newsletter-article.html', {
        "newsletter": newsletter
    })
