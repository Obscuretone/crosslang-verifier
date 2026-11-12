pub fn evaluate(x: std::option::Option<&str>) -> &str {
    x.unwrap_or("line\n\"quoted\"")
}
