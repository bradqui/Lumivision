import io
import json
import os
import shutil
import tempfile
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.test import Client, TestCase, override_settings
from PIL import Image

from .models import Asset, Board, BoardAsset, Invite, SiteSettings, User
from .utils import parse_embed

MEDIA_TMP = tempfile.mkdtemp(prefix="lumivision-test-media-")


def image_file(name="test.png", size=(640, 400), color=(126, 116, 212), fmt="PNG"):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, fmt)
    buf.seek(0)
    buf.name = name
    return buf


def make_user(username, role=User.Role.MEMBER, password="Test-Pass-123"):
    return User.objects.create_user(username, password=password, role=role)


def login(username, password="Test-Pass-123"):
    c = Client()
    assert c.login(username=username, password=password)
    return c


@override_settings(MEDIA_ROOT=MEDIA_TMP)
class MediaTestCase(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_TMP, ignore_errors=True)
        os.makedirs(MEDIA_TMP, exist_ok=True)


class InviteRegistrationTests(MediaTestCase):
    def setUp(self):
        self.admin = make_user("admin", User.Role.ADMIN)
        self.c_admin = login("admin")

    def test_admin_creates_invite_and_user_registers(self):
        r = self.c_admin.post(
            "/manage/invites/", {"role": "member", "note": "t", "max_uses": 2}
        )
        self.assertEqual(r.status_code, 302)
        invite = Invite.objects.get()

        c = Client()
        self.assertEqual(c.get(f"/join/{invite.token}/").status_code, 200)
        r = c.post(
            f"/join/{invite.token}/",
            {
                "username": "newbie",
                "email": "",
                "password1": "Vividly-Bright-9",
                "password2": "Vividly-Bright-9",
            },
        )
        self.assertEqual(r.status_code, 302)
        user = User.objects.get(username="newbie")
        self.assertEqual(user.role, User.Role.MEMBER)
        invite.refresh_from_db()
        self.assertEqual(invite.use_count, 1)

    def test_exhausted_and_revoked_invites_rejected(self):
        invite = Invite.objects.create(
            role=User.Role.MEMBER, created_by=self.admin, max_uses=1, use_count=1
        )
        self.assertEqual(Client().get(f"/join/{invite.token}/").status_code, 410)
        invite2 = Invite.objects.create(
            role=User.Role.MEMBER, created_by=self.admin, revoked=True
        )
        self.assertEqual(Client().get(f"/join/{invite2.token}/").status_code, 410)

    def test_member_cannot_manage_invites(self):
        make_user("m1")
        c = login("m1")
        self.assertEqual(c.get("/manage/invites/").status_code, 403)


class BoardVisibilityTests(MediaTestCase):
    def setUp(self):
        self.admin = make_user("admin", User.Role.ADMIN)
        self.member = make_user("member")
        self.viewer = make_user("viewer", User.Role.VIEWER)
        self.private = Board.objects.create(
            name="Secret", owner=self.admin, visibility=Board.Visibility.PRIVATE
        )
        self.registered = Board.objects.create(name="Shared", owner=self.member)
        self.public = Board.objects.create(
            name="Open", owner=self.member, visibility=Board.Visibility.PUBLIC
        )

    def test_dashboard_requires_login(self):
        self.assertEqual(Client().get("/").status_code, 302)

    def test_private_board_hidden_from_others(self):
        c = login("viewer")
        self.assertEqual(c.get(f"/b/{self.private.slug}/").status_code, 403)

    def test_public_board_anonymous_readonly(self):
        r = Client().get(f"/b/{self.public.slug}/")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn(b"lv-fab", r.content)

    def test_registered_board_redirects_anonymous(self):
        self.assertEqual(
            Client().get(f"/b/{self.registered.slug}/").status_code, 302
        )

    def test_viewer_cannot_create_board(self):
        c = login("viewer")
        self.assertEqual(
            c.post("/boards/new/", {"name": "X", "visibility": "private"}).status_code,
            403,
        )

    def test_collaborator_sees_private_board(self):
        self.private.collaborators.add(self.member)
        c = login("member")
        self.assertEqual(c.get(f"/b/{self.private.slug}/").status_code, 200)


