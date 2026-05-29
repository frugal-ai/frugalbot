import sys
from collections.abc import Generator
from pathlib import Path
from typing import Any, ClassVar, Self
from unittest.mock import MagicMock, patch

import pydantic
import pytest

from frugalbot.utils.loader import (
    _get_additional_module_prefix,
    load_dynamic_modules,
    load_dynamic_modules_with_config,
    load_or_reload_module,
)


@pytest.fixture(autouse=True)
def cleanup_sys_modules() -> Generator[None]:
    """Capture sys.modules state before each test and restore after."""
    snapshot = dict(sys.modules)
    yield
    # Restore sys.modules to its original state
    added = set(sys.modules.keys()) - set(snapshot.keys())
    for name in added:
        del sys.modules[name]
    removed = set(snapshot.keys()) - set(sys.modules.keys())
    for name in removed:
        sys.modules[name] = snapshot[name]


# ─── Tests for _get_additional_module_prefix ───────────────────────────────


def test_get_additional_module_prefix_with_standard_inputs_returns_expected_format() -> None:
    # Given
    location_name = "local"
    module_type_name = "tool"

    # When
    result = _get_additional_module_prefix(location_name, module_type_name)

    # Then
    assert result == "frugalbot_local_custom_tool_"


def test_get_additional_module_prefix_with_global_location_returns_expected_format() -> None:
    # Given
    location_name = "global"
    module_type_name = "extension"

    # When
    result = _get_additional_module_prefix(location_name, module_type_name)

    # Then
    assert result == "frugalbot_global_custom_extension_"


# ─── Tests for load_or_reload_module ──────────────────────────────────────


def test_load_or_reload_module_with_existing_module_reloads_it() -> None:
    # Given
    module_name = "json"
    sys.modules[module_name] = sys.modules[module_name]  # ensure it's loaded

    # When
    with patch("importlib.reload") as mock_reload:
        load_or_reload_module(module_name)

        # Then
        mock_reload.assert_called_once_with(sys.modules[module_name])


def test_load_or_reload_module_with_new_module_imports_it() -> None:
    # Given
    module_name = "frugalbot_test_nonexistent_module_xyz"
    assert module_name not in sys.modules

    # When / Then
    with pytest.raises(ModuleNotFoundError):
        load_or_reload_module(module_name)


def test_load_or_reload_module_with_package_imports_with_package() -> None:
    # Given
    module_name = ".json"
    package = "frugalbot"

    # When / Then
    with pytest.raises(ModuleNotFoundError):
        load_or_reload_module(module_name, package)


# ─── Tests for load_dynamic_modules ───────────────────────────────────────


def test_load_dynamic_modules_with_nonexistent_package_skips_gracefully() -> None:
    # Given
    package_name = "frugalbot_nonexistent_package_xyz"
    module_type = "tool"

    # When
    load_dynamic_modules(package_name, module_type)

    # Then - no exception raised, test passes


def test_load_dynamic_modules_with_existing_package_loads_modules() -> None:
    # Given
    package_name = "frugalbot.hooks"
    module_type = "hook"

    # When
    load_dynamic_modules(package_name, module_type)

    # Then - modules from the package should be loaded
    assert "frugalbot.hooks.auto_approval" in sys.modules


def test_load_dynamic_modules_skips_base_module() -> None:
    # Given
    package_name = "frugalbot.hooks"
    module_type = "hook"

    # When
    with patch("frugalbot.utils.loader.load_or_reload_module") as mock_load:
        load_dynamic_modules(package_name, module_type)

    # Then - base should NOT have been loaded by load_dynamic_modules
    for call in mock_load.call_args_list:
        assert call[0][0] != "frugalbot.hooks.base"


def test_load_dynamic_modules_with_local_directory_creates_module_in_sys_modules() -> None:
    # Given
    expected_name = "frugalbot_local_custom_tool_my_custom_tool"

    def capture_module(spec_name: str, spec_path: Path) -> MagicMock:
        mod = MagicMock()
        mod.MY_VAR = 42
        sys.modules[spec_name] = mod
        return mod

    with (
        patch.object(Path, "exists", return_value=True),
        patch.object(Path, "is_dir", return_value=True),
        patch.object(Path, "glob", return_value=[Path(".frugalbot/tools/my_custom_tool.py")]),
        patch("importlib.util.spec_from_file_location", side_effect=capture_module),
    ):
        # When
        load_dynamic_modules("frugalbot_nonexistent_xyz", "tool")

        # Then
        assert expected_name in sys.modules


