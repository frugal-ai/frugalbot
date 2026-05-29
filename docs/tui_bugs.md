### Bug 10: `on_worker_state_changed` — one-shot mode quit path has no error handling

**Location**: `on_worker_state_changed()` method

```python
elif event.state in (WorkerState.SUCCESS, WorkerState.ERROR, WorkerState.CANCELLED):
    ...
    if self.one_shot_mode:
        self.input.load_text("/quit")
        await self.action_submit()
```

This recursively triggers `action_submit()` → `execute_command()` which calls `app.exit()`. If any part of this chain fails, it's unhandled.
