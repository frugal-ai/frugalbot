To reimplement the `pytest` command filter module in another language, you need to replicate three main components: the **Command Wrapper**, the **State-Based Parser**, and the **Summary Generator**.

Below is the exhaustive technical specification of the module.

---

### 1. Command Wrapper (Execution Logic)
The module does not just run `pytest`; it forces specific flags to ensure the output is predictable and concise for the parser.

**Command Resolution:**
1. Try executing `pytest` directly.
2. If not found, fallback to `python -m pytest`.

**Forced Flags (Injected if not present in user args):**
- `--tb=short`: Forces short tracebacks (essential for the failure parser).
- `-q`: Quiet mode to remove verbose progress indicators.
- `-rxX`: Ensures the "short test summary" includes:
    - `x`: Expected failures (`XFAIL`)
    - `X`: Unexpected passes (`XPASS`)

**Execution Flow:**
- Construct the command: `[pytest/python -m pytest] + [forced flags] + [user arguments]`.
- Capture `stdout` for filtering.

---

### 2. State-Based Parser (Processing Logic)
The parser reads the output line-by-line using a state machine to categorize data.

#### A. Parse States
- `Header`: Initial state.
- `TestProgress`: Capturing which files are being tested.
- `Failures`: Capturing detailed traceback blocks.
- `Summary`: Capturing the final tally and short summary list.

#### B. State Transitions & Line Identification
| Trigger (Line contains...) | New State | Action |
| :--- | :--- | :--- |
| `===` AND `"test session starts"` | `Header` | Reset |
| `===` AND `"FAILURES"` | `Failures` | Start collecting tracebacks |
| `===` AND `"short test summary"` | `Summary` | Transition to summary list |
| `===` AND (`"passed"` OR `"failed"` OR `"skipped"`) | `Any` | **Capture as `summary_line`** |
| No `===` AND (`" passed"` OR `" failed"` OR `" skipped"`) AND `" in "` | `Any` | **Capture as `summary_line`** (Quiet mode fallback) |

#### C. Data Collection per State
- **`Header`**: If a line starts with `"collected"`, move to `TestProgress`.
- **`TestProgress`**: Collect lines that contain `.py` or `%]` (these are the files being tested).
- **`Failures`**: 
    - A line starting with `___` indicates a new test failure block.
    - Collect all lines until the next `___` or a state change.
- **`Summary`**: 
    - Lines starting with `FAILED` or `ERROR` $\rightarrow$ Add to `failures` list.
    - Lines starting with `XFAIL` or `XPASS` $\rightarrow$ Add to `xfail_lines` list.

---

### 3. Summary Generator (Formatting Logic)
Once parsing is complete, the module transforms the collected data into a compact report.

#### A. Tally Parsing (`parse_summary_line`)
Extract numbers from the `summary_line` (e.g., `"4 passed, 1 failed, 2 xfailed in 0.5s"`).
- Split by comma $\rightarrow$ Split by whitespace.
- Match the number preceding the keywords in this priority: `xpassed` $\rightarrow$ `xfailed` $\rightarrow$ `passed` $\rightarrow$ `failed` $\rightarrow$ `skipped`.

#### B. Output Construction
1. **Empty Case**: If all counts are 0 $\rightarrow$ `"Pytest: No tests collected"`.
2. **All Pass Case**: If only `passed > 0` and no skipped/xfail/xpass $\rightarrow$ `"Pytest: X passed"`.
3. **Complex Case**:
    - **Top Line**: `"Pytest: X passed, Y failed, Z skipped, W xfailed, V xpassed"` (only include non-zero counts).
    - **Separator**: `═══════════════════════════════════════`
    - **Expected Failures Section**: 
        - Header: `"Expected-failure outcomes:"`
        - List lines from `xfail_lines`.
        - **Limit**: Max 10 lines. Truncate each line to 120 chars.
        - If exceeded: Add `… +N more`.
    - **Failures Section**:
        - Header: `"Failures:"`
        - **Limit**: Max 10 failures.
        - **For each failure**:
            - **Identification**:
                - If line starts with `___`, extract the text between underscores as the test name.
                - If line starts with `FAILED`, split by `" - "`. Part 1 (minus "FAILED ") is the test name; Part 2 is the error message (truncated to 100 chars).
            - **Traceback Extraction**: Scan the block for "relevant" lines. A line is relevant if it:
                - Starts with `>` or `E`
                - Contains `"assert"` or `"error"` (case-insensitive)
                - Contains `.py:`
            - **Limit**: Take only the first 3 relevant lines. Truncate each to 100 chars.
        - If exceeded: Add `… +N more failures`.

---

### Summary of Constraints for Implementation
- **Max Failures Displayed**: 10
- **Max XFAILs Displayed**: 10
- **Max Relevant Traceback Lines per Failure**: 3
- **Line Truncation**: 100 chars (failures), 120 chars (xfails)
- **Critical Regex/Patterns**: 
    - `___` (Failure block start)
    - `===` (Section delimiter)
    - `FAILED`/`ERROR`/`XFAIL`/`XPASS` (Summary status)