# Contributing

Thanks for considering a contribution. This is a small hobby project, so expectations are light — but a few conventions help keep it maintainable.

## Development setup

```bash
git clone https://github.com/<your-user>/financial-dashboard.git
cd financial-dashboard
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt pytest
```

Run the app:

```bash
python main.py
```

Run the tests:

```bash
python -m pytest tests/ -q
```

Regenerate the README screenshot (headless, no display required):

```bash
QT_QPA_PLATFORM=offscreen python scripts/generate_screenshot.py
```

## Project conventions

- **Python 3.10+** — the code uses modern syntax (`X | None`, PEP 604 unions).
- **No new top-level dependencies** without a good reason. The goal is a small, auditable stack.
- **No mocking of `yfinance` in tests.** The tests for the predictor inject synthetic OHLCV directly via `monkeypatch`, which keeps them fast and deterministic without touching the network.
- **UI stays on the main thread.** Anything that can block (network, model training, disk I/O beyond SQLite CRUD) must go through the `QThreadPool` in `app/ui/main_window.py` so the window never freezes.
- **SQLite connections are per-call** via `get_conn()` in `app/data/db.py`. Do not share a connection across threads.

## Adding a new indicator

1. Implement it in `app/indicators.py` as a pure function over a `pandas.Series` or OHLCV DataFrame.
2. Add it to `build_feature_frame` if it should be used by the predictor.
3. Add a unit test in `tests/test_indicators.py` with a synthetic series.

## Adding a new prediction feature explanation

Edit `_describe_feature` in `app/ui/prediction_panel.py`. Each branch takes a raw feature value and returns an HTML snippet describing it in plain English. Keep it short and factual.

## Pull requests

- Keep PRs focused. One feature or fix per PR is much easier to review.
- Run `pytest tests/ -q` before pushing.
- If you touch the UI, regenerate `docs/screenshot.png` and include it in the PR.
- Update the README if you add a user-visible feature.

## Reporting bugs

Please open a GitHub issue with:
- Your OS and Python version
- The symbol(s) involved, if relevant
- The full traceback (the app now logs to stderr, so running `python main.py` from a terminal will surface errors)

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
