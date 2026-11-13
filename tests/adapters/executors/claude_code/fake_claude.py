"""A fake `claude -p --output-format stream-json`, as observed on Claude Code 2.1.311: an init message, the assistant's
tool calls, then one `result` message carrying the structured output. `--behave` picks what the task does,
`--record` keeps the arguments, the objective read on standard input and the folder it ran in."""

import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--behave", default="complete")
parser.add_argument("--record")
parser.add_argument("--session-id")
known, rest = parser.parse_known_args()
objective = sys.stdin.read()
if known.record:
    Path(known.record).write_text(
        json.dumps(
            {
                "arguments": sys.argv[1:],
                "objective": objective,
                "cwd": os.getcwd(),
                "api_key": os.environ.get("ANTHROPIC_API_KEY"),
            }
        )
    )


def say(message: dict[str, object]) -> None:
    print(json.dumps({**message, "session_id": known.session_id}), flush=True)


def tool(name: str, **given: object) -> None:
    say({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": name, "input": given}]}})


say({"type": "system", "subtype": "init", "cwd": os.getcwd(), "permissionMode": "dontAsk"})
print("not json\n[]", flush=True)
match known.behave:
    case "complete":
        report = Path.cwd() / "rapport.md"
        tool("Write", file_path=str(report), content="# Rapport")
        report.write_text("# Rapport")
        tool("Bash", command="ls -la", description="List files")
        tool("TodoWrite")
        tool("StructuredOutput", report="Rapport écrit.", files=[str(report)])
        output = {"report": "Rapport écrit.", "files": [str(report)]}
        say(
            {
                "type": "result",
                "subtype": "success",
                "is_error": False,
                "result": json.dumps(output),
                "structured_output": output,
            }
        )
    case "files":  # what it lists: a file, a link out of its folder, a big file, a folder, nothing
        (Path.cwd() / "ok.txt").write_text("ok")
        (Path.cwd() / "link.txt").symlink_to(Path.cwd().parent / "secret.txt")
        (Path.cwd() / "big.bin").write_bytes(b"x" * 2_000)
        (Path.cwd() / "sub").mkdir()
        listed = [str(Path.cwd() / name) for name in ("ok.txt", "link.txt", "big.bin", "sub", "missing.txt")]
        output = {"report": "Fichiers faits.", "files": listed}
        say({"type": "result", "subtype": "success", "is_error": False, "structured_output": output})
    case "odd":  # a structured output that is not the report asked for
        say({"type": "result", "subtype": "success", "is_error": False, "structured_output": {"summary": "Fini."}})
    case "huge":  # a tool result longer than any line limit, then the end
        print("x" * (64 * 1024 * 1024 + 1), flush=True)
        say({"type": "result", "subtype": "success", "is_error": False, "result": "Fini."})
    case "text":
        say({"type": "result", "subtype": "success", "is_error": False, "result": "Fini."})
    case "fail":
        say({"type": "result", "subtype": "error_max_budget_usd", "is_error": True})
    case "crash":
        print("Invalid API key · Please run /login", file=sys.stderr, flush=True)
        sys.exit(1)
    case "stubborn":
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        time.sleep(60)
    case _:  # slow
        time.sleep(60)
