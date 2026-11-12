"""Reporter extension boundary; JSON schema is independent of console presentation."""

import json
from typing import Any, Protocol


class Reporter(Protocol):
    def render(self, payload: dict[str, Any]) -> str: ...


class JsonReporter:
    def render(self, payload: dict[str, Any]) -> str:
        return json.dumps(payload, indent=2, ensure_ascii=True, allow_nan=False) + "\n"


class ConsoleReporter:
    def render(self, payload: dict[str, Any]) -> str:
        reports = payload.get("reports", [payload])
        lines = ["ObscureTone Semantic Diff · bounded behavioral evidence"]
        for report in reports:
            lines.append(f"{report['pair_id']}: {report['status']}")
            for assessment in report["assessments"]:
                label = "STATIC WARNING" if assessment["warning"] else "STATIC CHECK"
                lines.append(f"  {label} [{assessment['rule_id']}]: {assessment['message']}")
            for difference in report["differences"]:
                lines.append(
                    f"  CONFIRMED input={difference['input']} "
                    f"TypeScript={difference['typescript']} Rust={difference['rust']}"
                )
            for execution in report["executions"]:
                if execution["error"]:
                    lines.append(f"  {execution['language']} runner error: {execution['error']}")
            for limitation in report["limitations"]:
                lines.append(f"  Scope: {limitation}")
        if "summary" in payload:
            lines.append(f"Suite: {payload['summary']}")
        lines.append("No full semantic equivalence is claimed.")
        return "\n".join(lines) + "\n"
