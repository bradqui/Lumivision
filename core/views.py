import json
from datetime import timedelta
from functools import wraps

from django.contrib import messages
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.db import connection, transaction
from django.db.models import Count, F, Max
from django.http import (
    HttpResponseForbidden,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import (
    AssetEditForm,
    AssetForm,
    BoardForm,
    GlassPasswordChangeForm,
    GlassSetPasswordForm,
    InviteForm,
    RegisterForm,
)
from .models import Asset, Board, BoardAsset, Category, Invite, SiteSettings, User
from .themes import THEMES, THEME_KEYS
from .utils import (
    extract_video_poster,
    fetch_og,
    make_avatar,
    make_thumbnail,
    parse_embed,
)


def healthz(request):
    """Unauthenticated container health probe: verifies the DB responds."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        return JsonResponse({"status": "error"}, status=500)
    return JsonResponse({"status": "ok"})


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
                Invite.objects.filter(pk=invite.pk).update(
                    use_count=F("use_count") + 1
                )
            login(
                request, user, backend="django.contrib.auth.backends.ModelBackend"
            )
            messages.success(request, f"Welcome to Lumivision, {user.username}!")
            return redirect("dashboard")
    else:
        form = RegisterForm()
    return render(request, "auth/register.html", {"form": form, "invite": invite})


# --------------------------------------------------------------------- account


@login_required
def account(request):
    if request.method == "POST":
        action = request.POST.get("action", "theme")
        user = request.user
        if action == "avatar":
            uploaded = request.FILES.get("avatar")
            if not uploaded:
                messages.error(request, "Choose an image first.")
            elif uploaded.size > 15 * 1024 * 1024:
                messages.error(request, "Avatar image must be under 15 MB.")
            else:
                avatar = make_avatar(uploaded)
                if avatar:
                    if user.avatar:
                        user.avatar.delete(save=False)
                    user.avatar = avatar
                    user.save(update_fields=["avatar"])
                    messages.success(request, "Profile picture updated.")
                else:
                    messages.error(request, "Could not read that image file.")
        elif action == "remove_avatar":
            if user.avatar:
                user.avatar.delete(save=False)
                user.avatar = ""
                user.save(update_fields=["avatar"])
                messages.success(request, "Profile picture removed.")
        else:
            theme = request.POST.get("theme", "")
            if theme in THEME_KEYS:
                user.theme = theme
                user.save(update_fields=["theme"])
                messages.success(request, "Theme updated.")
        return redirect("account")
    return render(request, "core/account.html", {"themes": THEMES})


@login_required
def password_change(request):
    form = GlassPasswordChangeForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        update_session_auth_hash(request, request.user)  # stay signed in
        messages.success(request, "Your password has been changed.")
        return redirect("account")
    return render(request, "core/password_change.html", {"form": form})


@admin_required
def user_set_password(request, pk):
    target = get_object_or_404(User, pk=pk)
    form = GlassSetPasswordForm(target, request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Password for {target.username} has been set.")
        return redirect("manage_users")
    return render(
        request, "core/user_set_password.html", {"form": form, "target": target}
    )


# ---------------------------------------------------------------------- boards


def dashboard(request):
    # Guests may browse the board list only when the admin has switched the
    # site public; they then see public boards alone (via Board.visible_to)
    # and no create/edit affordances.
    if not request.user.is_authenticated and not SiteSettings.load().public_site:
        return redirect(f"/accounts/login/?next={request.path}")
    boards = list(
        Board.visible_to(request.user)
        .select_related("owner")
        .annotate(asset_count=Count("boardasset", distinct=True))
    )
    # Boards that opted in get up to four asset previews for their card
    # collage (skipped when a banner image would cover it anyway).
    wanting = [b.pk for b in boards if b.show_asset_preview and not b.banner_image]
    previews = {}
    if wanting:
        for entry in (
            BoardAsset.objects.filter(board_id__in=wanting)
            .select_related("asset")
            .order_by("board_id", "sort_order", "-added_at")
        ):
            urls = previews.setdefault(entry.board_id, [])
            if len(urls) < 4:
                url = entry.asset.preview_url
                if url:
                    urls.append(url)
    for b in boards:
        b.preview_urls = previews.get(b.pk, [])
    return render(request, "core/dashboard.html", {"boards": boards})


@member_required
def board_create(request):
    if request.method == "POST":
        form = BoardForm(request.POST, request.FILES, owner=request.user)
        if form.is_valid():
            board = form.save(commit=False)
            board.owner = request.user
            board.save()
            form.save_m2m()
            messages.success(request, f"Board “{board.name}” created.")
            return redirect(board)
    else:
        form = BoardForm(owner=request.user)
    return render(
        request, "core/board_form.html", {"form": form, "board": None}
    )


@login_required
def board_edit(request, slug):
    board = get_object_or_404(Board, slug=slug)
    if not board.can_edit(request.user):
        return HttpResponseForbidden()
    if request.method == "POST":
        form = BoardForm(request.POST, request.FILES, instance=board, owner=board.owner)
        if form.is_valid():
            old = Board.objects.get(pk=board.pk)
            old_banner, old_logo = old.banner_image, old.logo_image
            updated = form.save()
            if old_banner and old_banner != updated.banner_image:
                old_banner.delete(save=False)
            if old_logo and old_logo != updated.logo_image:
                old_logo.delete(save=False)
            messages.success(request, "Board updated.")
            return redirect(updated)
    else:
        form = BoardForm(instance=board, owner=board.owner)
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
        asset.lb_json = json.dumps(_lightbox_payload(asset, board))
        assets.append(asset)

    categories = sorted(
        {c for a in assets for c in a.categories.all()}, key=lambda c: c.name
    )
    can_edit = user.is_authenticated and board.can_edit(user)
    can_post = board.can_contribute(user)
    collaborator_names = list(
        board.collaborators.values_list("username", flat=True)
    )
    return render(
        request,
        "core/board_detail.html",
        {
            "board": board,
            "assets": assets,
            "categories": categories,
            "can_edit_board": can_edit,
            "can_post": can_post,
            "collaborator_names": collaborator_names,
            "asset_form": AssetForm(user=user, initial={"boards": [board.pk]})
            if can_post
            else None,
        },
    )


def _lightbox_payload(asset, board=None):
    """Data the lightbox needs to render this asset client-side.

    Expects asset.user_can_delete / user_can_remove to be set by the
    caller (board_detail does) so the lightbox can offer manage actions.
    """
    if asset.kind == Asset.Kind.EMBED:
        src = asset.embed_src
    elif asset.kind == Asset.Kind.LINK:
        # A user-replaced preview beats the fetched Open Graph image.
        src = asset.thumb.url if asset.thumb else asset.link_image_url
    else:
        src = asset.file.url if asset.file else ""
    owner = asset.owner
    return {
        "kind": asset.kind,
        "id": asset.pk,
        "title": asset.display_title,
        "desc": asset.description or asset.link_description,
        "src": src,
        "href": asset.link_url,
        "permalink": asset.get_absolute_url(),
        "owner": owner.username,
        "avatar": owner.avatar.url if owner.avatar else "",
        "can_delete": bool(getattr(asset, "user_can_delete", False)),
        "can_remove": bool(getattr(asset, "user_can_remove", False)),
        "edit_url": reverse("asset_edit", args=[asset.pk]),
        "delete_url": reverse("asset_delete", args=[asset.pk]),
        "remove_url": (
            reverse("board_asset_remove", args=[board.slug, asset.pk])
            if board
            else ""
        ),
        "board": board.name if board else "",
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
    if asset.kind == Asset.Kind.VIDEO and not asset.thumb:
        poster = extract_video_poster(asset.file.path)
        if poster:
            asset.thumb = poster
            asset.save(update_fields=["thumb"])
    asset.categories.set(form.category_objects())
    _attach_to_boards(asset, form.cleaned_data["boards"])
    first = form.cleaned_data["boards"][0]
    return JsonResponse({"ok": True, "redirect": first.get_absolute_url()})


@require_POST
@member_required
def asset_quick_upload(request, slug):
    """Drag-and-drop upload target: files dropped straight onto a board."""
    board = get_object_or_404(Board, slug=slug)
    if not board.can_contribute(request.user):
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
        if kind == Asset.Kind.VIDEO:
            poster = extract_video_poster(asset.file.path)
            if poster:
                asset.thumb = poster
                asset.save(update_fields=["thumb"])
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
    boards = list(Board.visible_to(request.user).filter(boardasset__asset=asset))
    can_delete = asset.can_delete(request.user)
    for b in boards:
        b.user_can_remove = can_delete or b.can_edit(request.user)
    return render(
        request,
        "core/asset_detail.html",
        {
            "asset": asset,
            "boards": boards,
            "user_can_delete": can_delete,
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
            # Images keep their auto-generated thumbnail; only videos and
            # links (whose previews come from posters / OG images) can have
            # theirs replaced.
            custom = form.cleaned_data.get("custom_thumb")
            if custom and asset.kind in (Asset.Kind.VIDEO, Asset.Kind.LINK):
                thumb = make_thumbnail(custom, name_hint="t")
                if thumb:
                    if asset.thumb:
                        asset.thumb.delete(save=False)
                    asset.thumb = thumb
            asset.save()
            asset.categories.set(form.category_objects())
            # Sync board membership — but only among boards this user can
            # contribute to, so other placements are never touched.
            contributable = set(
                Board.contributable_by(request.user).values_list("pk", flat=True)
            )
            current = set(asset.boards.values_list("pk", flat=True))
            chosen = {b.pk for b in form.cleaned_data["boards"]}
            BoardAsset.objects.filter(
                asset=asset, board_id__in=(current & contributable) - chosen
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
    # Categories already in use on this asset's boards, offered as one-tap
    # suggestions next to the free-text input.
    suggest_categories = (
        Category.objects.filter(assets__boards__in=asset.boards.all())
        .distinct()
        .order_by("name")
    )
    return render(
        request,
        "core/asset_form.html",
        {"form": form, "asset": asset, "suggest_categories": suggest_categories},
    )


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
    next_url = request.POST.get("next", "")
    # Don't bounce back to the asset page if this removal just cost the
    # remover their view access to it (editor removing from the only
    # shared board).
    if next_url.startswith("/") and (
        next_url != asset.get_absolute_url() or asset.can_view(request.user)
    ):
        return redirect(next_url)
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
def manage_settings(request):
    site = SiteSettings.load()
    if request.method == "POST":
        site.public_site = request.POST.get("public_site") == "1"
        site.save(update_fields=["public_site"])
        messages.success(request, "Site settings saved.")
        return redirect("manage_settings")
    return render(request, "core/manage_settings.html", {"site": site})


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
            # Lumivision admins are fully trusted: grant Django-admin access
            # including model permissions (superuser); revoke on demotion.
            is_admin = role == User.Role.ADMIN
            user.is_staff = is_admin
            user.is_superuser = is_admin
            user.save(update_fields=["role", "is_staff", "is_superuser"])
            messages.success(request, f"{user.username} is now a {user.get_role_display()}.")
    elif action == "toggle_active":
        user.is_active = not user.is_active
        user.save(update_fields=["is_active"])
        state = "re-activated" if user.is_active else "deactivated"
        messages.success(request, f"{user.username} {state}.")
    return redirect("manage_users")
