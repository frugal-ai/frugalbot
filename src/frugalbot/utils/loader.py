import importlib
import importlib.util
import inspect
import pkgutil
import sys
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, Protocol, TypeVar, runtime_checkable

import pydantic

from frugalbot.utils.typing import get_generic_type_of_base_class


@runtime_checkable
class SupportsRegistry(Protocol):
    @property
    def _registry(self) -> Iterable[type]: ...


@runtime_checkable
class SupportsName(Protocol):
    @property
    def name(self) -> str: ...


def _get_additional_module_prefix(location_name: str, module_type_name: str) -> str:
    return f"frugalbot_{location_name}_custom_{module_type_name}_"


def load_or_reload_module(module_name: str, package: str | None = None):
    if module_name in sys.modules:
        return importlib.reload(sys.modules[module_name])
    return importlib.import_module(module_name, package)


def load_dynamic_modules(
    default_package_name: str,
    module_type_name: str,
):
    try:
        pkg = importlib.import_module(default_package_name)
        for _, name, is_pkg in pkgutil.iter_modules(pkg.__path__):
            if is_pkg or name == "base":
                continue
            full_name = f"{default_package_name}.{name}"
            load_or_reload_module(full_name)
    except ImportError:
        # If the default package doesn't exist, we skip it and look for local ones
        pass

    # find additional modules and save them
    location = Path(f".frugalbot/{module_type_name}s")
    additional_locations: dict[str, Path] = {"local": Path.cwd() / location, "global": Path.home() / location}
    additional_modules: list[tuple[Path, str]] = []
    for location_name, local_dir in additional_locations.items():
        if local_dir.exists() and local_dir.is_dir():
            for file_path in local_dir.glob("*.py"):
                if file_path.name == "__init__.py":
                    continue
                additional_modules.append((file_path, f"{_get_additional_module_prefix(location_name, module_type_name)}{file_path.stem}"))

    # unload additional modules that are no longer present
    additional_module_names = set(name for _, name in additional_modules)
    for location_name in additional_locations.keys():
        additional_module_prefix = _get_additional_module_prefix(location_name, module_type_name)
        modules_to_unload = [name for name in sys.modules if name not in additional_module_names and name.startswith(additional_module_prefix)]
        for name in modules_to_unload:
            del sys.modules[name]

    # load/reload additional modules
    for file_path, module_name in additional_modules:
        if module_name in sys.modules:
            load_or_reload_module(module_name)
            continue
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)


def load_dynamic_modules_with_config(
    default_package_name: str,
    base_cls: type,
    config_base_cls: type[Any],
    error_cls: type[Exception],
    register_fn: Callable[[str, Any], None],
    config_dict: dict[str, list[dict[str, Any]]] | dict[str, Any],
    module_type_name: str,
    skip_if_no_config: bool = False,
) -> None:
    """Generic loader for dynamic modules (tools, hooks, etc.)."""
    load_dynamic_modules(default_package_name, module_type_name)

    for cls in base_cls._registry:
        # Normalize name (e.g., 'SearchTool' -> 'search')
        component_name = cls.__name__.lower()
        if component_name.endswith(module_type_name):
            component_name = component_name[: -len(module_type_name)]

        # skip if skip is enabled and there's no config
        if skip_if_no_config and component_name not in config_dict:
            continue

        # Inspect __init__ for config type hint
        sig = inspect.signature(cls.__init__)
        params = list(sig.parameters.values())
        config_param = params[1] if len(params) > 1 else None

        config_cls = config_base_cls
        if config_param:
            if config_param.annotation is inspect.Parameter.empty:
                raise error_cls(
                    f"{module_type_name.capitalize()} class '{cls.__name__}' __init__ must specify a type hint for its second parameter and the type hint must be a {config_base_cls.__name__} or subclass."
                )
            if isinstance(config_param.annotation, TypeVar):
                config_cls = get_generic_type_of_base_class(cls, base_cls, 1)
            else:
                config_cls = config_param.annotation

        if config_cls is None or not issubclass(config_cls, config_base_cls):
            raise error_cls(
                f"{module_type_name.capitalize()} class '{cls.__name__}' __init__ must take a {config_base_cls.__name__} (or subclass) as its second parameter "
                f"(currently taking a '{config_cls.__name__ if config_cls else 'None'}')"
            )
        if not issubclass(config_base_cls, pydantic.BaseModel):
            raise error_cls(f"{config_base_cls.__name__} must be a subclass of pydantic.BaseModel")

        try:
            raw_configs: list[dict[str, Any]] | dict[str, Any] = config_dict.get(component_name, {})
            raw_configs_list = raw_configs if isinstance(raw_configs, list) else [raw_configs]

            for raw_config in raw_configs_list:
                config_obj = config_cls.model_validate(raw_config, extra="ignore")
                instance = cls(config_obj)
                if not isinstance(instance, SupportsName):
                    raise ValueError(f"Class {type(instance)} must have a 'name' property")
                register_fn(instance.name, instance)

        except pydantic.ValidationError as e:
            print(f"Failed to load {module_type_name} '{component_name}': {e}")
