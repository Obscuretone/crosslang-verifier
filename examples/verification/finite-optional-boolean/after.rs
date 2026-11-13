pub fn check(x:Option<bool>)->bool{x.filter(|v|*v).unwrap_or(true)}
