export function evaluate(x: string | null | undefined): string {
    return x || "line\n\"quoted\"";
}
