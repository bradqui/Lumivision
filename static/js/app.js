/* Lumivision frontend: masonry, lightbox, modal, filters, drag & drop. */
(function () {
    "use strict";

    /* ---------------- helpers ---------------- */
    function getCookie(name) {
        const m = document.cookie.match("(^|;)\\s*" + name + "\\s*=\\s*([^;]+)");
        return m ? decodeURIComponent(m.pop()) : "";
    }
    const csrftoken = () => getCookie("csrftoken");

    function toast(msg, kind) {
        let holder = document.getElementById("lv-toasts");
        if (!holder) {
            holder = document.createElement("div");
            holder.id = "lv-toasts";
            holder.className = "lv-toasts";
            document.body.appendChild(holder);
        }
        const el = document.createElement("div");
        el.className = "lv-toast lv-toast-" + (kind || "info");
        el.textContent = msg;
        holder.appendChild(el);
        setTimeout(() => el.classList.add("hide"), 3600);
        setTimeout(() => el.remove(), 4100);
    }
    window.lvToast = toast;

    /* auto-dismiss server-rendered toasts */
    document.querySelectorAll(".lv-toast").forEach((el, i) => {
        setTimeout(() => el.classList.add("hide"), 3800 + i * 250);
        setTimeout(() => el.remove(), 4400 + i * 250);
    });

    /* ---------------- scroll reveal ---------------- */
    const revealObserver = new IntersectionObserver(
        (entries) => entries.forEach((e) => {
            if (e.isIntersecting) {
                e.target.classList.add("active");
                revealObserver.unobserve(e.target);
            }
        }),
        { threshold: 0.08 }
    );
    document.querySelectorAll(".reveal").forEach((el, i) => {
        el.style.transitionDelay = Math.min(i * 60, 480) + "ms";
        revealObserver.observe(el);
    });

    /* ---------------- masonry ---------------- */
    const masonry = document.querySelector(".lv-masonry");
    function layoutCard(card) {
        const rowH = 8;
        const inner = card.querySelector(".lv-card-inner");
        const h = inner ? inner.getBoundingClientRect().height : card.scrollHeight;
        // The card's border and bottom margin sit inside its grid area —
        // they must be part of the span or the footer gets clipped.
        const style = getComputedStyle(card);
        const extra =
            (parseFloat(style.marginBottom) || 0) +
            (parseFloat(style.borderTopWidth) || 0) +
            (parseFloat(style.borderBottomWidth) || 0);
        card.style.gridRowEnd = "span " + Math.max(10, Math.ceil((h + extra) / rowH));
    }
    function layoutMasonry() {
        if (!masonry) return;
        masonry.querySelectorAll(".lv-card:not(.filtered-out)").forEach(layoutCard);
    }
    if (masonry) {
        layoutMasonry();
        window.addEventListener("resize", () => {
            clearTimeout(window.__lvResize);
            window.__lvResize = setTimeout(layoutMasonry, 120);
        });
        masonry.querySelectorAll("img").forEach((img) => {
            if (!img.complete) img.addEventListener("load", () => layoutCard(img.closest(".lv-card")), { once: true });
            img.addEventListener("error", () => {
                const card = img.closest(".lv-card");
                const media = img.closest(".lv-card-media");
                if (media) {
                    const ph = document.createElement("div");
                    ph.className = "lv-media-placeholder";
                    ph.innerHTML = '<div class="glyph">🔗</div>';
                    media.replaceChild(ph, img);
                }
                if (card) layoutCard(card);
            }, { once: true });
        });
        // safety net for late layout shifts (fonts, etc.)
        setTimeout(layoutMasonry, 350);
        window.addEventListener("load", layoutMasonry);
    }

    /* ---------------- category filter ---------------- */
    const chips = document.querySelectorAll(".lv-chip[data-cat]");
    chips.forEach((chip) => {
        chip.addEventListener("click", () => {
            chips.forEach((c) => c.classList.remove("active"));
            chip.classList.add("active");
            const cat = chip.dataset.cat;
            document.querySelectorAll(".lv-card[data-cats]").forEach((card) => {
                const cats = card.dataset.cats.split("|").filter(Boolean);
                const show = cat === "*" || cats.indexOf(cat) !== -1;
                card.classList.toggle("filtered-out", !show);
            });
            layoutMasonry();
        });
    });

    /* ---------------- generic overlays ---------------- */
    function openOverlay(el) {
        el.classList.add("open");
        document.body.style.overflow = "hidden";
    }
    function closeOverlay(el) {
        el.classList.remove("open");
        document.body.style.overflow = "";
    }
    document.querySelectorAll("[data-open-overlay]").forEach((btn) => {
        btn.addEventListener("click", (ev) => {
            ev.preventDefault();
            const target = document.getElementById(btn.dataset.openOverlay);
            if (target) openOverlay(target);
        });
    });
    document.querySelectorAll(".lv-overlay").forEach((ov) => {
        ov.addEventListener("click", (ev) => {
            if (ev.target === ov) closeOverlay(ov);
        });
        ov.querySelectorAll("[data-close-overlay]").forEach((btn) =>
            btn.addEventListener("click", () => closeOverlay(ov))
        );
    });
    document.addEventListener("keydown", (ev) => {
        if (ev.key === "Escape")
            document.querySelectorAll(".lv-overlay.open").forEach(closeOverlay);
        if (ev.key === "ArrowRight" || ev.key === "ArrowLeft") {
            const lb = document.getElementById("lv-lightbox");
            if (lb && lb.classList.contains("open"))
                lightboxStep(ev.key === "ArrowRight" ? 1 : -1);
        }
    });

    /* ---------------- add-asset modal tabs ---------------- */
    const assetModal = document.getElementById("lv-asset-modal");
    if (assetModal) {
        const tabs = assetModal.querySelectorAll(".lv-tab");
        const kindInput = assetModal.querySelector("input[name='kind']");
        tabs.forEach((tab) => {
            tab.addEventListener("click", () => {
                tabs.forEach((t) => t.classList.remove("active"));
                tab.classList.add("active");
                assetModal.querySelectorAll(".lv-tabpane").forEach((p) =>
                    p.classList.toggle("active", p.dataset.pane === tab.dataset.tab)
                );
                kindInput.value = tab.dataset.kind;
            });
        });

        /* live OG preview on the Link tab */
        const linkInput = assetModal.querySelector("input[name='link_url']");
        const ogBox = assetModal.querySelector(".lv-og-preview");
        if (linkInput && ogBox) {
            let ogTimer;
            linkInput.addEventListener("input", () => {
                clearTimeout(ogTimer);
                ogTimer = setTimeout(async () => {
                    const url = linkInput.value.trim();
                    if (!/^https?:\/\/.+\..+/.test(url)) { ogBox.style.display = "none"; return; }
                    try {
                        const r = await fetch(assetModal.dataset.ogUrl, {
                            method: "POST",
                            headers: { "X-CSRFToken": csrftoken(), "Content-Type": "application/json" },
                            body: JSON.stringify({ url }),
                        });
                        const data = await r.json();
                        if (data.ok && (data.title || data.image)) {
                            ogBox.querySelector(".og-title").textContent = data.title || url;
                            ogBox.querySelector(".og-desc").textContent = data.description || "";
                            const img = ogBox.querySelector("img");
                            if (data.image) { img.src = data.image; img.style.display = "block"; }
                            else img.style.display = "none";
                            ogBox.style.display = "block";
                            const titleField = assetModal.querySelector("input[name='title']");
                            if (titleField && !titleField.value) titleField.value = data.title || "";
                        }
                    } catch (e) { /* preview is best-effort */ }
                }, 600);
            });
        }

        /* AJAX submit */
        const form = assetModal.querySelector("form");
        form.addEventListener("submit", async (ev) => {
            ev.preventDefault();
            const btn = form.querySelector("button[type='submit']");
            btn.disabled = true;
            btn.textContent = "Adding…";
            try {
                const r = await fetch(form.action, {
                    method: "POST",
                    headers: { "X-CSRFToken": csrftoken() },
                    body: new FormData(form),
                });
                const data = await r.json();
                if (data.ok) {
                    window.location.href = data.redirect;
                } else {
                    const msgs = [];
                    Object.entries(data.errors || {}).forEach(([field, errs]) =>
                        errs.forEach((e) => msgs.push((field === "__all__" ? "" : field + ": ") + e))
                    );
                    toast(msgs.join(" ") || "Could not add asset.", "error");
                    btn.disabled = false;
                    btn.textContent = "Add to board";
                }
            } catch (e) {
                toast("Upload failed — check your connection.", "error");
                btn.disabled = false;
                btn.textContent = "Add to board";
            }
        });
    }

    /* ---------------- lightbox ---------------- */
    const lightbox = document.getElementById("lv-lightbox");
    let lbItems = [];
    let lbIndex = 0;

    function visibleCards() {
        return Array.from(document.querySelectorAll(".lv-card[data-lb]:not(.filtered-out)"));
    }

    function renderLightbox() {
        const item = lbItems[lbIndex];
        if (!item) return;
        const media = lightbox.querySelector(".lv-lightbox-media");
        const cap = lightbox.querySelector(".lv-lightbox-caption");
        media.innerHTML = "";
        if (item.kind === "image") {
            const img = document.createElement("img");
            img.src = item.src;
            img.alt = item.title || "";
            media.appendChild(img);
        } else if (item.kind === "video") {
            const v = document.createElement("video");
            v.src = item.src;
            v.controls = true;
            v.autoplay = true;
            media.appendChild(v);
        } else if (item.kind === "embed") {
            const wrap = document.createElement("div");
            wrap.className = "frame-wrap";
            const f = document.createElement("iframe");
            f.src = item.src + (item.src.indexOf("?") === -1 ? "?autoplay=1" : "&autoplay=1");
            f.allow = "autoplay; fullscreen; picture-in-picture; encrypted-media";
            f.allowFullscreen = true;
            wrap.appendChild(f);
            media.appendChild(wrap);
        } else if (item.kind === "link") {
            const wrap = document.createElement("div");
            wrap.style.textAlign = "center";
            if (item.src) {
                const img = document.createElement("img");
                img.src = item.src;
                img.alt = item.title || "";
                wrap.appendChild(img);
            }
            media.appendChild(wrap);
        }
        let capHtml =
            '<div><div class="t">' + escapeHtml(item.title || "") + '</div>' +
            (item.desc ? '<div class="d">' + escapeHtml(item.desc) + "</div>" : "") +
            "</div>" +
            '<div style="display:flex;gap:0.6rem;flex-wrap:wrap;">';
        if (item.kind === "link" && item.href)
            capHtml += '<a class="btn btn-gold btn-sm" href="' + item.href + '" target="_blank" rel="noopener">Visit link ↗</a>';
        capHtml += '<button class="btn btn-ghost btn-sm" data-share="' + item.permalink + '">Copy link</button></div>';
        cap.innerHTML = capHtml;
        cap.querySelector("[data-share]").addEventListener("click", (ev) =>
            copyText(ev.target.dataset.share)
        );
    }

    function openLightboxFromCard(card) {
        const cards = visibleCards();
        lbItems = cards.map((c) => JSON.parse(c.dataset.lb));
        lbIndex = cards.indexOf(card);
        renderLightbox();
        openOverlay(lightbox);
    }
    function lightboxStep(dir) {
        if (!lbItems.length) return;
        lbIndex = (lbIndex + dir + lbItems.length) % lbItems.length;
        renderLightbox();
    }
    window.lightboxStep = lightboxStep;

    if (lightbox) {
        lightbox.querySelector(".lv-lightbox-prev").addEventListener("click", () => lightboxStep(-1));
        lightbox.querySelector(".lv-lightbox-next").addEventListener("click", () => lightboxStep(1));
        lightbox.addEventListener("transitionend", () => {
            if (!lightbox.classList.contains("open"))
                lightbox.querySelector(".lv-lightbox-media").innerHTML = "";
        });
        document.querySelectorAll(".lv-card[data-lb]").forEach((card) => {
            card.addEventListener("click", (ev) => {
                if (ev.target.closest(".lv-card-actions") || ev.target.closest("a")) return;
                openLightboxFromCard(card);
            });
        });
        /* deep link: /b/slug/#a123 opens that asset */
        const m = location.hash.match(/^#a(\d+)$/);
        if (m) {
            const target = document.querySelector('.lv-card[data-asset-id="' + m[1] + '"]');
            if (target) setTimeout(() => openLightboxFromCard(target), 300);
        }
    }

    function escapeHtml(s) {
        return String(s).replace(/[&<>"']/g, (c) => ({
            "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
        }[c]));
    }

    /* ---------------- copy to clipboard ---------------- */
    function copyText(text) {
        const abs = text.startsWith("http") ? text : location.origin + text;
        navigator.clipboard.writeText(abs).then(
            () => toast("Link copied to clipboard ✨", "success"),
            () => toast("Could not copy link.", "error")
        );
    }
    document.querySelectorAll("[data-copy]").forEach((btn) =>
        btn.addEventListener("click", (ev) => {
            ev.preventDefault();
            ev.stopPropagation();
            copyText(btn.dataset.copy);
        })
    );

    /* ---------------- confirm-on-submit forms ---------------- */
    document.querySelectorAll("form[data-confirm]").forEach((form) =>
        form.addEventListener("submit", (ev) => {
            if (!window.confirm(form.dataset.confirm)) ev.preventDefault();
        })
    );

    /* ---------------- drag & drop upload ---------------- */
    const dropzone = document.getElementById("lv-dropzone");
    if (dropzone) {
        const uploadUrl = dropzone.dataset.uploadUrl;
        const progress = document.getElementById("lv-upload-progress");
        let dragDepth = 0;

        window.addEventListener("dragenter", (ev) => {
            if (!ev.dataTransfer || !Array.from(ev.dataTransfer.types).includes("Files")) return;
            dragDepth++;
            dropzone.classList.add("active");
        });
        window.addEventListener("dragleave", () => {
            dragDepth = Math.max(0, dragDepth - 1);
            if (!dragDepth) dropzone.classList.remove("active");
        });
        window.addEventListener("dragover", (ev) => ev.preventDefault());
        window.addEventListener("drop", async (ev) => {
            ev.preventDefault();
            dragDepth = 0;
            dropzone.classList.remove("active");
            const files = Array.from(ev.dataTransfer.files || []);
            if (!files.length) return;
            const fd = new FormData();
            files.forEach((f) => fd.append("files", f));
            progress.textContent = "Uploading " + files.length + " file" + (files.length > 1 ? "s" : "") + "…";
            progress.classList.add("active");
            try {
                const r = await fetch(uploadUrl, {
                    method: "POST",
                    headers: { "X-CSRFToken": csrftoken() },
                    body: fd,
                });
                const data = await r.json();
                progress.classList.remove("active");
                if (data.ok) {
                    if (data.errors && data.errors.length) toast(data.errors.join(" · "), "error");
                    if (data.created) window.location.reload();
                } else toast("Upload failed.", "error");
            } catch (e) {
                progress.classList.remove("active");
                toast("Upload failed — check your connection.", "error");
            }
        });
    }

    /* ---------------- drag reorder (board owner) ---------------- */
    const reorderUrl = masonry ? masonry.dataset.reorderUrl : null;
    if (masonry && reorderUrl) {
        let dragged = null;
        masonry.querySelectorAll(".lv-card").forEach((card) => {
            card.setAttribute("draggable", "true");
            card.addEventListener("dragstart", (ev) => {
                dragged = card;
                card.classList.add("dragging");
                ev.dataTransfer.effectAllowed = "move";
                try { ev.dataTransfer.setData("text/plain", card.dataset.assetId); } catch (e) {}
            });
            card.addEventListener("dragend", () => {
                card.classList.remove("dragging");
                masonry.querySelectorAll(".drag-over").forEach((c) => c.classList.remove("drag-over"));
                dragged = null;
            });
            card.addEventListener("dragover", (ev) => {
                if (!dragged || dragged === card) return;
                ev.preventDefault();
                card.classList.add("drag-over");
            });
            card.addEventListener("dragleave", () => card.classList.remove("drag-over"));
            card.addEventListener("drop", async (ev) => {
                ev.preventDefault();
                ev.stopPropagation();
                card.classList.remove("drag-over");
                if (!dragged || dragged === card) return;
                const cards = Array.from(masonry.querySelectorAll(".lv-card"));
                const from = cards.indexOf(dragged);
                const to = cards.indexOf(card);
                if (from < to) card.after(dragged);
                else card.before(dragged);
                layoutMasonry();
                const order = Array.from(masonry.querySelectorAll(".lv-card")).map(
                    (c) => c.dataset.assetId
                );
                try {
                    await fetch(reorderUrl, {
                        method: "POST",
                        headers: { "X-CSRFToken": csrftoken(), "Content-Type": "application/json" },
                        body: JSON.stringify({ order }),
                    });
                } catch (e) {
                    toast("Could not save the new order.", "error");
                }
            });
        });
    }
})();
