fn nonnegative(value: f64) -> f64 {
    if value < 0.0 { 0.0 } else { value }
}

pub fn shipping(amount: f64, rush: bool) -> f64 {
    if nonnegative(amount) > 100.0 {
        if rush { 10.0 } else { 0.0 }
    } else if rush { 20.0 } else { 10.0 }
}

pub fn eligible(member: bool, coupon: bool) -> bool {
    !(!member && !coupon)
}