class AssetTests(MediaTestCase):
    def setUp(self):
        self.member = make_user("member")
        self.other = make_user("other")
        self.viewer = make_user("viewer", User.Role.VIEWER)
        self.c = login("member")
        self.board = Board.objects.create(name="Mine", owner=self.member)
        self.public = Board.objects.create(
            name="Open", owner=self.member, visibility=Board.Visibility.PUBLIC
        )

    def _create_image_asset(self, boards=None):
        r = self.c.post(
            "/assets/new/",
            {
                "kind": "image",
                "title": "Pic",
                "description": "",
                "categories": "Travel, Home",
                "boards": boards or [self.board.pk],
                "file": image_file(),
            },
        )
        self.assertEqual(r.status_code, 200, r.content)
        return Asset.objects.latest("pk")

    def test_image_upload_thumbnail_categories(self):
        asset = self._create_image_asset(boards=[self.board.pk, self.public.pk])
        self.assertEqual(asset.kind, Asset.Kind.IMAGE)
        self.assertTrue(asset.thumb)
        self.assertEqual(asset.boards.count(), 2)
        self.assertEqual(asset.categories.count(), 2)
        self.assertTrue(os.path.exists(asset.file.path))

    def test_youtube_embed_parsed_offline(self):
        r = self.c.post(
            "/assets/new/",
            {
                "kind": "embed",
                "title": "Vid",
                "embed_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "boards": [self.board.pk],
                "categories": "",
                "description": "",
            },
        )
        self.assertEqual(r.status_code, 200)
        asset = Asset.objects.latest("pk")
        self.assertIn("youtube-nocookie.com/embed/dQw4w9WgXcQ", asset.embed_src)
        self.assertIn("i.ytimg.com", asset.embed_thumb_url)

    @patch("core.views.fetch_og")
    def test_link_asset_uses_og_data(self, mock_og):
        mock_og.return_value = {
            "title": "Example",
            "description": "d",
            "image": "https://example.com/x.jpg",
        }
        r = self.c.post(
            "/assets/new/",
            {
                "kind": "link",
                "title": "",
                "link_url": "https://example.com/",
                "boards": [self.board.pk],
                "categories": "",
                "description": "",
            },
        )
        self.assertEqual(r.status_code, 200)
        asset = Asset.objects.latest("pk")
        self.assertEqual(asset.link_title, "Example")

    def test_quick_upload_requires_contribution(self):
        c_other = login("other")
        r = c_other.post(
            f"/b/{self.board.slug}/upload/", {"files": [image_file("q.jpg", fmt="JPEG")]}
        )
        self.assertEqual(r.status_code, 403)
        self.board.collaborators.add(self.other)
        r = c_other.post(
            f"/b/{self.board.slug}/upload/", {"files": [image_file("q.jpg", fmt="JPEG")]}
        )
        self.assertEqual(json.loads(r.content)["created"], 1)

    def test_delete_rules_and_file_cleanup(self):
        asset = self._create_image_asset(boards=[self.board.pk, self.public.pk])
        file_path, thumb_path = asset.file.path, asset.thumb.path

        c_viewer = login("viewer")
        self.assertEqual(
            c_viewer.post(f"/a/{asset.pk}/delete/").status_code, 403
        )

        r = self.c.post(f"/b/{self.board.slug}/remove/{asset.pk}/")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(asset.boards.count(), 1)

        r = self.c.post(f"/a/{asset.pk}/delete/")
        self.assertEqual(r.status_code, 302)
        self.assertFalse(os.path.exists(file_path))
        self.assertFalse(os.path.exists(thumb_path))

    def test_asset_permalink_visibility(self):
        asset = self._create_image_asset(boards=[self.public.pk])
        self.assertEqual(Client().get(f"/a/{asset.pk}/").status_code, 200)
        hidden = self._create_image_asset(boards=[self.board.pk])
        self.assertEqual(Client().get(f"/a/{hidden.pk}/").status_code, 302)

    def test_reorder(self):
        a1 = self._create_image_asset()
        a2 = self._create_image_asset()
        r = self.c.post(
            f"/b/{self.board.slug}/reorder/",
            json.dumps({"order": [a2.pk, a1.pk]}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200)
        first = (
            BoardAsset.objects.filter(board=self.board).order_by("sort_order").first()
        )
        self.assertEqual(first.asset_id, a2.pk)

    def test_edit_asset(self):
        asset = self._create_image_asset()
        c_other = login("other")
        self.assertEqual(c_other.get(f"/a/{asset.pk}/edit/").status_code, 403)
        board2 = Board.objects.create(name="Second", owner=self.member)
        r = self.c.post(
            f"/a/{asset.pk}/edit/",
            {
                "title": "Renamed",
                "description": "now described",
                "categories": "Outdoor",
                "boards": [board2.pk],
            },
        )
        self.assertEqual(r.status_code, 302)
        asset.refresh_from_db()
        self.assertEqual(asset.title, "Renamed")
        self.assertEqual(
            list(asset.boards.values_list("name", flat=True)), ["Second"]
        )

    def test_upload_rejects_unknown_extension(self):
        bad = io.BytesIO(b"plain text")
        bad.name = "notes.txt"
        r = self.c.post(
            "/assets/new/",
            {"kind": "image", "boards": [self.board.pk], "file": bad,
             "title": "", "description": "", "categories": ""},
        )
        self.assertEqual(r.status_code, 400)


class ThemeTests(MediaTestCase):
    def setUp(self):
        self.member = make_user("member")
        self.c = login("member")

    def test_user_theme_saved_and_applied(self):
        r = self.c.post("/account/", {"theme": "neon-cyan-dark"})
        self.assertEqual(r.status_code, 302)
        self.assertIn(b"theme-neon-cyan-dark", self.c.get("/").content)

    def test_bogus_theme_rejected(self):
        self.c.post("/account/", {"theme": "nope"})
        self.member.refresh_from_db()
        self.assertEqual(self.member.theme, "purple-gold-dark")

    def test_board_theme_overrides_user_theme(self):
        board = Board.objects.create(
            name="Sky", owner=self.member, theme="sky-light",
            visibility=Board.Visibility.PUBLIC,
        )
        self.assertIn(b"theme-sky-light", Client().get(f"/b/{board.slug}/").content)

    def test_dashboard_card_stamped_with_board_theme(self):
        Board.objects.create(name="Ember", owner=self.member, theme="ember-dark")
        self.assertIn(b"theme-ember-dark", self.c.get("/").content)


class AccountTests(MediaTestCase):
    def setUp(self):
        self.admin = make_user("admin", User.Role.ADMIN)
        self.member = make_user("member")
        self.c = login("member")

    def test_password_change_keeps_session(self):
        r = self.c.post(
            "/account/password/",
            {
                "old_password": "Test-Pass-123",
                "new_password1": "Nova-Cascade-77",
                "new_password2": "Nova-Cascade-77",
            },
        )
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.c.get("/account/").status_code, 200)
        self.assertTrue(
            Client().login(username="member", password="Nova-Cascade-77")
        )

    def test_admin_sets_user_password(self):
        c_admin = login("admin")
        r = c_admin.post(
            f"/manage/users/{self.member.pk}/password/",
            {"new_password1": "Zephyr-Quartz-88", "new_password2": "Zephyr-Quartz-88"},
        )
        self.assertEqual(r.status_code, 302)
        self.assertTrue(
            Client().login(username="member", password="Zephyr-Quartz-88")
        )

    def test_member_cannot_set_passwords(self):
        r = self.c.post(
            f"/manage/users/{self.admin.pk}/password/",
            {"new_password1": "x", "new_password2": "x"},
        )
        self.assertEqual(r.status_code, 403)

    def test_promotion_grants_and_revokes_django_admin(self):
        c_admin = login("admin")
        c_admin.post(
            f"/manage/users/{self.member.pk}/update/",
            {"action": "role", "role": "admin"},
        )
        self.member.refresh_from_db()
        self.assertTrue(self.member.is_staff and self.member.is_superuser)
        c_admin.post(
            f"/manage/users/{self.member.pk}/update/",
            {"action": "role", "role": "member"},
        )
        self.member.refresh_from_db()
        self.assertFalse(self.member.is_staff or self.member.is_superuser)

    def test_avatar_upload_replace_remove(self):
        r = self.c.post(
            "/account/", {"action": "avatar", "avatar": image_file("me.png")}
        )
        self.assertEqual(r.status_code, 302)
        self.member.refresh_from_db()
        self.assertTrue(self.member.avatar)
        with Image.open(self.member.avatar.path) as img:
            self.assertEqual(img.size, (256, 256))
        path = self.member.avatar.path

        self.c.post("/account/", {"action": "remove_avatar"})
        self.member.refresh_from_db()
        self.assertFalse(self.member.avatar)
        self.assertFalse(os.path.exists(path))


