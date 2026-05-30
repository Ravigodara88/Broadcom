#!/usr/bin/env python3
"""Interactive chat REPL for SchemaIntelligenceAgent."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from agent.agent import SchemaIntelligenceAgent

HELP = """
Commands:
  /schema   – paste or load a schema JSON, then analyse it for PII
  /load     – load schema from a file path
  /mask     – generate masking config from last schema analysis result
  /help     – show this message
  /quit     – exit

Or just type any question about masking, GDPR, PII functions, etc.
"""

EXAMPLES = """
Example questions you can ask:
  • What does DATE_SHIFT do?
  • How does CREDIT_CARD_MASK work?
  • How do I comply with GDPR when masking customer data?
  • Is column ssn_number in table EMPLOYEES PII?
  • /schema   (then paste schema JSON)
"""


def load_schema_interactive() -> list[dict] | None:
    print("Paste your schema JSON (a list of column objects), then press Enter twice:")
    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line == "" and lines:
            break
        lines.append(line)
    raw = "\n".join(lines).strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            data = [data]
        print(f"  Loaded {len(data)} column(s).")
        return data
    except json.JSONDecodeError as e:
        print(f"  Invalid JSON: {e}")
        return None


def load_schema_from_file(path_str: str) -> list[dict] | None:
    p = Path(path_str.strip()).expanduser()
    if not p.exists():
        print(f"  File not found: {p}")
        return None
    try:
        data = json.loads(p.read_text())
        if isinstance(data, dict):
            data = [data]
        print(f"  Loaded {len(data)} column(s) from {p.name}.")
        return data
    except Exception as e:
        print(f"  Error reading file: {e}")
        return None


def main() -> None:
    print("=" * 60)
    print("  SchemaIntelligence Agent — Interactive Chat")
    print("=" * 60)
    print(HELP)
    print(EXAMPLES)

    agent = SchemaIntelligenceAgent()
    last_schema: list[dict] | None = None
    last_detections: list[dict] | None = None

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not user_input:
            continue

        cmd = user_input.lower()

        if cmd in ("/quit", "/exit", "quit", "exit"):
            print("Bye!")
            break

        elif cmd == "/help":
            print(HELP)

        elif cmd == "/schema":
            schema = load_schema_interactive()
            if schema:
                last_schema = schema
                last_detections = None
                response = agent.chat("Analyse this schema for PII", schema=last_schema)
                print(f"\nAgent: {response}\n")
                # try to extract detections from response for /mask
                try:
                    json_start = response.find("[")
                    if json_start != -1:
                        last_detections = json.loads(response[json_start:response.rfind("]") + 1])
                except Exception:
                    pass

        elif cmd.startswith("/load"):
            parts = user_input.split(maxsplit=1)
            if len(parts) < 2:
                print("  Usage: /load <path/to/schema.json>")
            else:
                schema = load_schema_from_file(parts[1])
                if schema:
                    last_schema = schema
                    last_detections = None
                    response = agent.chat("Analyse this schema for PII", schema=last_schema)
                    print(f"\nAgent: {response}\n")
                    try:
                        json_start = response.find("[")
                        if json_start != -1:
                            last_detections = json.loads(response[json_start:response.rfind("]") + 1])
                    except Exception:
                        pass

        elif cmd == "/mask":
            if last_schema is None and last_detections is None:
                print("  No schema analysed yet. Use /schema or /load first.")
            else:
                response = agent.chat(
                    "Generate a masking configuration for these results",
                    schema=last_schema,
                    detections=last_detections,
                )
                print(f"\nAgent: {response}\n")

        else:
            # If this looks like a config-generation request but we have no detections
            # loaded (from /schema or /load), offer an inline paste mode so the user
            # can supply the detection JSON — input() only reads one line at a time,
            # so multiline JSON cannot be embedded in the trigger message directly.
            cfg_keywords = ("generate a masking configuration", "generate masking configuration")
            lower_input = user_input.lower()
            if any(k in lower_input for k in cfg_keywords) and last_detections is None:
                print("  Paste your detection results JSON (a list), then press Enter twice:")
                json_lines: list[str] = []
                while True:
                    try:
                        line = input()
                    except EOFError:
                        break
                    if line == "" and json_lines:
                        break
                    json_lines.append(line)
                raw_json = "\n".join(json_lines).strip()
                if raw_json:
                    try:
                        last_detections = json.loads(raw_json)
                        if isinstance(last_detections, dict):
                            last_detections = [last_detections]
                    except json.JSONDecodeError as exc:
                        print(f"  Invalid JSON: {exc}")
                        last_detections = None

            response = agent.chat(user_input, schema=last_schema, detections=last_detections)
            print(f"\nAgent: {response}\n")


if __name__ == "__main__":
    main()
