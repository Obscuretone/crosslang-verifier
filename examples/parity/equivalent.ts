export function adjust(value: number, enabled: boolean): number {
    let total = value * 2;
    if (enabled) {
        total = total + 1;
    } else {
        total = total - 1;
    }
    while (total < 10) {
        total = total + 1;
    }
    return total;
}
