from django.shortcuts import render, redirect


def landing(request):
    """Landing page for Goaly - goal setting and rewards."""
    if request.method == "POST" and request.POST.get("email"):
        # Pre-launch: accept email (no persistence yet). Redirect back with success.
        from django.contrib import messages

        messages.success(
            request,
            "Thanks for signing up! We'll notify you when Goaly launches.",
        )
        return redirect("landing")
    return render(request, "goals/landing.html")