class BoardImageTests(MediaTestCase):
    def setUp(self):
        self.member = make_user("member")
        self.c = login("member")

    def _png_content(self):
        buf = image_file()
        return ContentFile(buf.read(), name="b.png")

    def test_clear_banner_deletes_file(self):
        board = Board.objects.create(
            name="B", owner=self.member, banner_image=self._png_content()
        )
        path = board.banner_image.path
        r = self.c.post(
            f"/b/{board.slug}/edit/",
            {"name": "B", "description": "", "visibility": "registered",
             "theme": "", "banner_image-clear": "on"},
        )
        self.assertEqual(r.status_code, 302)
        board.refresh_from_db()
        self.assertFalse(board.banner_image)
        self.assertFalse(os.path.exists(path))

    def test_board_delete_cleans_cover(self):
        board = Board.objects.create(
            name="B2", owner=self.member, banner_image=self._png_content()
        )
        path = board.banner_image.path
        self.c.post(f"/b/{board.slug}/delete/")
        self.assertFalse(os.path.exists(path))


class SecurityTests(MediaTestCase):
    def setUp(self):
        self.member = make_user("member")
        self.c = login("member")

    def test_healthz(self):
        r = Client().get("/healthz")
        self.assertEqual(r.status_code, 200)

    def test_referrer_policy_allows_youtube_embeds(self):
        # same-origin (Django's default) breaks the YouTube player (error 153)
        r = Client().get("/accounts/login/")
        self.assertEqual(
            r.headers.get("Referrer-Policy"), "strict-origin-when-cross-origin"
        )

    def test_oversized_body_rejected_early(self):
        r = self.c.post(
            "/assets/new/", {"x": "y"},
            CONTENT_LENGTH=str(10 * 1024 * 1024 * 1024),
        )
        self.assertEqual(r.status_code, 413)

    def test_og_preview_requires_member(self):
        viewer = make_user("viewer", User.Role.VIEWER)
        c = login("viewer")
        r = c.post(
            "/api/og-preview/",
            json.dumps({"url": "https://example.com"}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 403)

    def test_ssrf_guard_blocks_private_hosts(self):
        from core.utils import _host_is_public

        for host in ("127.0.0.1", "10.0.0.5", "192.168.1.1", "169.254.169.254"):
            self.assertFalse(_host_is_public(host), host)

    def test_embed_parser_ignores_lookalike_domains(self):
        self.assertIsNone(parse_embed("https://evil.com/watch?v=x"))
        self.assertIsNotNone(
            parse_embed("https://youtu.be/dQw4w9WgXcQ")
        )


@override_settings(AXES_ENABLED=True, AXES_FAILURE_LIMIT=3)
class LoginRateLimitTests(MediaTestCase):
    def test_lockout_after_repeated_failures(self):
        make_user("target")
        c = Client()
        for _ in range(3):
            r = c.post(
                "/accounts/login/",
                {"username": "target", "password": "wrong-pass"},
            )
        # Locked out now — even the correct password is refused.
        r = c.post(
            "/accounts/login/",
            {"username": "target", "password": "Test-Pass-123"},
        )
        self.assertEqual(r.status_code, 429)

    def test_other_account_unaffected_by_lockout(self):
        make_user("target")
        make_user("bystander")
        c = Client()
        for _ in range(3):
            c.post(
                "/accounts/login/",
                {"username": "target", "password": "wrong-pass"},
            )
        r = Client().post(
            "/accounts/login/",
            {"username": "bystander", "password": "Test-Pass-123"},
        )
        self.assertEqual(r.status_code, 302)


class PreviewReplaceTests(MediaTestCase):
    def setUp(self):
        self.member = make_user("member")
        self.c = login("member")
        self.board = Board.objects.create(name="Mine", owner=self.member)

    def _make_link_asset(self):
        with patch("core.views.fetch_og") as mock_og:
            mock_og.return_value = {
                "title": "Example",
                "description": "d",
                "image": "https://example.com/x.jpg",
            }
            self.c.post(
                "/assets/new/",
                {"kind": "link", "link_url": "https://example.com/",
                 "boards": [self.board.pk], "title": "", "description": "",
                 "categories": ""},
            )
        return Asset.objects.latest("pk")

    def test_link_asset_offers_and_applies_replacement(self):
        asset = self._make_link_asset()
        r = self.c.get(f"/a/{asset.pk}/edit/")
        self.assertIn(b"Replace preview image", r.content)
        r = self.c.post(
            f"/a/{asset.pk}/edit/",
            {"title": "", "description": "", "categories": "",
             "boards": [self.board.pk], "custom_thumb": image_file("p.png")},
        )
        self.assertEqual(r.status_code, 302)
        asset.refresh_from_db()
        self.assertTrue(asset.thumb)
        # The replaced preview beats the fetched OG image everywhere.
        self.assertEqual(asset.preview_url, asset.thumb.url)

    def test_image_asset_keeps_generated_thumbnail(self):
        self.c.post(
            "/assets/new/",
            {"kind": "image", "boards": [self.board.pk], "file": image_file(),
             "title": "", "description": "", "categories": ""},
        )
        asset = Asset.objects.latest("pk")
        original_thumb = asset.thumb.name
        r = self.c.get(f"/a/{asset.pk}/edit/")
        self.assertNotIn(b"Replace preview image", r.content)
        # Even a hand-crafted POST can't replace an image's thumbnail.
        self.c.post(
            f"/a/{asset.pk}/edit/",
            {"title": "", "description": "", "categories": "",
             "boards": [self.board.pk], "custom_thumb": image_file("p.png")},
        )
        asset.refresh_from_db()
        self.assertEqual(asset.thumb.name, original_thumb)


class CategorySuggestTests(MediaTestCase):
    def setUp(self):
        self.member = make_user("member")
        self.c = login("member")
        self.board = Board.objects.create(name="Mine", owner=self.member)
        self.c.post(
            "/assets/new/",
            {"kind": "image", "boards": [self.board.pk], "file": image_file(),
             "title": "", "description": "", "categories": "Travel, Fitness"},
        )
        self.asset = Asset.objects.latest("pk")

    def test_board_page_offers_existing_categories(self):
        r = self.c.get(f"/b/{self.board.slug}/")
        self.assertIn(b"lv-cat-suggest", r.content)
        self.assertIn(b'data-cat-name="Travel"', r.content)

    def test_edit_page_suggests_categories_from_its_boards(self):
        r = self.c.get(f"/a/{self.asset.pk}/edit/")
        self.assertIn(b'data-cat-name="Fitness"', r.content)


class BoardCollageTests(MediaTestCase):
    def setUp(self):
        self.member = make_user("member")
        self.c = login("member")
        self.board = Board.objects.create(
            name="Mine", owner=self.member, show_asset_preview=True
        )
        self.c.post(
            "/assets/new/",
            {"kind": "image", "boards": [self.board.pk], "file": image_file(),
             "title": "", "description": "", "categories": ""},
        )

    def test_collage_rendered_when_enabled(self):
        r = self.c.get("/")
        self.assertIn(b"lv-board-collage", r.content)
        asset = Asset.objects.latest("pk")
        self.assertIn(asset.thumb.url.encode(), r.content)

    def test_collage_uses_up_to_four_previews(self):
        for _ in range(4):  # 5 image assets total incl. setUp's
            self.c.post(
                "/assets/new/",
                {"kind": "image", "boards": [self.board.pk], "file": image_file(),
                 "title": "", "description": "", "categories": ""},
            )
        r = self.c.get("/")
        collage = r.content.split(b"lv-board-collage")[1].split(b"</div>")[0]
        self.assertEqual(collage.count(b"<img"), 4)

    def test_collage_absent_when_disabled(self):
        self.board.show_asset_preview = False
        self.board.save(update_fields=["show_asset_preview"])
        r = self.c.get("/")
        self.assertNotIn(b"lv-board-collage", r.content)

    def test_banner_beats_collage(self):
        self.board.banner_image.save(
            "banner.png", ContentFile(image_file().read()), save=True
        )
        r = self.c.get("/")
        self.assertIn(b"lv-board-cover", r.content)
        self.assertNotIn(b"lv-board-collage", r.content)

    def test_board_form_saves_toggle(self):
        r = self.c.post(
            f"/b/{self.board.slug}/edit/",
            {"name": "Mine", "description": "", "visibility": "registered",
             "theme": ""},
        )
        self.assertEqual(r.status_code, 302)
        self.board.refresh_from_db()
        self.assertFalse(self.board.show_asset_preview)  # unchecked box = off
        self.c.post(
            f"/b/{self.board.slug}/edit/",
            {"name": "Mine", "description": "", "visibility": "registered",
             "theme": "", "show_asset_preview": "on"},
        )
        self.board.refresh_from_db()
        self.assertTrue(self.board.show_asset_preview)


class PublicSiteTests(MediaTestCase):
    def setUp(self):
        self.admin = make_user("admin", User.Role.ADMIN)
        self.member = make_user("member")
        self.public = Board.objects.create(
            name="OpenBoard", owner=self.member, visibility=Board.Visibility.PUBLIC
        )
        self.private = Board.objects.create(
            name="SecretBoard", owner=self.member,
            visibility=Board.Visibility.PRIVATE,
        )
        self.registered = Board.objects.create(name="SharedBoard", owner=self.member)

    def test_root_redirects_guests_by_default(self):
        self.assertEqual(Client().get("/").status_code, 302)

    def test_public_site_lists_only_public_boards(self):
        SiteSettings.objects.update_or_create(pk=1, defaults={"public_site": True})
        r = Client().get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"OpenBoard", r.content)
        self.assertNotIn(b"SecretBoard", r.content)
        self.assertNotIn(b"SharedBoard", r.content)
        self.assertNotIn(b"New board", r.content)

    def test_members_still_see_everything(self):
        SiteSettings.objects.update_or_create(pk=1, defaults={"public_site": True})
        r = login("member").get("/")
        self.assertIn(b"SecretBoard", r.content)
        self.assertIn(b"SharedBoard", r.content)

    def test_settings_page_is_admin_only(self):
        self.assertEqual(login("member").get("/manage/settings/").status_code, 403)
        c = login("admin")
        self.assertEqual(c.get("/manage/settings/").status_code, 200)
        r = c.post("/manage/settings/", {"public_site": "1"})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(SiteSettings.load().public_site)
        c.post("/manage/settings/", {})  # unchecked box turns it back off
        self.assertFalse(SiteSettings.load().public_site)
