# Contributing to Lumivision

Thanks for your interest in improving Lumivision! This document covers how to get a
development environment running and how changes make their way into a release.

## Development setup

```bash
git clone https://github.com/bradqui/Lumivision.git && cd Lumivision
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export LUMIVISION_DEBUG=1                            # Windows: $env:LUMIVISION_DEBUG="1"
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Optional: install `ffmpeg` locally if you're working on video poster extraction —
everything else works without it.

To test the actual container build:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

## Running tests

```bash
python manage.py test
```

CI runs the test suite, Django system checks, and a production static build on every
push and pull request. All of these must pass before a change is merged.

## Making changes

1. Fork the repository (or create a branch if you have write access).
2. Create a feature branch from `main`: `git checkout -b feature/short-description`
3. Make your changes. Please:
   - Match the existing code style (Django conventions, 4-space indentation).
   - Add or update tests in `core/tests.py` for anything user-visible or security-relevant.
   - Update `README.md` if you add configuration options or change behavior.
   - Create database migrations with `python manage.py makemigrations` when models change.
4. Run the test suite locally.
5. Open a pull request against `main` describing what changed and why.

Keep pull requests focused — one feature or fix per PR is much easier to review.

## Reporting bugs

Open a GitHub issue with steps to reproduce, what you expected, and what happened
instead. Screenshots help a lot for UI issues.

## Reporting security vulnerabilities

Please **do not** open a public issue for security problems. Use GitHub's private
vulnerability reporting ("Report a vulnerability" under the repository's Security tab)
so a fix can ship before details are public.

## License

By contributing, you agree that your contributions are licensed under the
[MIT License](LICENSE).
