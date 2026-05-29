import pytest

from frugalbot.ui.commands.base import command, tui_typer, unload_commands


@pytest.fixture(autouse=True)
def cleanup_typer():
    """
    Ensure the global tui_typer is clean before and after every test.
    This acts as part of the 'Given' or 'Teardown' logic.
    """
    unload_commands()
    yield
    unload_commands()


def test_command_registration():
    # Given: A clean tui_typer state (handled by fixture)
    command_name = "test-cmd"

    # When: We register a new command using the custom decorator
    @command(command_name, help="Test help text")
    def dummy_callback():
        pass

    # Then: The command should be present in the registered_commands list
    assert len(tui_typer.registered_commands) == 1
    registered_cmd = tui_typer.registered_commands[0]
    assert registered_cmd.name == command_name
    assert registered_cmd.help == "Test help text"


def test_command_registration_with_kwargs():
    # Given: A clean state
    command_name = "advanced-cmd"

    # When: We register a command with extra kwargs (e.g., hidden=True)
    @command(command_name, hidden=True)
    def dummy_callback():
        pass

    # Then: The registration should reflect those kwargs
    assert len(tui_typer.registered_commands) == 1
    assert tui_typer.registered_commands[0].hidden is True


def test_unload_commands_clears_all_state():
    # Given: A tui_typer with registered commands and a callback
    @tui_typer.callback()
    def global_callback():
        pass

    @command("cmd1")
    def cmd1():
        pass

    # Sanity check to ensure state is populated
    assert len(tui_typer.registered_commands) > 0
    assert tui_typer.registered_callback is not None

    # When: We call unload_commands
    unload_commands()

    # Then: All internal registration lists and callbacks should be empty/None
    assert len(tui_typer.registered_commands) == 0
    assert len(tui_typer.registered_groups) == 0
    assert tui_typer.registered_callback is None


def test_unload_commands_with_groups():
    # Given: A tui_typer with a sub-group registered
    import typer

    sub_app = typer.Typer()
    tui_typer.add_typer(sub_app, name="sub")

    assert len(tui_typer.registered_groups) == 1

    # When: We call unload_commands
    unload_commands()

    # Then: The groups list should be cleared
    assert len(tui_typer.registered_groups) == 0
