# Cross-language AST parity

The default two-file command parses each file, resolves the supported local primitive types/bindings, maps both languages into a shared AST, and compares that shared AST. It does not compare language-specific node names and call that cross-language parity.

## Mappings

| TypeScript | Rust | Shared representation |
| --- | --- | --- |
| Named function declaration | Named `fn` | function with name, visibility, signature and body |
| `number` / `boolean` / `string` | `f64` / `bool` / `&str` | f64 / bool / string |
| Parameter/local names | Different parameter/local names | lexical IDs `p0`, `v0`, etc. |
| `return expression` | Explicit return or tail expression | return value |
| `let`/`const` bindings | `let`/`let mut` bindings | bind; assignment legality tracked separately |
| Primitive arithmetic/comparisons | Same primitive operations | typed operator and ordered operands |
| Primitive `===`/`!==` | Primitive `==`/`!=` | eq/ne after local primitive resolution |
| Boolean `&&`/`||`/`!` | Boolean `&&`/`||`/`!` | typed boolean operation |
| `if/else`, `while`, nested blocks | Corresponding control constructs | if, while, block |
| Calls to named local functions | Calls to named local functions | resolved local call/signature |

Function names, public visibility, parameter order/types, literal values and operand order remain observable in the comparison. Local names are normalized with lexical scope, so shadowed variables do not accidentally become their outer bindings. Function declaration order is normalized by name. Comments and parentheses do not enter the shared operation tree. Original syntax trees, positions and source hashes remain in JSON reports.

Literal numbers use binary64 normalization for TypeScript numbers/Rust floats. Rust integers remain exact and width-specific; large integer literals are not rounded through a Python float. Integer widths are not merged into TypeScript `number`. Integer inference is limited to directly resolved expected widths; unsupported inference is unresolved. Only decimal unsuffixed numeric literals and supported basic string escapes are handled.

## Resolution and assumptions

The resolver tracks concrete primitive parameter annotations, local initialized bindings, assignment types and signatures of functions declared in these standalone files. Unknown identifiers/types, shadowed call targets, inconsistent types, defaults, generic calls and external methods prevent a positive parity result. This is local resolution, not a TypeScript compiler or rust-analyzer integration, and does not certify that arbitrary input code compiles.

The optional `--assume-option-mapping` flag explicitly declares that Rust Option methods are standard-library methods and TypeScript null/undefined inputs map to None, with present primitive values mapping to Some. That assertion is recorded in the report. Without it, Option correspondence/method identity is unresolved. It does not override unsupported types or arbitrary method bodies.

With that contract, nullable primitive signatures map to Option signatures. TypeScript `??` and Rust `unwrap_or(literal)` become a fallback-on-missing node. TypeScript `||` becomes fallback-on-falsy. The exact pure Option filters already supported by the behavioral demo can reproduce primitive truthiness before `unwrap_or`. Only literal Rust defaults are supported, so eager default evaluation does not silently get equated with an effectful lazy expression.

## Result contract

- `parity`: every relevant construct was handled and the shared ASTs match.
- `different`: all relevant constructs were handled and the shared ASTs differ.
- `unresolved`: parsing, supported syntax or resolution is incomplete. Even identical unsupported trees cannot produce a positive result. `comparison.same_shared_ast` is null in this case.

These are normalized structural findings. A difference is not necessarily a behavioral regression; parity is not a full behavioral-equivalence proof. Equivalent algorithms expressed with different supported control structures may still produce different shared ASTs. Library behavior, exceptions, aliasing, concurrency, module context and inputs outside the declared primitive contract are not proven by this comparison.

Known limitations include standalone function declarations only; no imports, classes, generic/async/unsafe functions, arbitrary closures, arrays/objects, string ownership conversions, external calls, implicit JavaScript coercions across types, or full compiler inference. Unhandled constructs are retained as unresolved placeholders with reasons and locations, never dropped to force a match.

## Outputs

`--output-dir asts` saves the normalized trees as `left.ast.json` / `right.ast.json`, original parser trees as `left.syntax.json` / `right.syntax.json`, and a unified shared-tree `diff.txt`. `--format json` or `--json-output report.json` includes both forms, resolution issues, assumptions, status and source hashes. No source is executed by this mode.

`--raw` selects the older syntax-only dump/diff. The manifest-based `compare` and `suite` commands remain independent, including their actual Node/Cargo execution evidence.
