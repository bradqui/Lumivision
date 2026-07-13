from django import forms
from django.conf import settings
from django.contrib.auth.forms import (
    PasswordChangeForm,
    SetPasswordForm,
    UserCreationForm,
)

from .models import Asset, Board, Category, Invite, User

IMAGE_EXTS = {"jpg", "jpeg", "png", "gif", "webp", "avif"}
VIDEO_EXTS = {"mp4", "webm", "mov", "m4v", "ogv"}


class GlassFormMixin:
    """Apply the Lumivision input styling to every field."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            css = widget.attrs.get("class", "")
            if isinstance(widget, (forms.CheckboxSelectMultiple, forms.RadioSelect)):
                continue  # rendered as custom pills, not text inputs
            if isinstance(widget, (forms.CheckboxInput,)):
                widget.attrs["class"] = f"{css} lv-check".strip()
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                widget.attrs["class"] = f"{css} lv-input lv-select".strip()
            else:
                widget.attrs["class"] = f"{css} lv-input".strip()


class RegisterForm(GlassFormMixin, UserCreationForm):
    email = forms.EmailField(required=False)

    class Meta:
        model = User
        fields = ("username", "email")


class LvClearableFileInput(forms.ClearableFileInput):
    """Styled replacement for Django's confusing filename + [x] Clear row."""

    template_name = "widgets/lv_clearable_file.html"


class GlassPasswordChangeForm(GlassFormMixin, PasswordChangeForm):
    pass


class GlassSetPasswordForm(GlassFormMixin, SetPasswordForm):
    pass


class BoardForm(GlassFormMixin, forms.ModelForm):
    class Meta:
        model = Board
        fields = (
            "name",
            "description",
            "banner_image",
            "logo_image",
            "visibility",
            "theme",
            "collaborators",
        )
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "collaborators": forms.CheckboxSelectMultiple,
            "banner_image": LvClearableFileInput,
            "logo_image": LvClearableFileInput,
        }

    def __init__(self, *args, owner=None, **kwargs):
        super().__init__(*args, **kwargs)
        qs = User.objects.filter(
            is_active=True, role__in=[User.Role.MEMBER, User.Role.ADMIN]
        ).order_by("username")
        if owner:
            qs = qs.exclude(pk=owner.pk)
        self.fields["collaborators"].queryset = qs


class InviteForm(GlassFormMixin, forms.ModelForm):
    expires_days = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=365,
        label="Expires after (days)",
        help_text="Leave blank for no expiry",
    )

    class Meta:
        model = Invite
        fields = ("role", "note", "max_uses")


class AssetForm(GlassFormMixin, forms.Form):
    """One form, four kinds — upload / embed / link resolved in clean()."""

    kind = forms.ChoiceField(choices=Asset.Kind.choices, widget=forms.HiddenInput)
    title = forms.CharField(max_length=200, required=False)
    description = forms.CharField(
        required=False, widget=forms.Textarea(attrs={"rows": 2})
    )
    file = forms.FileField(required=False)
    custom_thumb = forms.ImageField(
        required=False, label="Preview image (optional, for videos)"
    )
    embed_url = forms.URLField(required=False, assume_scheme="https")
    link_url = forms.URLField(required=False, assume_scheme="https")
    categories = forms.CharField(
        required=False,
        help_text="Comma-separated, e.g. Travel, Home, Fitness",
    )
    boards = forms.ModelMultipleChoiceField(
        queryset=Board.objects.none(),
        required=True,
        widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields["boards"].queryset = Board.contributable_by(user)

    def clean_file(self):
        f = self.cleaned_data.get("file")
        if not f:
            return f
        if f.size > settings.LUMIVISION_MAX_UPLOAD_BYTES:
            limit_mb = settings.LUMIVISION_MAX_UPLOAD_BYTES // (1024 * 1024)
            raise forms.ValidationError(f"File exceeds the {limit_mb} MB limit.")
        return f

    def clean(self):
        data = super().clean()
        kind = data.get("kind")
        f = data.get("file")
        if kind in (Asset.Kind.IMAGE, Asset.Kind.VIDEO):
            if not f:
                raise forms.ValidationError("Choose a file to upload.")
            ext = (f.name.rsplit(".", 1)[-1] if "." in f.name else "").lower()
            if ext in IMAGE_EXTS:
                data["kind"] = Asset.Kind.IMAGE
            elif ext in VIDEO_EXTS:
                data["kind"] = Asset.Kind.VIDEO
            else:
                raise forms.ValidationError(
                    "Unsupported file type. Images: jpg/png/gif/webp/avif. "
                    "Videos: mp4/webm/mov/m4v/ogv."
                )
        elif kind == Asset.Kind.EMBED and not data.get("embed_url"):
            raise forms.ValidationError("Paste a YouTube or Vimeo URL.")
        elif kind == Asset.Kind.LINK and not data.get("link_url"):
            raise forms.ValidationError("Paste a link URL.")
        return data

    def category_objects(self):
        return resolve_categories(self.cleaned_data.get("categories"))


def resolve_categories(raw):
    """Turn a comma-separated string into Category objects, creating as needed."""
    names = [n.strip() for n in (raw or "").split(",") if n.strip()]
    objs = []
    for name in names[:10]:
        obj = Category.objects.filter(name__iexact=name).first()
        if not obj:
            obj = Category.objects.create(name=name[:60])
        objs.append(obj)
    return objs


class AssetEditForm(GlassFormMixin, forms.Form):
    """Edit an asset's listing — title, description, categories, boards."""

    title = forms.CharField(max_length=200, required=False)
    description = forms.CharField(
        required=False, widget=forms.Textarea(attrs={"rows": 3})
    )
    categories = forms.CharField(
        required=False,
        help_text="Comma-separated, e.g. Travel, Home, Fitness",
    )
    boards = forms.ModelMultipleChoiceField(
        queryset=Board.objects.none(),
        required=True,
        widget=forms.CheckboxSelectMultiple,
    )
    custom_thumb = forms.ImageField(
        required=False, label="Replace preview image (optional)"
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["boards"].queryset = Board.contributable_by(user)

    def category_objects(self):
        return resolve_categories(self.cleaned_data.get("categories"))
