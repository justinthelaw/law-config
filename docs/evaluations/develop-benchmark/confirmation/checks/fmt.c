#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fmt/fmt-c.h>
int main(void){
    if(strcmp(getenv("PANEL_STAGE"),"contract")!=0){
        char out[6]={0};
        int n=fmt_format(out,sizeof(out),"{}",123);
        printf("%d %.3s\n",n,out);
        return n==3 && !memcmp(out,"123",3)?0:42;
    }
    int n=fmt_format(NULL,0,"{:2147483647}{:2147483647}{}",1,2,"more");
    printf("%d expected %d\n",n,(int)fmt_error);
    return n==fmt_error?0:42;
}
