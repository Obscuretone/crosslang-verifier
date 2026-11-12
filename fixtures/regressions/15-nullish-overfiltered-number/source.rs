pub fn evaluate(x: std::option::Option<f64>) -> f64 {
    x.filter(|v| *v != 0.0 && !v.is_nan()).unwrap_or(9.0)
}
