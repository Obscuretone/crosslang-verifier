"""Deterministic, bounded candidate generation (not a solver or proof)."""

from .models import FallbackIR, Resolution, Value


class CandidateGenerator:
    def generate(self, resolution: Resolution, ts: FallbackIR, rust: FallbackIR) -> list[Value]:
        if resolution.allowed_inputs is not None:
            return list(resolution.allowed_inputs)
        primitive = {
            "number": [
                Value("number", v)
                for v in ["0", "-0", "NaN", "1", "-1", "0.5", "Infinity", "-Infinity"]
            ],
            "boolean": [Value("boolean", False), Value("boolean", True)],
            "string": [Value("string", v) for v in ["", "hello", "0", "false", " ", 'é\n"\\']],
        }[resolution.domain]
        types = ts.parameter_type.split("|")
        missing = [Value(k) for k in ["null", "undefined"] if k in types]
        return list(dict.fromkeys([*primitive, *missing, ts.fallback, rust.fallback]))
