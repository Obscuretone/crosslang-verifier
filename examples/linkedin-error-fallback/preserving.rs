pub fn evaluate(error: std::option::Option<&str>) -> &str {
    error.filter(|v| !v.is_empty()).unwrap_or("Unknown error")
}
