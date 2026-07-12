import json
from datetime import timedelta
from functools import wraps

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Max
from django.http import (
    HttpResponseForbidden,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import AssetEditForm, AssetForm, BoardForm, InviteForm, RegisterForm
from .models import Asset, Board, BoardAsset, Category, Invite, User
from .utils import fetch_og, make_thumbnail, parse_embed


def member_required(view):
    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.can_post:
            return HttpResponseForbidden("Members only.")
        return view(request, *args, **kwargs)

    return wrapper


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_admin_role:
            return HttpResponseForbidden("Admins only.")
        return view(request, *args, **kwargs)

    return wrapper


# ---------------------------------------------------------------- auth / invites


def join(request, token):
    invite = get_object_or_404(Invite, token=token)
    if not invite.is_valid:
        return render(request, "auth/invite_invalid.html", status=410)
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                invite.refresh_from_db()
                if not invite.is_valid:
                    return render(request, "auth/invite_invalid.html", status=410)
                user = form.save(commit=False)
                user.role = invite.role
                user.save()
                invite.use_count += 1
                invite.save(update_fields=["use_count"])
            login(request, user)
            messages.success(request, f"Welcome to Lumivision, {user.username}!")
            return redirect("dashboard")
    else:
        form = RegisterForm()
    return render(request, "auth/register.html", {"form": form, "invite": invite})


# ---------------------------------------------------------------------- boards


@login_required
def dashboard(request):
    boards = (
        Board.visible_to(request.user)
        .select_related("owner")
        .annotate(asset_count=Count("boardasset"))
    )
    return render(request, "core/dashboard.html", {"boards": boards})


@member_required
def board_create(request):
    if request.method == "POST":
        form = BoardForm(request.POST, request.FILES)
        if form.is_valid():
            board = form.save(commit=False)
            board.owner = request.user
            board.save()
            messages.success(request, f"Board “{board.name}” created.")
            return redirect(board)
    else:
        form = BoardForm()
    return render(
        request, "core/board_form.html", {"form": form, "board": None}
    )


@login_required
def board_edit(request, slug):
    board = get_object_or_404(Board, slug=slug)
    if not board.can_edit(request.user):
        return HttpResponseForbidden()
    if request.method == "POST":
        form = BoardForm(request.POST, request.FILES, instance=board)
        if form.is_valid():
            old_cover = Board.objects.get(pk=board.pk).cover_image
            updated = form.save()
            if old_cover and old_cover != updated.cover_image:
                old_cover.delete(save=False)
            messages.success(request, "Board updated.")
            return redirect(updated)
    else:
        form = BoardForm(instance=board)
    return render(
        request, "core/board_form.html", {"form": form, "board": board}
    )


@require_POST
@login_required
def board_delete(request, slug):
    board = get_object_or_404(Board, slug=slug)
    if not board.can_edit(request.user):
        return HttpResponseForbidden()
    name = board.name
    orphan_assets = list(
        Asset.objects.filter(boards=board)
        .annotate(nboards=Count("boards"))
        .filter(nboards=1)
    )
    board.delete()
    # Assets that lived only on this board and belong to the board owner
    # or the deleting user get cleaned up; others survive.
    for asset in orphan_assets:
        if asset.can_delete(request.user):
            asset.delete()
    messages.success(request, f"Board “{name}” deleted.")
    return redirect("dashboard")


def board_detail(request, slug):
    board = get_object_or_404(Board.objects.select_related("owner"), slug=slug)
    if not board.can_view(request.user):
        if not request.user.is_authenticated:
            return redirect(f"/accounts/login/?next={request.path}")
        return HttpResponseForbidden("This board is private.")

    entries = (
        BoardAsset.objects.filter(board=board)
        .select_related("asset", "asset__owner")
        .prefetch_related("asset__categories")
        .order_by("sort_order", "-added_at")
    )
    assets = []
    user = request.user
    for entry in entries:
        asset = entry.asset
        asset.user_can_delete = asset.can_delete(user)
        asset.user_can_remove = (
            asset.user_can_delete or board.can_edit(user)
        )
        asset.lb_json = json.dumps(_lightbox_payload(asset))
        assets.append(asset)

    categories = sorted(
        {c for a in assets for c in a.categories.all()}, key=lambda c: c.name
    )
    can_edit = user.is_authenticated and board.can_edit(user)
    can_post = user.is_authenticated and user.can_post
    return render(
        request,
        "core/board_detail.html",
        {
            "board": board,
            "assets": assets,
            "categories": categories,
            "can_edit_board": can_edit,
            "can_post": can_post,
            "asset_form": AssetForm(user=user, initial={"boards": [board.pk]})
            if can_post
            else None,
        },
    )


def _lightbox_payload(asset):
    """Data the lightbox needs to render this asset client-side."""
    if asset.kind == Asset.Kind.EMBED:
        src = asset.embed_src
    elif asset.kind == Asset.Kind.LINK:
        src = asset.link_image_url
    else:
        src = asset.file.url if asset.file else ""
    return {
        "kind": asset.kind,
        "title": asset.display_title,
        "desc": asset.description or asset.link_description,
        "src": src,
        "href": asset.link_url,
        "permalink": asset.get_absolute_url(),
    }


# ---------------------------------------------------------------------- assets


def _apply_asset_media(asset, form):
    """Populate kind-specific fields (thumbnails, embed/link metadata)."""
    kind = form.cleaned_data["kind"]
    if kind == Asset.Kind.IMAGE:
        asset.file = form.cleaned_data["file"]
        thumb = make_thumbnail(asset.file, name_hint="t")
        if thumb:
            asset.thumb = thumb
    elif kind == Asset.Kind.VIDEO:
        asset.file = form.cleaned_data["file"]
        custom = form.cleaned_data.get("custom_thumb")
        if custom:
            thumb = make_thumbnail(custom, name_hint="t")
            if thumb:
                asset.thumb = thumb
    elif kind == Asset.Kind.EMBED:
        asset.embed_url = form.cleaned_data["embed_url"]
        info = parse_embed(asset.embed_url)
        if info:
            asset.embed_provider = info["provider"]
            asset.embed_src = info["src"]
            asset.embed_thumb_url = info["thumb_url"]
    elif kind == Asset.Kind.LINK:
        asset.link_url = form.cleaned_data["link_url"]
        og = fetch_og(asset.link_url)
        asset.link_title = og["title"]
        asset.link_description = og["description"]
        asset.link_image_url = og["image"]
    asset.kind = kind


def _attach_to_boards(asset, boards):
    for board in boards:
        next_order = (
            BoardAsset.objects.filter(board=board).aggregate(m=Max("sort_order"))["m"]
            or 0
        ) + 1
        BoardAsset.objects.get_or_create(
            board=board, asset=asset, defaults={"sort_order": next_order}
        )
        board.save(update_fields=["updated_at"])


@require_POST
@member_required
def asset_create(request):
    form = AssetForm(request.POST, request.FILES, user=request.user)
    if not form.is_valid():
        return JsonResponse({"ok": False, "errors": form.errors}, status=400)
    kind = form.cleaned_data["kind"]
    if kind == Asset.Kind.EMBED and not parse_embed(form.cleaned_data["embed_url"]):
        return JsonResponse(
            {"ok": False, "errors": {"embed_url": ["Only YouTube and Vimeo URLs are supported."]}},
            status=400,
        )
    asset = Asset(owner=request.user, title=form.cleaned_data["title"],
                  description=form.cleaned_data["description"])
    _apply_asset_media(asset, form)
    asset.save()
    asset.categories.set(form.category_objects())
    _attach_to_boards(asset, form.cleaned_data["boards"])
    first = form.cleaned_data["boards"][0]
    return JsonResponse({"ok": True, "redirect": first.get_absolute_url()})


@require_POST
@member_required
def asset_quick_upload(request, slug):
    """Drag-and-drop upload target: files dropped straight onto a board."""
    board = get_object_or_404(Board, slug=slug)
    if not board.can_view(request.user):
        return HttpResponseForbidden()
    created = 0
    errors = []
    from .forms import IMAGE_EXTS, VIDEO_EXTS  # noqa: PLC0415

    for f in request.FILES.getlist("files")[:20]:
        ext = (f.name.rsplit(".", 1)[-1] if "." in f.name else "").lower()
        if ext in IMAGE_EXTS:
            kind = Asset.Kind.IMAGE
        elif ext in VIDEO_EXTS:
            kind = Asset.Kind.VIDEO
        else:
            errors.append(f"{f.name}: unsupported type")
            continue
        from django.conf import settings

        if f.size > settings.LUMIVISION_MAX_UPLOAD_BYTES:
            errors.append(f"{f.name}: too large")
            continue
        title = f.name.rsplit(".", 1)[0].replace("_", " ").replace("-", " ").strip()[:200]
        asset = Asset(owner=request.user, kind=kind, title=title, file=f)
        if kind == Asset.Kind.IMAGE:
            thumb = make_thumbnail(f, name_hint="t")
            if thumb:
                asset.thumb = thumb
        asset.save()
        _attach_to_boards(asset, [board])
        created += 1
    return JsonResponse({"ok": True, "created": created, "errors": errors})


def asset_detail(request, pk):
    asset = get_object_or_404(
        Asset.objects.select_related("owner").prefetch_related("categories"), pk=pk
    )
    if not asset.can_view(request.user):
        if not request.user.is_authenticated:
            return redirect(f"/accounts/login/?next={request.path}")
        return HttpResponseForbidden("You don't have access to this asset.")
    boards = Board.visible_to(request.user).filter(boardasset__asset=asset)
    return render(
        request,
        "core/asset_detail.html",
        {
            "asset": asset,
            "boards": boards,
            "user_can_delete": asset.can_delete(request.user),
        },
    )


@login_required
def asset_edit(request, pk):
    asset = get_object_or_404(Asset, pk=pk)
    if not asset.can_delete(request.user):
        return HttpResponseForbidden("You can only edit assets you posted.")
    if request.method == "POST":
        form = AssetEditForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            asset.title = form.cleaned_data["title"]
            asset.description = form.cleaned_data["description"]
            custom = form.cleaned_data.get("custom_thumb")
            if custom:
                thumb = make_thumbnail(custom, name_hint="t")
                if thumb:
                    if asset.thumb:
                        asset.thumb.delete(save=False)
                    asset.thumb = thumb
            asset.save()
            asset.categories.set(form.category_objects())
            # Sync board membership — but only for boards this user can see,
            # so an unrelated private board's placement is never touched.
            visible = set(
                Board.visible_to(request.user).values_list("pk", flat=True)
            )
            current = set(asset.boards.values_list("pk", flat=True))
            chosen = {b.pk for b in form.cleaned_data["boards"]}
            BoardAsset.objects.filter(
                asset=asset, board_id__in=(current & visible) - chosen
            ).delete()
            _attach_to_boards(
                asset,
                [b for b in form.cleaned_data["boards"] if b.pk not in current],
            )
            messages.success(request, "Asset updated.")
            next_url = request.POST.get("next", "")
            if next_url.startswith("/"):
                return redirect(next_url)
            return redirect(asset)
    else:
        form = AssetEditForm(
            user=request.user,
            initial={
                "title": asset.title,
                "description": asset.description,
                "categories": ", ".join(
                    asset.categories.values_list("name", flat=True)
                ),
                "boards": list(asset.boards.values_list("pk", flat=True)),
            },
        )
    return render(request, "core/asset_form.html", {"form": form, "asset": asset})


@require_POST
@login_required
def asset_delete(request, pk):
    asset = get_object_or_404(Asset, pk=pk)
    if not asset.can_delete(request.user):
        return HttpResponseForbidden("You can only delete assets you posted.")
    asset.delete()  # post_delete signal removes the files from disk
    if request.headers.get("x-requested-with") == "fetch":
        return JsonResponse({"ok": True})
    messages.success(request, "Asset deleted.")
    return redirect(request.POST.get("next") or "dashboard")


@require_POST
@login_required
def board_asset_remove(request, slug, pk):
    """Remove an asset from one board without deleting the asset."""
    board = get_object_or_404(Board, slug=slug)
    asset = get_object_or_404(Asset, pk=pk)
    if not (asset.can_delete(request.user) or board.can_edit(request.user)):
        return HttpResponseForbidden()
    BoardAsset.objects.filter(board=board, asset=asset).delete()
    if request.headers.get("x-requested-with") == "fetch":
        return JsonResponse({"ok": True})
    messages.success(request, "Removed from board.")
    return redirect(board)


@require_POST
@login_required
def board_reorder(request, slug):
    board = get_object_or_404(Board, slug=slug)
    if not board.can_edit(request.user):
        return HttpResponseForbidden()
    try:
        ids = json.loads(request.body).get("order", [])
        ids = [int(i) for i in ids]
    except (ValueError, AttributeError, json.JSONDecodeError):
        return JsonResponse({"ok": False}, status=400)
    entries = {ba.asset_id: ba for ba in BoardAsset.objects.filter(board=board)}
    for pos, asset_id in enumerate(ids, start=1):
        entry = entries.get(asset_id)
        if entry and entry.sort_order != pos:
            entry.sort_order = pos
            entry.save(update_fields=["sort_order"])
    return JsonResponse({"ok": True})


@require_POST
@member_required
def og_preview(request):
    """Live link-preview endpoint used by the “Link” tab of the add-asset modal."""
    try:
        url = json.loads(request.body).get("url", "")
    except json.JSONDecodeError:
        url = ""
    if not url:
        return JsonResponse({"ok": False}, status=400)
    return JsonResponse({"ok": True, **fetch_og(url)})


# ---------------------------------------------------------------------- manage


@admin_required
def manage_invites(request):
    if request.method == "POST":
        form = InviteForm(request.POST)
        if form.is_valid():
            invite = form.save(commit=False)
            invite.created_by = request.user
            days = form.cleaned_data.get("expires_days")
            if days:
                invite.expires_at = timezone.now() + timedelta(days=days)
            invite.save()
            messages.success(request, "Invite link created — copy it below.")
            return redirect("manage_invites")
    else:
        form = InviteForm()
    invites = list(Invite.objects.select_related("created_by"))
    for invite in invites:
        invite.full_url = request.build_absolute_uri(invite.get_absolute_url())
    return render(
        request, "core/manage_invites.html", {"form": form, "invites": invites}
    )


@require_POST
@admin_required
def invite_revoke(request, pk):
    invite = get_object_or_404(Invite, pk=pk)
    invite.revoked = True
    invite.save(update_fields=["revoked"])
    messages.success(request, "Invite revoked.")
    return redirect("manage_invites")


@admin_required
def manage_users(request):
    users = User.objects.order_by("username").annotate(
        n_assets=Count("assets", distinct=True),
        n_boards=Count("boards", distinct=True),
    )
    return render(
        request,
        "core/manage_users.html",
        {"users": users, "role_choices": User.Role.choices},
    )


@require_POST
@admin_required
def user_update(request, pk):
    user = get_object_or_404(User, pk=pk)
    if user.pk == request.user.pk:
        messages.error(request, "You can't modify your own account here.")
        return redirect("manage_users")
    action = request.POST.get("action")
    if action == "role":
        role = request.POST.get("role")
        if role in User.Role.values:
            user.role = role
            user.save(update_fields=["role"])
            messages.success(request, f"{user.username} is now a {user.get_role_display()}.")
    elif action == "toggle_active":
        user.is_active = not user.is_active
        user.save(update_fields=["is_active"])
        state = "re-activated" if user.is_active else "deactivated"
        messages.success(request, f"{user.username} {state}.")
    return redirect("manage_users")
