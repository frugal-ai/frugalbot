from unittest.mock import patch

from frugalbot.hooks.base import (
    HookBase,
    HookConfig,
    HookError,
    HookPriority,
    Hooks,
    PostToolCallHook,
    PreToolCallHook,
)


def test_hook_base_name_returns_lowercase_class_name() -> None:
    # Given
    class MyHook(HookBase):
        pass

    plugin = MyHook(HookConfig())

    # When
    result = plugin.name

    # Then
    assert result == "myhook"


def test_hook_base_subclassing_adds_to_registry() -> None:
    # Given
    # Registry is cleared by fixture

    # When
    class RegisteredPlugin(HookBase):
        pass

    # Then
    assert RegisteredPlugin in HookBase._registry


def test_hook_base_priority_returns_high_by_default() -> None:
    # Given
    class DefaultPriorityHook(HookBase):
        pass

    hook = DefaultPriorityHook(HookConfig())

    # When
    result = hook.priority

    # Then
    assert result == HookPriority.HIGH


def test_hook_base_priority_returns_custom_value_when_overridden() -> None:
    # Given
    class LowPriorityHook(HookBase):
        @property
        def priority(self) -> HookPriority:
            return HookPriority.LOW

    hook = LowPriorityHook(HookConfig())

    # When
    result = hook.priority

    # Then
    assert result == HookPriority.LOW


def test_hooks_register_adds_to_hooks_registry() -> None:
    # Given
    class MockHook(HookBase):
        pass

    hook = MockHook(HookConfig())
    name = "test_hook"
    hooks = Hooks()

    # When
    hooks._register(name, hook)

    # Then
    assert hooks._hooks_registry[name] == hook


def test_hooks_get_hook_type_returns_generic_param() -> None:
    # Given
    class TypedHook(HookBase[PreToolCallHook, HookConfig]):
        pass

    hook = TypedHook(HookConfig())
    hooks = Hooks()

    # When
    result = hooks._get_hook_type(hook)

    # Then
    assert result is PreToolCallHook


def test_hooks_get_hook_type_returns_none_for_non_generic_hook() -> None:
    # Given
    class NonGenericHook(HookBase):
        pass

    hook = NonGenericHook(HookConfig())
    hooks = Hooks()

    # When
    result = hooks._get_hook_type(hook)

    # Then
    assert result is None


def test_hooks_unload_clears_registries() -> None:
    # Given
    class MockHookForUnload(HookBase):
        pass

    hook = MockHookForUnload(HookConfig())
    hooks = Hooks()
    hooks._register("test", hook)
    # HookBase._registry already contains MockHookForUnload from subclassing

    # When
    hooks.unload()

    # Then
    assert len(HookBase._registry) == 0
    assert len(hooks._hooks_registry) == 0


def test_hook_config_default_enabled_is_true() -> None:
    # Given
    config = HookConfig()

    # When
    result = config.enabled

    # Then
    assert result is True


def test_hook_config_custom_enabled_value_is_preserved() -> None:
    # Given
    config = HookConfig(enabled=False)

    # When
    result = config.enabled

    # Then
    assert result is False


def test_hooks_load_calls_loader_with_correct_args() -> None:
    # Given
    hooks_config = {"my_hook": {"enabled": True}}
    hooks = Hooks()

    # When
    with patch("frugalbot.hooks.base.load_dynamic_modules_with_config") as mock_load:
        hooks.load(hooks_config)

        # Then
        mock_load.assert_called_once_with(
            default_package_name="frugalbot.hooks",
            base_cls=HookBase,
            config_base_cls=HookConfig,
            error_cls=HookError,
            register_fn=hooks._register,
            config_dict=hooks_config,
            module_type_name="hook",
        )


async def test_hooks_run_calls_matching_hook() -> None:
    # Given
    class MatchingHook(HookBase[PreToolCallHook, HookConfig]):
        def __init__(self, config: HookConfig) -> None:
            self.called = False
            super().__init__(config)

        async def run(self, hook_data: PreToolCallHook) -> None:
            self.called = True

    hooks = Hooks()
    matching_hook = MatchingHook(HookConfig())
    hooks._hooks_registry = {"matching": matching_hook}

    # When
    await hooks.run(PreToolCallHook(tool_name="foo", arguments={"args": "bar"}))

    # Then
    assert matching_hook.called


