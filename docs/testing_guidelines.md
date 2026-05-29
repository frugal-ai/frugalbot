# Testing Guidelines

## Philosophy
Tests must be **Trustworthy, Readable, and Maintainable.**
- **Unit of Work:** Sum of actions from an **Entry Point** (public method) to an **Exit Point** (observable result).
- **Isolation:** Unless it's impossible, tests run in memory only. No filesystem, database, or network. Use pyfakefs as a replacement for the filesystem.
- **Do not repeat yourself:** Test code should never duplicate code. If code is repeated, move it into a fixture or some other appropriate re-usable unit of code.
- **Test edge cases**: Include tests for normal input and edge cases. Make sure the tested code fails fast on invalid input.

## Structure: Given-When-Then (GWT)
Every test has three sections, separated by blank lines with labeled comments.
- **Given:** Setup/context — initialize objects and configure Stubs (data providers).
- **When:** Exactly one call to the public entry point.
- **Then:** Assert exactly one exit point — return value, state change, or Mock interaction.

```python
def test_calculate_total_with_valid_items_returns_sum():
    # Given
    calc = PriceCalculator()
    items = [Item(price=10), Item(price=20)]

    # When
    result = calc.calculate_total(items)

    # Then
    assert result == 30
```

## Naming
Template: `test_[UnitOfWork]_[StateUnderTest]_[ExpectedBehavior]`
- **UnitOfWork:** The method/action. **StateUnderTest:** The Given context (e.g., `EmptyCart`). **ExpectedBehavior:** The Then outcome (e.g., `ReturnsZero`).
- Example: `test_process_payment_with_expired_card_logs_error`

## Exit Points (assert exactly one per test)
1. **Return Value:** What the function returns.
2. **State Change:** Observable state mutation (e.g., `user.is_active == True`).
3. **Third-Party Interaction:** Dependency was called (e.g., `mock_email.send.assert_called_once()`).

## Fakes: Stubs vs. Mocks
- **Stubs (Given):** Provide data *to* the system. Never assert against them. (e.g., `mock_db.get_user.return_value = 'Alice'`)
- **Mocks (Then):** Verify data coming *out* of the system. Assert they were called. (e.g., `mock_email.send.assert_called_once()`)
- Use only **one Mock assertion** per test.

## Maintainability Rules
- **No logic in tests:** No `if`, `for`, `while`, or `try/except` (unless testing the exception).
- **No over-specification:** Don't mock private methods or internal details — only Exit Point boundaries.
- **One When call per test:** Multi-method setup belongs in Given.
- **Literal values:** Use clear literals in assertions, not complex calculations.

## Python Implementation
- **Framework:** `pytest` with standard `assert` statements.
- **Exceptions:** Use `with pytest.raises(ErrorType):` in the When block.
- **Fixtures:** Use `pytest.fixture` for repetitive Given setups; keep the specific state visible inside the test.
- **Parametrization:** Use `pytest.mark.parametrize` to exercise multiple inputs for the same test scenario.

## Additional Instructions
1. **Identify** the entry point and target exit point before writing.
2. **Structure** using `# Given`, `# When`, `# Then` comments.
3. **Name** strictly as `test_Unit_State_Behavior`.
4. **Stubs in Given, Mocks in Then** — no exceptions.
5. **Refactor** Given sections longer than 5–7 lines into a helper or fixture.

## Test Coverage
- Tests must cover 100% of the code being tested.
- To check the coverage, run `uv run pytest` with the `--cov` and `--cov-report=term-missing` options. For example, to check the coverage of test_agent.py, run `uv run pytest --cov=frugalbot.agent --cov-report=term-missing .\tests\frugalbot\test_agent.py`.
