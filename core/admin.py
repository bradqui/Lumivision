from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Asset, Board, BoardAsset, Category, Invite, SiteSettings, User


@admin.register(User)
class LumiUserAdmin(UserAdmin):
    list_display = ("username", "email", "role", "is_active", "date_joined")
    list_filter = ("role", "is_active")
    fieldsets = UserAdmin.fieldsets + (("Lumivision", {"fields": ("role",)}),)


@admin.register(Invite)
class InviteAdmin(admin.ModelAdmin):
    list_display = (
        "token",
        "role",
        "note",
        "created_by",
        "use_count",
        "max_uses",
        "expires_at",
        "revoked",
    )
    list_filter = ("role", "revoked")
    readonly_fields = ("token", "use_count")


class BoardAssetInline(admin.TabularInline):
    model = BoardAsset
    extra = 0


@admin.register(Board)
class BoardAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "visibility", "owner", "updated_at")
    list_filter = ("visibility",)
    search_fields = ("name", "slug")
    filter_horizontal = ("collaborators",)
    inlines = [BoardAssetInline]


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    list_display = ("__str__", "public_site")

    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()  # singleton


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ("display_title", "kind", "owner", "created_at")
    list_filter = ("kind",)
    search_fields = ("title", "link_title", "link_url", "embed_url")
    filter_horizontal = ("categories",)
