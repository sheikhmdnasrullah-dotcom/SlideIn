#!/usr/bin/env python3
"""Slidein Client Intake CLI.

Accepts raw notes (via file, stdin, or chat paste), automatically parses
company details, industry, terminology, brand assets, sending policy,
and team members, and outputs a validated deployment bundle (config.json + owners.json).

Usage:
    python3 scripts/compile_client_intake.py --input client_notes.txt
    cat client_notes.txt | python3 scripts/compile_client_intake.py --output bundle.json
"""

import argparse
import json
import os
import sys

# Auto-detect virtualenv python if run with system python lacking dependencies
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
venv_py = os.path.join(root_dir, "slidein-api", ".venv", "bin", "python")
if os.path.exists(venv_py) and sys.executable != venv_py:
    try:
        import sqlalchemy
    except ImportError:
        os.execv(venv_py, [venv_py] + sys.argv)

api_dir = os.path.join(root_dir, "slidein-api")
if api_dir not in sys.path:
    sys.path.insert(0, api_dir)

from slidein_api.factory.compiler import IntakeCompiler


def main():
    parser = argparse.ArgumentParser(description="Compile raw client intake notes into a deployment bundle.")
    parser.add_argument("--input", "-i", help="Path to input text file (reads from stdin if omitted).")
    parser.add_argument("--output", "-o", help="Path to write the compiled JSON bundle (writes to stdout if omitted).")
    parser.add_argument("--client-id", help="Explicit tenant ID (auto-generated if omitted).")
    args = parser.parse_args()

    if args.input:
        with open(args.input, "r", encoding="utf-8") as f:
            raw_text = f.read()
    else:
        if sys.stdin.isatty():
            print("Enter client intake notes (press Ctrl+D when finished):", file=sys.stderr)
        raw_text = sys.stdin.read()

    if not raw_text.strip():
        print("Error: No intake text provided.", file=sys.stderr)
        sys.exit(1)

    bundle = IntakeCompiler.compile(raw_text, client_id=args.client_id)
    output_json = json.dumps(bundle, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_json)
        print(f"==> Successfully compiled client bundle for '{bundle['config']['identity']['business_name']}'", file=sys.stderr)
        print(f"==> Wrote: {args.output}", file=sys.stderr)
    else:
        print(output_json)


if __name__ == "__main__":
    main()
