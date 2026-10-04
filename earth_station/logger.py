"""Screen output plus one JSON line per event in runs/<timestamp>.jsonl."""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

_COLOR = sys.stdout.isatty() and not os.getenv("NO_COLOR")
if _COLOR and os.name == "nt":
    os.system("")  # enables ANSI colours in the Windows console

_CODES = {"green": "32", "yellow": "33", "red": "31", "blue": "36", "dim": "90"}


def paint(text: str, color: str) -> str:
    return f"\033[{_CODES[color]}m{text}\033[0m" if _COLOR else text


class Logger:
    def __init__(self, log_dir: Path):
        log_dir.mkdir(parents=True, exist_ok=True)
        self.path = log_dir / f"{datetime.now():%Y-%m-%d_%H%M%S}.jsonl"
        self._file = self.path.open("a", encoding="utf-8")

    def close(self) -> None:
        self._file.close()

    def _write(self, kind: str, **data: Any) -> None:
        record = {"t": time.time(), "kind": kind, **data}
        self._file.write(json.dumps(record, default=str) + "\n")
        self._file.flush()

    def _stamp(self) -> str:
        return paint(datetime.now().strftime("%H:%M:%S.%f")[:-3], "dim")

    def check(self, ok: bool, message: str) -> None:
        mark = paint("OK ", "green") if ok else paint("X  ", "red")
        print(f"  {mark} {message}")

    def info(self, message: str, color: str | None = None) -> None:
        print(f"{self._stamp()} {paint(message, color) if color else message}")
        self._write("info", message=message)

    def mode(self, old: str, new: str) -> None:
        self.info(f"mode {old} -> {paint(new.upper(), 'blue')}")
        self._write("mode", old=old, new=new)

    def scene(self, scene: dict[str, Any]) -> None:
        print(f'{self._stamp()} scene  "{scene["summary"]}"')
        self._write("scene", scene=scene)

    def decision(self, state, decision, gate, reply, suggest_only: bool) -> None:
        seq = gate.command["seq"] if gate.command else "-"
        if decision is None:
            head = f"#{seq:<5} {'(no answer)':<11}      "
        else:
            conf = f"{decision.confidence:.2f}"
            conf = paint(conf, "green" if gate.approved else "yellow")
            head = f"#{seq:<5} {decision.action:<11} {conf}"

        if gate.command is None:
            tail = paint(f"idle: {gate.reason}", "dim")
        elif suggest_only:
            would = gate.command["action"] if gate.approved else f"stop ({gate.reason})"
            tail = paint(f"suggest only, would send {would}", "blue")
        elif not gate.approved:
            tail = paint(f"gate: {gate.reason}, sent stop", "yellow")
        elif reply is None:
            tail = paint("rover did not answer", "red")
        elif reply.get("ok"):
            tail = "sent, rover ok"
        else:
            tail = paint(f"rover refused: {reply.get('refused', 'unknown')}", "red")

        print(f"{self._stamp()} {head}  -> {tail}")
        self._write(
            "decision",
            state=state,
            decision=None if decision is None else decision.__dict__,
            gate={"command": gate.command, "approved": gate.approved, "reason": gate.reason},
            reply=reply,
            suggest_only=suggest_only,
        )
