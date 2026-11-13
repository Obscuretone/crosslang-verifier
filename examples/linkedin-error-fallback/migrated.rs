pub fn evaluate(error: std::option::Option<&str>) -> &str {
    error.unwrap_or("Unknown error")
}
