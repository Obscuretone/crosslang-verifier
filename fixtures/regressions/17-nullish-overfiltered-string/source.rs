pub fn evaluate(x: std::option::Option<&str>) -> &str {
    x.filter(|v| !v.is_empty()).unwrap_or("default")
}
