"""Counterexample queries for a deliberately small, loop-free shared IR model.

UNSAT proves only this model. Native observations are separate evidence.
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass

import z3

from .models import Value


class OutsideModel(ValueError):
    pass


@dataclass
class OptionalTerm:
    present: object
    value: object


class ModelChecker:
    def __init__(self, timeout_ms: int = 5000):
        if timeout_ms <= 0:
            raise ValueError("Solver timeout must be positive")
        self.timeout_ms = timeout_ms

    def check(self, left: dict, right: dict, name: str) -> dict:
        model = Query(left, right, self.timeout_ms)
        try:
            return model.check(name)
        except (OutsideModel, z3.Z3Exception, RecursionError) as exc:
            return {"status": "unsupported", "reason": str(exc), "solver": z3.get_version_string()}


class Query:
    def __init__(self, left: dict, right: dict, timeout: int):
        self.modules = [
            {function["name"]: function for function in module["functions"]}
            for module in (left, right)
        ]
        self.solver = z3.Solver()
        self.solver.set(timeout=timeout)
        self.strings: dict[str, object] = {}
        self.string_sort = z3.DeclareSort("SharedString")
        self.string("")
        self.timeout_ms = timeout
        self.steps = 0

    def string(self, text: str):
        if text not in self.strings:
            self.strings[text] = z3.Const(f"literal_{len(self.strings)}", self.string_sort)
        return self.strings[text]

    def symbolic(self, name: str, type_: object):
        if isinstance(type_, dict) and set(type_) == {"option"}:
            return OptionalTerm(z3.Bool(name + "_present"), self.symbolic(name, type_["option"]))
        sorts = {"f64": z3.Float64(), "bool": z3.BoolSort(), "string": self.string_sort}
        if not isinstance(type_, str) or type_ not in sorts:
            raise OutsideModel(f"No solver input model for {type_!r}")
        return z3.Const(name, sorts[type_])

    def truthy(self, term):
        if isinstance(term, OptionalTerm):
            return z3.And(term.present, self.truthy(term.value))
        if z3.is_fp(term):
            return z3.And(z3.Not(z3.fpIsNaN(term)), z3.Not(z3.fpIsZero(term)))
        if z3.is_bool(term):
            return term
        return term != self.string("")

    def choose(self, condition, yes, no):
        if isinstance(yes, OptionalTerm) and isinstance(no, OptionalTerm):
            return OptionalTerm(
                z3.If(condition, yes.present, no.present),
                z3.If(condition, yes.value, no.value),
            )
        return z3.If(condition, yes, no)

    def expression(self, node: dict, env: dict, module: dict, stack: tuple):
        kind = node["kind"]
        if kind == "load":
            return env[node["id"]]
        if kind == "literal":
            type_, value = node["type"], node["value"]
            if type_ == "bool":
                return z3.BoolVal(value)
            if type_ == "string":
                return self.string(value)
            if type_ == "f64":
                # Preserve the exact binary64 value, including signed zero.
                bits = struct.unpack(">Q", struct.pack(">d", float(value)))[0]
                return z3.fpBVToFP(z3.BitVecVal(bits, 64), z3.Float64())
            raise OutsideModel(f"No solver literal model for {type_}")
        if kind == "call":
            args = [self.expression(a, env, module, stack) for a in node["arguments"]]
            return self.function(module, node["function"], args, stack)
        if kind in {"unary", "truthy", "fallback"}:
            value = self.expression(node["value"], env, module, stack)
            if kind == "truthy":
                return self.truthy(value)
            if kind == "unary":
                return z3.Not(value) if node["operator"] == "not" else z3.fpNeg(value)
            default = self.expression(node["default"], env, module, stack)
            present = value.present if isinstance(value, OptionalTerm) else z3.BoolVal(True)
            keep = self.truthy(value) if node["trigger"] == "falsy" else present
            payload = value.value if isinstance(value, OptionalTerm) else value
            return self.choose(keep, payload, default)
        if kind != "binary":
            raise OutsideModel(f"No solver expression model for {kind}")
        a = self.expression(node["left"], env, module, stack)
        b = self.expression(node["right"], env, module, stack)
        operator = node["operator"]
        if operator in {"eq", "ne"}:
            equal = z3.fpEQ(a, b) if z3.is_fp(a) else a == b
            return z3.Not(equal) if operator == "ne" else equal
        if operator == "&&":
            return z3.And(a, b)
        if operator == "||":
            return z3.Or(a, b)
        if not z3.is_fp(a) or not z3.is_fp(b):
            raise OutsideModel("Only binary64 arithmetic is modeled")
        arithmetic = {"+": z3.fpAdd, "-": z3.fpSub, "*": z3.fpMul, "/": z3.fpDiv}
        comparisons = {"<": z3.fpLT, "<=": z3.fpLEQ, ">": z3.fpGT, ">=": z3.fpGEQ}
        if operator in arithmetic:
            return arithmetic[operator](z3.RNE(), a, b)
        if operator in comparisons:
            return comparisons[operator](a, b)
        # IEEE fp.rem is NOT JS/Rust remainder; do not substitute it.
        raise OutsideModel(f"No solver arithmetic model for {operator}")

    def block(self, statements: list, states: list, module: dict, stack: tuple):
        returns = []
        for node in statements:
            following = []
            for guard, env in states:
                self.steps += 1
                if self.steps > 512:
                    raise OutsideModel("Symbolic path budget exceeded")
                kind = node["kind"]
                if kind == "return":
                    returns.append((guard, self.expression(node["value"], env, module, stack)))
                    continue
                if kind in {"if", "block"}:
                    if kind == "if":
                        condition = self.expression(node["condition"], env, module, stack)
                        branches = [
                            (node["then"], z3.And(guard, condition)),
                            (node["else"], z3.And(guard, z3.Not(condition))),
                        ]
                    else:
                        branches = [(node["body"], guard)]
                    for body, branch_guard in branches:
                        active, finished = self.block(
                            body, [(branch_guard, env.copy())], module, stack
                        )
                        following.extend(active)
                        returns.extend(finished)
                    continue
                updated = env.copy()
                if kind in {"assign", "bind", "evaluate"}:
                    value = self.expression(node["value"], env, module, stack)
                    if kind != "evaluate":
                        updated[node["target"] if kind == "assign" else node["id"]] = value
                else:
                    raise OutsideModel(f"No solver statement model for {kind}")
                following.append((guard, updated))
            states = following
        return states, returns

    def function(self, module: dict, name: str, args: list, stack: tuple = ()):
        if name in stack or len(stack) >= 16:
            raise OutsideModel("Recursion is outside the solver model")
        function = module[name]
        if not isinstance(function["returns"], str) or function["returns"] not in {
            "f64",
            "bool",
            "string",
        }:
            raise OutsideModel("Only primitive return values are modeled")
        env = {f"p{i}": arg for i, arg in enumerate(args)}
        active, returns = self.block(
            function["body"], [(z3.BoolVal(True), env)], module, (*stack, name)
        )
        if active or not returns:
            raise OutsideModel("Not all modeled paths return")
        result = returns[-1][1]
        for guard, value in reversed(returns[:-1]):
            result = self.choose(guard, value, result)
        return result

    def decode(self, model, term, fresh: dict) -> Value:
        if isinstance(term, OptionalTerm):
            if not z3.is_true(model.eval(term.present, model_completion=True)):
                return Value("null")  # The caller chooses an admitted TS missing representation.
            return self.decode(model, term.value, fresh)
        if z3.is_bool(term):
            return Value("boolean", z3.is_true(model.eval(term, model_completion=True)))
        if z3.is_fp(term):
            if z3.is_true(model.eval(z3.fpIsNaN(term), model_completion=True)):
                return Value("number", "NaN")
            bits = model.eval(z3.fpToIEEEBV(term), model_completion=True).as_long()
            value = struct.unpack(">d", bits.to_bytes(8, "big"))[0]
            if value == float("inf"):
                text = "Infinity"
            elif value == -float("inf"):
                text = "-Infinity"
            else:
                text = "-0" if bits == 1 << 63 else repr(value)
            return Value("number", text)
        representative = str(model.eval(term, model_completion=True))
        for text, constant in self.strings.items():
            if str(model.eval(constant, model_completion=True)) == representative:
                return Value("string", text)
        if representative not in fresh:
            text = f"solver_string_{len(fresh)}"
            while text in self.strings or text in fresh.values():
                text += "_"
            fresh[representative] = text
        return Value("string", fresh[representative])

    def check(self, name: str) -> dict:
        args = [
            self.symbolic(f"p{i}", t) for i, t in enumerate(self.modules[0][name]["parameters"])
        ]
        left, right = [self.function(module, name, args) for module in self.modules]
        if len(self.strings) > 1:
            self.solver.add(z3.Distinct(*self.strings.values()))
        if z3.is_fp(left):
            same = z3.Or(
                z3.And(z3.fpIsNaN(left), z3.fpIsNaN(right)),
                z3.And(
                    z3.Not(z3.fpIsNaN(left)),
                    z3.Not(z3.fpIsNaN(right)),
                    z3.fpToIEEEBV(left) == z3.fpToIEEEBV(right),
                ),
            )
        else:
            same = left == right
        self.solver.add(z3.Not(same))
        query = self.solver.to_smt2()
        answer = self.solver.check()
        result = {
            "status": {"sat": "counterexample_candidate", "unsat": "unsat"}.get(
                str(answer), "unknown"
            ),
            "solver": z3.get_version_string(),
            "timeout_ms": self.timeout_ms,
            "query_sha256": hashlib.sha256(query.encode()).hexdigest(),
            "smt2": query,
            "scope": "Loop-free shared IR: RNE binary64, booleans, string equality/empty tests; "
            "NaN payloads ignored, signed zero distinguished. Mapping correctness is assumed.",
        }
        if answer == z3.sat:
            model, fresh = self.solver.model(), {}
            result["candidate"] = [self.decode(model, term, fresh) for term in args]
        elif answer == z3.unknown:
            result["reason"] = self.solver.reason_unknown()
        return result
