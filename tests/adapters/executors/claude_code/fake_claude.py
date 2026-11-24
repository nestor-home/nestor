"""A fake `claude -p --input-format stream-json --output-format stream-json`, as observed on Claude Code 2.1.323: it
reads user messages on standard input, one JSON line each; writes an init message, the assistant's tool calls, then a
`result` message carrying the structured output; and exits only once its input is closed. `--behave` picks what the
turn does, `--record` keeps the arguments, the instruction it was given, the folder it ran in and what it found there,
the MCP servers it was given (`--mcp-config`), with that file's permissions."""

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
parser.add_argument("--resume")
parser.add_argument("--mcp-config")
known, rest = parser.parse_known_args()
session = known.resume or known.session_id


def heard() -> str | None:
    """The next user message, `None` once the input is closed."""
    line = sys.stdin.readline()
    return json.loads(line)["message"]["content"] if line else None


instruction = heard()
if known.record:
    Path(known.record).write_text(
        json.dumps(
            {
                "arguments": sys.argv[1:],
                "instruction": instruction,
                "cwd": os.getcwd(),
                "found": {name: Path(name).read_bytes().decode() for name in sorted(os.listdir())},
                "api_key": os.environ.get("ANTHROPIC_API_KEY"),
                "mcp": json.loads(Path(known.mcp_config).read_text()) if known.mcp_config else None,
                "mcp_mode": Path(known.mcp_config).stat().st_mode & 0o777 if known.mcp_config else None,
            }
        )
    )


def say(message: dict[str, object]) -> None:
    print(json.dumps({**message, "session_id": session}), flush=True)


def tool(name: str, **given: object) -> None:
    say({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": name, "input": given}]}})


def report(text: str, files: list[str] | None = None, question: str = "") -> None:
    output = {"report": text, "files": files or [], "question": question}
    say(
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": json.dumps(output),
            "structured_output": output,
        }
    )


say({"type": "system", "subtype": "init", "cwd": os.getcwd(), "permissionMode": "dontAsk"})
print("not json\n[]", flush=True)
match known.behave:
    case "complete":
        written = Path.cwd() / "rapport.md"
        tool("Write", file_path=str(written), content="# Rapport")
        written.write_text("# Rapport")
        tool("Bash", command="curl -H 'Authorization: Bearer sk-secret' https://api.example", description="Call it")
        tool("TodoWrite")
        tool("StructuredOutput", report="Rapport écrit.", files=[str(written)], question="")
        report("Rapport écrit.", [str(written)])
    case "ask":
        report("J'ai trouvé deux devis.", question="Lequel garder ?")
    case "steered":  # works until an instruction comes, then reports it
        tool("Read", file_path=str(Path.cwd() / "devis.pdf"))
        report(f"Fait, avec : {heard()}")
    case "files":  # what it lists: a file, a link out of its folder, a big file, a folder, nothing
        (Path.cwd() / "ok.txt").write_text("ok")
        (Path.cwd() / "link.txt").symlink_to(Path.cwd().parent / "secret.txt")
        (Path.cwd() / "big.bin").write_bytes(b"x" * 2_000)
        (Path.cwd() / "sub").mkdir()
        listed = [str(Path.cwd() / name) for name in ("ok.txt", "link.txt", "big.bin", "sub", "missing.txt")]
        report("Fichiers faits.", listed)
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
    case _:  # slow: takes instructions, never ends on its own
        time.sleep(60)
while heard() is not None:  # like Claude Code, it waits for more until its input is closed
    pass
