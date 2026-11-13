pub fn adjust(amount: f64, flag: bool) -> f64 {
    let mut result = amount * 3.0;
    if flag {
        result = result + 1.0;
    } else {
        result = result - 1.0;
    }
    while result < 10.0 {
        result = result + 1.0;
    }
    result
}