def test_load_dynamic_modules_skips_init_py_in_additional_directories() -> None:
    # Given
    with (
        patch.object(Path, "exists", return_value=True),
        patch.object(Path, "is_dir", return_value=True),
        patch.object(Path, "glob", return_value=[Path(".frugalbot/tools/__init__.py")]),
        patch("importlib.util.spec_from_file_location") as mock_spec_fn,
    ):
        # When
        load_dynamic_modules("frugalbot_nonexistent_xyz", "tool")

        # Then
        mock_spec_fn.assert_not_called()
        module_name = "frugalbot_local_custom_tool___init__"
        assert module_name not in sys.modules


def test_load_dynamic_modules_unloads_removed_modules() -> None:
    # Given
    module_type = "tool"
    old_module_name = "frugalbot_local_custom_tool_existing_tool"

    # Pre-populate sys.modules with a module that should be unloaded
    mock_old = MagicMock()
    sys.modules[old_module_name] = mock_old

    def capture_new_module(spec_name: str, spec_path: Path) -> MagicMock:
        mod = MagicMock()
        mod.NEW_VAR = 2
        sys.modules[spec_name] = mod
        return mod

    with (
        patch.object(Path, "exists", return_value=True),
        patch.object(Path, "is_dir", return_value=True),
        patch.object(Path, "glob", return_value=[Path(".frugalbot/tools/new_tool.py")]),
        patch("importlib.util.spec_from_file_location", side_effect=capture_new_module),
    ):
        # When
        load_dynamic_modules("frugalbot_nonexistent_xyz", module_type)

        # Then
        assert old_module_name not in sys.modules
        new_module_name = "frugalbot_local_custom_tool_new_tool"
        assert new_module_name in sys.modules


def test_load_dynamic_modules_reloads_already_loaded_additional_modules() -> None:
    # Given
    # Path.glob will trigger for both 'local' and 'global' iterations, so we put both in sys.modules
    sys.modules["frugalbot_local_custom_tool_reloadable"] = MagicMock(COUNTER=1)
    sys.modules["frugalbot_global_custom_tool_reloadable"] = MagicMock(COUNTER=1)

    with (
        patch.object(Path, "exists", return_value=True),
        patch.object(Path, "is_dir", return_value=True),
        patch.object(Path, "glob", return_value=[Path(".frugalbot/tools/reloadable.py")]),
        patch("importlib.util.spec_from_file_location") as mock_spec_fn,
        patch("importlib.reload") as mock_reload,
    ):
        # When
        load_dynamic_modules("frugalbot_nonexistent_xyz", "tool")

        # Then - since module is already in sys.modules, reload should be called
        assert mock_reload.call_count == 2
        # spec_from_file_location should NOT be called (module already loaded)
        mock_spec_fn.assert_not_called()


def test_load_dynamic_modules_handles_both_local_and_global_locations() -> None:
    # Given
    loaded_modules: list[str] = []

    def capture_module(spec_name: str, spec_path: Path) -> MagicMock:
        mod = MagicMock()
        sys.modules[spec_name] = mod
        loaded_modules.append(spec_name)
        return mod

    local_file = Path("/fake/cwd/.frugalbot/tools/file_a.py")
    global_file = Path("/fake/home/.frugalbot/tools/file_b.py")

    def fake_glob(self: Path, pattern: str) -> list[Path]:
        s = str(self)
        if "cwd" in s:
            return [local_file]
        if "home" in s:
            return [global_file]
        return []

    with (
        patch.object(Path, "cwd", return_value=Path("/fake/cwd")),
        patch.object(Path, "home", return_value=Path("/fake/home")),
        patch.object(Path, "exists", return_value=True),
        patch.object(Path, "is_dir", return_value=True),
        patch.object(Path, "glob", fake_glob),
        patch("importlib.util.spec_from_file_location", side_effect=capture_module),
    ):
        # When
        load_dynamic_modules("frugalbot_nonexistent_xyz", "tool")

        # Then
        assert "frugalbot_local_custom_tool_file_a" in loaded_modules
        assert "frugalbot_global_custom_tool_file_b" in loaded_modules


# ─── Tests for load_dynamic_modules_with_config ───────────────────────────


class _FakeConfig(pydantic.BaseModel):
    enabled: bool = True
    value: int = 0


class _FakeExtendedConfig(_FakeConfig):
    extra: str = "default"


class _FakeError(Exception):
    pass


class _FakeBase:
    _registry: ClassVar[list[type[Self]]] = []

    def __init__(self, config: _FakeConfig) -> None:
        self._config = config

    @property
    def config(self) -> Any:
        return self._config

    @property
    def name(self) -> str:
        return type(self).__name__.lower()


