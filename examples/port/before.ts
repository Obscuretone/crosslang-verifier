function nonnegative(amount: number): number {
  if (amount < 0) { return 0; }
  return amount;
}

export function shipping(subtotal: number, express: boolean): number {
  let cost: number = 10;
  if (nonnegative(subtotal) >= 100) { cost = 0; }
  if (express) { cost = cost + 10; }
  return cost;
}

export function eligible(member: boolean, coupon: boolean): boolean {
  return member || coupon;
}
