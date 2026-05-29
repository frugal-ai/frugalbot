Here is a comprehensive guide to writing good tests for a Python Textual app.

## The Core Tool: `run_test()` + Pilot

Textual's built-in `run_test()` method is the foundation of UI testing  [textual.textualize](https://textual.textualize.io/guide/testing/). It runs your app in **headless mode** (no terminal output) and returns a `Pilot` object you use to simulate user interaction. Because Textual is `asyncio`-based, your tests must be `async` functions  [textual.textualize](https://textual.textualize.io/guide/testing/).

A minimal example:

```python
from myapp import MyApp


async def test_some_behavior():
    app = MyApp()
    async with app.run_test() as pilot:
        await pilot.press("r")
        assert app.screen.styles.background == Color.parse("red")
```

Set `asyncio_mode = auto` in your `pytest.ini` or `pyproject.toml` to avoid decorating every test with `@pytest.mark.asyncio`  [textual.textualize](https://textual.textualize.io/guide/testing/).

## Simulating User Interactions

The `Pilot` object supports a rich set of interactions  [textual.textualize](https://textual.textualize.io/guide/testing/):

- **Key presses**: `await pilot.press("enter")`, `await pilot.press("h", "e", "l", "l", "o")` for typing
- **Clicks by CSS selector**: `await pilot.click("#my-button")` — targets widgets by their `id`
- **Click with offset**: `await pilot.click(Button, offset=(0, -1))` clicks relative to a widget
- **Double/triple clicks**: `await pilot.click(Button, times=2)`
- **Modifier keys**: `await pilot.click("#slider", control=True)`
- **Mouse hover**: `await pilot.hover("#widget-id")` (useful for snapshot tests)

## Handling Async Timing

Some messages take a moment to bubble through the widget tree  [textual.textualize](https://textual.textualize.io/guide/testing/). If an assertion fails right after an action, add a `pause()` call:

```python
await pilot.pause()  # waits for all pending messages
assert some_state == expected
```

You can also pass a `delay` parameter for an explicit wait before processing finishes  [textual.textualize](https://textual.textualize.io/guide/testing/).

## Snapshot Testing

For visual regression testing, install `pytest-textual-snapshot`  [textual.textualize](https://textual.textualize.io/guide/testing/):

```bash
pip install pytest-textual-snapshot
```

Then write a snapshot test like this:

```python
def test_my_app_looks_correct(snap_compare):
    assert snap_compare("path/to/app.py")
```

The first run generates an SVG screenshot and **intentionally fails** — you review it, then run `pytest --snapshot-update` to save it as ground truth  [textual.textualize](https://textual.textualize.io/guide/testing/). Future runs compare against that baseline, catching visual regressions automatically. You can also combine it with key presses and setup code:

```python
def test_after_interaction(snap_compare):
    async def run_before(pilot):
        await pilot.click("#submit")

    assert snap_compare("app.py", press=["tab", "enter"], run_before=run_before)
```

## Testing Different Terminal Sizes

Pass a `size` parameter to `run_test()` to test responsive layouts  [textual.textualize](https://textual.textualize.io/guide/testing/):

```python
async with app.run_test(size=(100, 50)) as pilot:
    # test at 100 cols × 50 rows
```