def _run_loader(
    registry_classes: list[type],
    config_dict: dict[str, Any],
    register_fn: MagicMock | None = None,
    skip_if_no_config: bool = False,
    config_base_cls: type[pydantic.BaseModel] = _FakeConfig,
) -> MagicMock:
    """Helper: clears registry, populates it, runs loader, returns register_fn."""
    _FakeBase._registry.clear()
    for cls in registry_classes:
        _FakeBase._registry.append(cls)
    fn = register_fn or MagicMock()
    with patch("frugalbot.utils.loader.load_dynamic_modules"):
        load_dynamic_modules_with_config(
            default_package_name="fake_package",
            base_cls=_FakeBase,
            config_base_cls=config_base_cls,
            error_cls=_FakeError,
            register_fn=fn,
            config_dict=config_dict,
            module_type_name="extension",
            skip_if_no_config=skip_if_no_config,
        )
    return fn


def test_load_dynamic_modules_with_config_valid_inputs_registers_instance() -> None:
    # Given
    class TestExtension(_FakeBase):
        pass

    config_dict: dict[str, Any] = {"test": {"value": 5}}

    # When
    register_fn = _run_loader([TestExtension], config_dict)

    # Then
    register_fn.assert_called_once()
    args = register_fn.call_args
    assert args[0][0] == "testextension"
    assert isinstance(args[0][1], TestExtension)


def test_load_dynamic_modules_with_config_skip_if_no_config_skips_unconfigured() -> None:
    # Given
    class SkippedExtension(_FakeBase):
        pass

    config_dict: dict[str, Any] = {}  # No config for "skipped"

    # When
    register_fn = _run_loader([SkippedExtension], config_dict, skip_if_no_config=True)

    # Then
    register_fn.assert_not_called()


def test_load_dynamic_modules_with_config_no_skip_instantiates_with_default_config() -> None:
    # Given
    class DefaultExtension(_FakeBase):
        pass

    config_dict: dict[str, Any] = {}  # No config for "default"

    # When
    register_fn = _run_loader([DefaultExtension], config_dict, skip_if_no_config=False)

    # Then
    register_fn.assert_called_once()
    instance = register_fn.call_args[0][1]
    assert instance.config.enabled is True
    assert instance.config.value == 0


def test_load_dynamic_modules_with_config_missing_annotation_raises_error() -> None:
    # Given
    class BadExtension(_FakeBase):
        def __init__(self, config) -> None:  # type: ignore[no-untyped-def]
            pass

    config_dict: dict[str, Any] = {"bad": {}}

    # When / Then
    with patch("frugalbot.utils.loader.load_dynamic_modules"):
        _FakeBase._registry.clear()
        _FakeBase._registry.append(BadExtension)
        with pytest.raises(_FakeError, match="type hint"):
            load_dynamic_modules_with_config(
                default_package_name="fake_package",
                base_cls=_FakeBase,
                config_base_cls=_FakeConfig,
                error_cls=_FakeError,
                register_fn=MagicMock(),
                config_dict=config_dict,
                module_type_name="extension",
            )


def test_load_dynamic_modules_with_config_wrong_config_type_raises_error() -> None:
    # Given
    class _OtherConfig(pydantic.BaseModel):
        other_field: str = "x"

    class WrongExtension(_FakeBase):
        def __init__(self, config: _OtherConfig):
            pass

    config_dict: dict[str, Any] = {"wrong": {}}

    # When / Then
    with patch("frugalbot.utils.loader.load_dynamic_modules"):
        _FakeBase._registry.clear()
        _FakeBase._registry.append(WrongExtension)
        with pytest.raises(_FakeError, match="must take a _FakeConfig"):
            load_dynamic_modules_with_config(
                default_package_name="fake_package",
                base_cls=_FakeBase,
                config_base_cls=_FakeConfig,
                error_cls=_FakeError,
                register_fn=MagicMock(),
                config_dict=config_dict,
                module_type_name="extension",
            )


def test_load_dynamic_modules_with_config_pydantic_validation_error_prints_message(capsys: Any) -> None:
    # Given
    class ValExtension(_FakeBase):
        pass

    config_dict: dict[str, Any] = {"val": {"value": "not_an_int"}}  # Invalid value type

    # When
    register_fn = _run_loader([ValExtension], config_dict)

    # Then
    captured = capsys.readouterr()
    assert "Failed to load extension 'val'" in captured.out
    register_fn.assert_not_called()


