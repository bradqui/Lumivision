"""Theme registry. Each theme maps to a `theme-<key>` body class in
lumivision.css; hex values here are only used to draw picker swatches."""

THEMES = [
    {
        "key": "purple-gold-dark",
        "label": "Royal (dark)",
        "hex1": "#7E74D4",
        "hex2": "#F2C478",
        "bg": "#07080D",
    },
    {
        "key": "neon-cyan-dark",
        "label": "Neon Cyan (dark)",
        "hex1": "#38BDF8",
        "hex2": "#2DD4BF",
        "bg": "#04090F",
    },
    {
        "key": "emerald-dark",
        "label": "Emerald (dark)",
        "hex1": "#34D399",
        "hex2": "#E3C55F",
        "bg": "#050B08",
    },
    {
        "key": "ember-dark",
        "label": "Ember (dark)",
        "hex1": "#F97316",
        "hex2": "#FACC15",
        "bg": "#0C0604",
    },
    {
        "key": "ivory-light",
        "label": "Ivory (light)",
        "hex1": "#6858D6",
        "hex2": "#B07C20",
        "bg": "#F4F2EC",
    },
    {
        "key": "sky-light",
        "label": "Sky (light)",
        "hex1": "#2563EB",
        "hex2": "#0D9488",
        "bg": "#EEF3F9",
    },
    {
        "key": "rose-light",
        "label": "Rosé (light)",
        "hex1": "#DB2777",
        "hex2": "#9333EA",
        "bg": "#FAF3F5",
    },
]

THEME_KEYS = [t["key"] for t in THEMES]
THEME_CHOICES = [(t["key"], t["label"]) for t in THEMES]
DEFAULT_THEME = "purple-gold-dark"