async def test_hooks_run_skips_non_matching_hook_type() -> None:
    # Given
    class PostToolHook(HookBase[PostToolCallHook, HookConfig]):
        def __init__(self, config: HookConfig) -> None:
            self.called = False
            super().__init__(config)

        async def run(self, hook_data: PostToolCallHook) -> None:
            self.called = True

    hooks = Hooks()
    post_hook = PostToolHook(HookConfig())
    hooks._hooks_registry = {"post": post_hook}

    # When
    await hooks.run(PreToolCallHook(tool_name="foo", arguments={"args": "bar"}))

    # Then
    assert not post_hook.called


async def test_hooks_run_skips_hook_with_no_generic_type() -> None:
    # Given
    class NonGenericHook(HookBase):
        def __init__(self, config: HookConfig) -> None:
            self.called = False
            super().__init__(config)

        async def run(self, hook_data):
            self.called = True

    hooks = Hooks()
    non_generic = NonGenericHook(HookConfig())
    hooks._hooks_registry = {"nongeneric": non_generic}

    # When
    await hooks.run(PreToolCallHook(tool_name="foo", arguments={"args": "bar"}))

    # Then
    assert not non_generic.called


async def test_hooks_run_sorts_hooks_by_priority() -> None:
    # Given
    call_order: list[str] = []

    class LowHook(HookBase[PreToolCallHook, HookConfig]):
        @property
        def priority(self) -> HookPriority:
            return HookPriority.LOW

        async def run(self, hook_data: PreToolCallHook) -> None:
            call_order.append("low")

    class HighHook(HookBase[PreToolCallHook, HookConfig]):
        @property
        def priority(self) -> HookPriority:
            return HookPriority.HIGH

        async def run(self, hook_data: PreToolCallHook) -> None:
            call_order.append("high")

    hooks = Hooks()
    hooks._hooks_registry = {
        "low": LowHook(HookConfig()),
        "high": HighHook(HookConfig()),
    }

    # When
    await hooks.run(PreToolCallHook(tool_name="foo", arguments={}))

    # Then
    assert call_order == ["high", "low"]


async def test_hooks_run_calls_multiple_matching_hooks() -> None:
    # Given
    class HookA(HookBase[PreToolCallHook, HookConfig]):
        def __init__(self, config: HookConfig) -> None:
            self.called = False
            super().__init__(config)

        async def run(self, hook_data: PreToolCallHook) -> None:
            self.called = True

    class HookB(HookBase[PreToolCallHook, HookConfig]):
        def __init__(self, config: HookConfig) -> None:
            self.called = False
            super().__init__(config)

        async def run(self, hook_data: PreToolCallHook) -> None:
            self.called = True

    hooks = Hooks()
    hook_a = HookA(HookConfig())
    hook_b = HookB(HookConfig())
    hooks._hooks_registry = {"a": hook_a, "b": hook_b}

    # When
    await hooks.run(PreToolCallHook(tool_name="foo", arguments={}))

    # Then
    assert hook_a.called and hook_b.called


async def test_hook_with_multiple_hook_types_hooks_run_calls_hook_for_each_matching_type() -> None:
    # Given
    class MultiHook(HookBase[PreToolCallHook | PostToolCallHook, HookConfig]):
        def __init__(self, config: HookConfig) -> None:
            self.called_with_pre = False
            self.called_with_post = False
            super().__init__(config)

        async def run(self, hook_data: PreToolCallHook | PostToolCallHook) -> None:
            if isinstance(hook_data, PreToolCallHook):
                self.called_with_pre = True
            elif isinstance(hook_data, PostToolCallHook):
                self.called_with_post = True

    hooks = Hooks()
    multi_hook = MultiHook(HookConfig())
    hooks._hooks_registry = {"multi": multi_hook}

    # When
    await hooks.run(PreToolCallHook(tool_name="foo", arguments={}))
    await hooks.run(PostToolCallHook(tool_name="foo", result_json="{}"))

    # Then
    assert multi_hook.called_with_pre
    assert multi_hook.called_with_post


def test_hook_with_custom_config_type_config_property_returns_custom_config_type() -> None:
    # given
    class CustomConfig(HookConfig):
        foo: bool = False

    class CustomHook(HookBase[PreToolCallHook, CustomConfig]):
        pass

    custom_hook = CustomHook(CustomConfig())

    # when
    config = custom_hook.config

    # then
    assert isinstance(config, CustomConfig)
    assert not config.foo