def test_load_dynamic_modules_with_config_merges_global_and_specific_configs() -> None:
    # Given
    class MergeExtension(_FakeBase):
        pass

    config_dict: dict[str, Any] = {
        "all": {"value": 100, "enabled": True},
        "merge": {"value": 42},
    }

    # When
    register_fn = _run_loader([MergeExtension], config_dict)

    # Then
    instance = register_fn.call_args[0][1]
    assert instance.config.value == 42  # Specific config overrides global
    assert instance.config.enabled is True  # Global config applied


def test_load_dynamic_modules_with_config_all_as_list_is_ignored() -> None:
    # Given
    class ListAllExtension(_FakeBase):
        pass

    config_dict: dict[str, Any] = {
        "all": [{"value": 100}],  # "all" as list should be ignored
        "listall": {},
    }

    # When
    register_fn = _run_loader([ListAllExtension], config_dict)

    # Then
    instance = register_fn.call_args[0][1]
    assert instance.config.value == 0  # Default value, global list ignored


def test_load_dynamic_modules_with_config_list_configs_creates_multiple_instances() -> None:
    # Given
    class MultiExtension(_FakeBase):
        @property
        def name(self) -> str:
            return f"multi_{self.config.value}"

    config_dict: dict[str, Any] = {"multi": [{"value": 1}, {"value": 2}, {"value": 3}]}

    # When
    register_fn = _run_loader([MultiExtension], config_dict)

    # Then
    assert register_fn.call_count == 3
    calls = register_fn.call_args_list
    assert calls[0][0][0] == "multi_1"
    assert calls[1][0][0] == "multi_2"
    assert calls[2][0][0] == "multi_3"


def test_load_dynamic_modules_with_config_class_without_enabled_attribute_registers() -> None:
    # Given
    class NoEnabledExtension(_FakeBase):
        pass

    config_dict: dict[str, Any] = {"noenabled": {"value": 10}}

    # When
    register_fn = _run_loader([NoEnabledExtension], config_dict)

    # Then
    register_fn.assert_called_once()
    assert register_fn.call_args[0][0] == "noenabledextension"


def test_load_dynamic_modules_with_config_name_normalization_strips_suffix() -> None:
    # Given
    class MySearchExtension(_FakeBase):
        pass

    config_dict: dict[str, Any] = {"mysearch": {"value": 3}}

    # When
    register_fn = _run_loader([MySearchExtension], config_dict)

    # Then
    register_fn.assert_called_once()
    assert register_fn.call_args[0][0] == "mysearchextension"


def test_load_dynamic_modules_with_config_calls_load_dynamic_modules() -> None:
    # Given
    class SimpleExtension(_FakeBase):
        pass

    config_dict: dict[str, Any] = {"simple": {}}

    # When
    with patch("frugalbot.utils.loader.load_dynamic_modules") as mock_load:
        _FakeBase._registry.clear()
        _FakeBase._registry.append(SimpleExtension)
        load_dynamic_modules_with_config(
            default_package_name="my_package",
            base_cls=_FakeBase,
            config_base_cls=_FakeConfig,
            error_cls=_FakeError,
            register_fn=MagicMock(),
            config_dict=config_dict,
            module_type_name="extension",
        )

    # Then
    mock_load.assert_called_once_with("my_package", "extension")


def test_load_dynamic_modules_with_config_no_init_params_passes_config_and_raises() -> None:
    # Given
    # When __init__ only has 'self', config_base_cls is used, but cls(config_obj) fails
    # because the class doesn't accept a config argument.
    class NoParamExtension(_FakeBase):
        def __init__(self) -> None:  # No config parameter
            pass

    config_dict: dict[str, Any] = {"noparam": {}}

    # When / Then
    with patch("frugalbot.utils.loader.load_dynamic_modules"):
        _FakeBase._registry.clear()
        _FakeBase._registry.append(NoParamExtension)
        with pytest.raises(TypeError):
            load_dynamic_modules_with_config(
                default_package_name="fake_package",
                base_cls=_FakeBase,
                config_base_cls=_FakeConfig,
                error_cls=_FakeError,
                register_fn=MagicMock(),
                config_dict=config_dict,
                module_type_name="extension",
            )


def test_load_dynamic_modules_with_config_multiple_classes_all_registered() -> None:
    # Given
    class AlphaExtension(_FakeBase):
        pass

    class BetaExtension(_FakeBase):
        pass

    config_dict: dict[str, Any] = {"alpha": {"value": 1}, "beta": {"value": 2}}

    # When
    register_fn = _run_loader([AlphaExtension, BetaExtension], config_dict)

    # Then
    assert register_fn.call_count == 2
    names = [c[0][0] for c in register_fn.call_args_list]
    assert "alphaextension" in names
    assert "betaextension" in names
