import pytest
import typer
import typer._click

from frugalbot.utils.typer import get_command_from_name

# --- Helpers & Factories ---


def _make_typer_with_command(
    command_name: str = "hello",
    func_name: str = "greet",
) -> typer.Typer:
    """Build a Typer instance with a single named command."""
    app = typer.Typer()

    # We need a real function for typer to register a command.
    # Using exec to dynamically create a function with the desired name.
    func_code = f"def {func_name}(name: str = 'World'): pass"
    local_ns: dict = {}
    exec(func_code, {}, local_ns)
    func = local_ns[func_name]

    app.command(name=command_name)(func)
    return app


def _make_typer_with_multiple_commands(commands: list[str]) -> typer.Typer:
    """Build a Typer instance with multiple named commands."""
    app = typer.Typer()
    for i, cmd_name in enumerate(commands):
        func_code = f"def cmd_{i}(value: str = ''): pass"
        local_ns: dict = {}
        exec(func_code, {}, local_ns)
        func = local_ns[f"cmd_{i}"]
        app.command(name=cmd_name)(func)
    return app


def _make_typer_with_no_explicit_name(func_name: str = "hello") -> typer.Typer:
    """Build a Typer instance where the command has no explicit name (CommandInfo.name is None)."""
    app = typer.Typer()
    func_code = f"def {func_name}(name: str = 'World'): pass"
    local_ns: dict = {}
    exec(func_code, {}, local_ns)
    func = local_ns[func_name]
    app.command()(func)
    return app


# --- Tests ---


class TestGetCommandFromName:
    def test_with_matching_name_returns_click_command(self):
        # Given
        app = _make_typer_with_command(command_name="hello")

        # When
        result = get_command_from_name(app, "hello")

        # Then
        assert result is not None
        assert isinstance(result, typer._click.Command)
        assert result.name == "hello"

    def test_with_nonexistent_name_returns_none(self):
        # Given
        app = _make_typer_with_command(command_name="hello")

        # When
        result = get_command_from_name(app, "goodbye")

        # Then
        assert result is None

    def test_with_slash_prefix_strips_prefix_and_returns_command(self):
        # Given
        app = _make_typer_with_command(command_name="status")

        # When
        result = get_command_from_name(app, "/status")

        # Then
        assert result is not None
        assert result.name == "status"

    def test_with_slash_prefix_and_nonexistent_name_returns_none(self):
        # Given
        app = _make_typer_with_command(command_name="hello")

        # When
        result = get_command_from_name(app, "/unknown")

        # Then
        assert result is None

    def test_with_empty_typer_returns_none(self):
        # Given
        app = typer.Typer()

        # When
        result = get_command_from_name(app, "anything")

        # Then
        assert result is None

    def test_with_multiple_commands_returns_correct_one(self):
        # Given
        app = _make_typer_with_multiple_commands(["start", "stop", "restart"])

        # When
        result = get_command_from_name(app, "stop")

        # Then
        assert result is not None
        assert result.name == "stop"

    def test_with_multiple_commands_first_command_found(self):
        # Given
        app = _make_typer_with_multiple_commands(["alpha", "beta", "gamma"])

        # When
        result = get_command_from_name(app, "alpha")

        # Then
        assert result is not None
        assert result.name == "alpha"

    def test_with_multiple_commands_last_command_found(self):
        # Given
        app = _make_typer_with_multiple_commands(["alpha", "beta", "gamma"])

        # When
        result = get_command_from_name(app, "gamma")

        # Then
        assert result is not None
        assert result.name == "gamma"

    def test_with_no_explicit_command_name_does_not_match(self):
        # Given
        # When no explicit name is passed to @app.command(), CommandInfo.name is None.
        # The function compares command_info.name against the string "hello", so None != "hello".
        app = _make_typer_with_no_explicit_name(func_name="hello")

        # When
        result = get_command_from_name(app, "hello")

        # Then
        assert result is None

    def test_with_duplicate_slash_prefix_strips_only_one(self):
        # Given
        app = _make_typer_with_command(command_name="help")

        # When
        # "//help" -> "/help" after removeprefix("/"), which won't match "help"
        result = get_command_from_name(app, "//help")

        # Then
        assert result is None

    def test_with_empty_string_name_returns_none(self):
        # Given
        app = _make_typer_with_command(command_name="hello")

        # When
        result = get_command_from_name(app, "")

        # Then
        assert result is None

    def test_with_slash_only_name_returns_none(self):
        # Given
        app = _make_typer_with_command(command_name="hello")

        # When
        result = get_command_from_name(app, "/")

        # Then
        assert result is None

    @pytest.mark.parametrize(
        "search_name,expected_found",
        [
            ("hello", True),
            ("HELLO", False),
            ("Hello", False),
            ("hElLo", False),
        ],
    )
    def test_with_various_casings_is_case_sensitive(self, search_name: str, expected_found: bool):
        # Given
        app = _make_typer_with_command(command_name="hello")

        # When
        result = get_command_from_name(app, search_name)

        # Then
        assert (result is not None) == expected_found

    def test_returns_command_with_params_preserved(self):
        # Given
        app = _make_typer_with_command(command_name="greet", func_name="greet_func")

        # When
        result = get_command_from_name(app, "greet")

        # Then
        assert result is not None
        assert len(result.params) >= 1
        param_names = [p.name for p in result.params]
        assert "name" in param_names
