function helper(a:boolean,b:boolean):boolean{return (a&&b)||(!a&&!b);}
export function check(a:boolean,b:boolean):boolean{let result:boolean=false;if(a){result=helper(a,b);}else{result=helper(a,b);}return result;}
