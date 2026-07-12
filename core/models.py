import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from .themes import DEFAULT_THEME, THEME_CHOICES


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        MEMBER = "member", "Member"
        VIEWER = "viewer", "Viewer"

    role = models.CharField(max_length=10, choices=Role.choices, default=Role.MEMBER)
    theme = models.CharField(
        max_length=30,
        choices=THEME_CHOICES,
        default=DEFAULT_THEME,
        help_text="Look and feel of Lumivision for this user",
    )

    @property
    def is_admin_role(self):
        return self.role == self.Role.ADMIN or self.is_superuser

    @property
    def can_post(self):
        return self.is_admin_role or self.role == self.Role.MEMBER

    def __str__(self):
        return self.username


class Invite(models.Model):
    """A shareable registration link. Send /join/<token>/ to someone."""

    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    role = models.CharField(
        max_length=10,
        choices=[(User.Role.MEMBER, "Member"), (User.Role.VIEWER, "Viewer")],
        default=User.Role.MEMBER,
    )
    note = models.CharField(
        max_length=120, blank=True, help_text="Who/what this invite is for"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="invites"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    max_uses = models.PositiveIntegerField(default=1)
    use_count = models.PositiveIntegerField(default=0)
    revoked = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    @property
    def is_valid(self):
        if self.revoked:
            return False
        if self.expires_at and timezone.now() > self.expires_at:
            return False
        if self.max_uses and self.use_count >= self.max_uses:
            return False
        return True

    def get_absolute_url(self):
        return reverse("join", kwargs={"token": self.token})

    def __str__(self):
        return f"Invite {self.token} ({self.get_role_display()})"


class Board(models.Model):
    class Visibility(models.TextChoices):
        PRIVATE = "private", "Private"
        REGISTERED = "registered", "Registered Users"
        PUBLIC = "public", "Public"

    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True, editable=False)
    description = models.TextField(blank=True)
    banner_image = models.ImageField(
        upload_to="covers/%Y/%m/",
        blank=True,
        help_text="Backdrop shown behind the board name",
    )
    logo_image = models.ImageField(
        upload_to="logos/%Y/%m/",
        blank=True,
        help_text="Displayed in place of the board name, like a logo",
    )
    visibility = models.CharField(
        max_length=12, choices=Visibility.choices, default=Visibility.REGISTERED
    )
    theme = models.CharField(
        max_length=30,
        choices=[("", "Viewer's own theme")] + THEME_CHOICES,
        blank=True,
        default="",
        help_text="Forces a theme for everyone viewing this board",
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="boards"
    )
    collaborators = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="collab_boards",
        help_text="Registered users who may add content to this board",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    assets = models.ManyToManyField("Asset", through="BoardAsset", related_name="boards")

    class Meta:
        ordering = ["-updated_at"]

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name)[:120] or "board"
            slug = base
            n = 1
            while Board.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                n += 1
                slug = f"{base}-{n}"
            self.slug = slug
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("board_detail", kwargs={"slug": self.slug})

    def can_view(self, user):
        if self.visibility == self.Visibility.PUBLIC:
            return True
        if not user.is_authenticated:
            return False
        if self.visibility == self.Visibility.REGISTERED:
            return True
        return (
            self.owner_id == user.id
            or user.is_admin_role
            or self.collaborators.filter(pk=user.pk).exists()
        )

    def can_edit(self, user):
        return user.is_authenticated and (self.owner_id == user.id or user.is_admin_role)

    def can_contribute(self, user):
        """May this user add assets to the board?"""
        if not user.is_authenticated or not user.can_post:
            return False
        return (
            self.owner_id == user.id
            or user.is_admin_role
            or self.collaborators.filter(pk=user.pk).exists()
        )

    @staticmethod
    def visible_to(user):
        """Queryset of boards the given user (possibly anonymous) may view."""
        qs = Board.objects.all()
        if not user.is_authenticated:
            return qs.filter(visibility=Board.Visibility.PUBLIC)
        if user.is_admin_role:
            return qs
        return qs.filter(
            Q(visibility__in=[Board.Visibility.PUBLIC, Board.Visibility.REGISTERED])
            | Q(owner=user)
            | Q(collaborators=user)
        ).distinct()

    @staticmethod
    def contributable_by(user):
        """Queryset of boards this user may add assets to."""
        if not user.is_authenticated or not user.can_post:
            return Board.objects.none()
        if user.is_admin_role:
            return Board.objects.all()
        return Board.objects.filter(
            Q(owner=user) | Q(collaborators=user)
        ).distinct()

    def __str__(self):
        return self.name


class Category(models.Model):
    name = models.CharField(max_length=60, unique=True)
    slug = models.SlugField(max_length=80, unique=True, editable=False)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categories"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:80]
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Asset(models.Model):
    class Kind(models.TextChoices):
        IMAGE = "image", "Image"
        VIDEO = "video", "Video"
        EMBED = "embed", "Embedded Video"
        LINK = "link", "Link"

    kind = models.CharField(max_length=10, choices=Kind.choices)
    title = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)

    # Uploaded file (image or video)
    file = models.FileField(upload_to="assets/%Y/%m/", blank=True)
    # Generated (images) or user-supplied (videos) preview
    thumb = models.ImageField(upload_to="thumbs/%Y/%m/", blank=True)

    # Embedded video (YouTube / Vimeo)
    embed_url = models.URLField(blank=True)
    embed_provider = models.CharField(max_length=20, blank=True)
    embed_src = models.URLField(blank=True)  # iframe src
    embed_thumb_url = models.URLField(blank=True)

    # External link with Open Graph preview
    link_url = models.URLField(max_length=500, blank=True)
    link_title = models.CharField(max_length=300, blank=True)
    link_description = models.TextField(blank=True)
    link_image_url = models.URLField(max_length=500, blank=True)

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="assets"
    )
    categories = models.ManyToManyField(Category, blank=True, related_name="assets")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def get_absolute_url(self):
        return reverse("asset_detail", kwargs={"pk": self.pk})

    @property
    def display_title(self):
        return self.title or self.link_title or f"{self.get_kind_display()} #{self.pk}"

    @property
    def preview_url(self):
        """Best available image URL for the board card."""
        if self.thumb:
            return self.thumb.url
        if self.kind == self.Kind.IMAGE and self.file:
            return self.file.url
        if self.embed_thumb_url:
            return self.embed_thumb_url
        if self.link_image_url:
            return self.link_image_url
        return ""

    def can_view(self, user):
        if user.is_authenticated and (self.owner_id == user.id or user.is_admin_role):
            return True
        return Board.visible_to(user).filter(boardasset__asset=self).exists()

    def can_delete(self, user):
        return user.is_authenticated and (self.owner_id == user.id or user.is_admin_role)

    def __str__(self):
        return self.display_title


class BoardAsset(models.Model):
    board = models.ForeignKey(Board, on_delete=models.CASCADE)
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE)
    sort_order = models.PositiveIntegerField(default=0)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("board", "asset")]
        ordering = ["sort_order", "-added_at"]

    def __str__(self):
        return f"{self.asset} on {self.board}"
