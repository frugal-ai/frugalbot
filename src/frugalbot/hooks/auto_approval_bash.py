from __future__ import annotations

import asyncio
from collections.abc import Iterator

import tree_sitter_bash
from tree_sitter import Language, Node, Parser

from frugalbot.hooks.base import HookError

# tree-sitter-bash 0.25.x with tree-sitter 0.25.x.
_BASH_LANGUAGE = Language(tree_sitter_bash.language())
_BASH_PARSER = Parser(_BASH_LANGUAGE)
_BASH_PARSE_LOCK = asyncio.Lock()


_BASH_EXPANSION_NODE_TYPES = frozenset({
    "simple_expansion",
    "expansion",
    "command_substitution",
    "process_substitution",
    "arithmetic_expansion",
})

_BASH_COMPOUND_NODE_TYPES = frozenset({
    "compound_statement",
    "subshell",
    "if_statement",
    "for_statement",
    "while_statement",
    "function_definition",
    "case_statement",
    "test_command",
    "negated_command",
})

_BASH_COMMAND_WORD_NODE_TYPES = frozenset({
    "command_name",
    "word",
    "string",
    "raw_string",
    "concatenation",
    "variable_assignment",
})

_BASH_REDIRECT_NODE_TYPES = frozenset({
    "file_redirect",
    "heredoc_redirect",
    "herestring_redirect",
})


def _iter_tree(node: Node) -> Iterator[Node]:
    """Yield node and all descendants in source order."""
    yield node
    for child in node.children:
        yield from _iter_tree(child)


def _node_text(source: bytes, node: Node) -> str:
    """Get the exact UTF-8 source covered by node."""
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="strict")


def _tree_has_parse_error(root: Node) -> bool:
    """Tree-sitter error recovery is not acceptable at an approval boundary."""
    return root.has_error or any(node.is_error or node.is_missing for node in _iter_tree(root))


def _node_has_expansion(node: Node) -> bool:
    return any(descendant.type in _BASH_EXPANSION_NODE_TYPES for descendant in _iter_tree(node))


def _bash_word_needs_approval(source: bytes, node: Node) -> bool:
    """
    Conservatively identify shell-expanded or filesystem-dependent words.

    Raw-text checks deliberately complement AST checks. A false positive asks
    for approval; a false negative could silently approve altered arguments.
    """
    if _node_has_expansion(node):
        return True

    text = _node_text(source, node)

    # Defensive handling of all dollar/backtick forms, including future grammar
    # changes and expansion forms represented differently by the grammar.
    if "$" in text or "`" in text:
        return True

    # Tilde, pathname, and brace expansion are runtime dependent. This is
    # intentionally conservative and may flag quoted literal punctuation.
    if text.startswith("~"):
        return True

    return any(character in text for character in ("*", "?", "[", "{", "}"))


def _is_match(pattern: list[str], command: list[str]) -> bool:
    """Return True if pattern matches the leading tokens of command."""
    return len(command) >= len(pattern) and all(
        expected == "DONTCARE" or expected == actual
        for expected, actual in zip(
            pattern,
            command[: len(pattern)],
            strict=True,
        )
    )


def _is_exempt_command(
    command_words: list[str],
    exempt_commands: list[list[str]],
) -> bool:
    """Exemptions are evaluated before any MUST_APPROVE marker is inserted."""
    return any(_is_match(pattern, command_words) for pattern in exempt_commands)


def _command_from_node(
    source: bytes,
    command_node: Node,
    exempt_commands: list[list[str]],
) -> list[str]:
    """Convert one Tree-sitter command node to a policy command list."""
    words: list[str] = []
    requires_approval = False

    for child in command_node.named_children:
        if child.type in _BASH_COMMAND_WORD_NODE_TYPES:
            words.append(_node_text(source, child))

            # Assignments have shell-scoping/environment semantics even when
            # static, so they require explicit approval unless exempted.
            if child.type == "variable_assignment":
                requires_approval = True

            if _bash_word_needs_approval(source, child):
                requires_approval = True

        elif child.type in _BASH_REDIRECT_NODE_TYPES:
            # File redirects, heredocs, and here strings are side-effectful or
            # input-changing and must not be approved by ordinary allow rules.
            requires_approval = True

        else:
            # Unknown named syntax is fail-closed.
            requires_approval = True

    if not words:
        return ["MUST_APPROVE", "<empty-or-redirection-only-command>"]

    if requires_approval and not _is_exempt_command(words, exempt_commands):
        # The marker MUST be first: prefix matching then cannot let ["ls"]
        # approve a sensitive command such as ls "$HOME".
        return ["MUST_APPROVE", *words]

    return words


def _split_bash_commands_sync(
    cmd_string: str,
    exempt_commands: list[list[str]],
) -> list[list[str]]:
    """Parse Bash source and return the command lists used by the policy."""
    source = cmd_string.encode("utf-8")
    tree = _BASH_PARSER.parse(source)
    root = tree.root_node

    if _tree_has_parse_error(root):
        raise HookError("Bash parsing failed: input contains a syntax error, missing token, or parser error-recovery node")

    commands: list[list[str]] = []

    for node in _iter_tree(root):
        if node.type == "command":
            # Descending the complete tree intentionally discovers commands
            # inside $(...), backticks, and process substitutions.
            commands.append(_command_from_node(source, node, exempt_commands))
        elif node.type in _BASH_COMPOUND_NODE_TYPES:
            # The nested simple commands are also collected, but they alone
            # cannot cause a compound construct to be auto-approved.
            commands.append(["MUST_APPROVE", f"<{node.type}>"])

    if not commands and cmd_string.strip():
        commands.append(["MUST_APPROVE", "<unrecognized-bash-input>"])

    return commands


async def split_bash_commands(
    cmd_string: str,
    exempt_commands: list[list[str]],
) -> list[list[str]]:
    """Serialize access to the stateful Tree-sitter parser."""
    async with _BASH_PARSE_LOCK:
        try:
            return _split_bash_commands_sync(cmd_string, exempt_commands)
        except HookError:
            raise
        except Exception as exc:
            raise HookError(f"Bash Tree-sitter parsing failed: {exc}") from exc
