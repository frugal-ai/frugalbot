from frugalbot.utils.json import json_to_readable_yaml


def test_json_to_readable_yaml():
    s = (
        '{"returncode":1,"output":"============================= test session starts =============================\\r\\n'
        "platform win32 -- Python 3.14.2, pytest-9.0.3, pluggy-1.6.0\\r\\n"
        "rootdir: C:\\\\repo\\\\github\\\\frugal-ai\\\\frugalbot\\r\\n"
        "configfile: pyproject.toml\\r\\n"
        "plugins: anyio-4.13.0, asyncio-1.3.0\\r\\n"
        'asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function\\r\\n"}'
    )
    y = json_to_readable_yaml(s)
    lines = y.splitlines()
    output_line = ""
    for line in lines:
        if line.lstrip().startswith("output:"):
            output_line = line
            break
    assert output_line == "output: |"
    assert "\\r" not in output_line
