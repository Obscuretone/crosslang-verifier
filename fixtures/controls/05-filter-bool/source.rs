pub fn evaluate(x: std::option::Option<bool>) -> bool {
    x.filter(|v| *v).unwrap_or(true)
}
