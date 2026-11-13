pub fn check(x:Option<&str>)->&str{x.filter(|v|!v.is_empty()).unwrap_or("fallback")}
