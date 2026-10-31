#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "expat.h"
static void *dirty_alloc(size_t n){void *p=malloc(n);if(p)memset(p,0XA5,n);return p;}
int main(void){
    XML_Memory_Handling_Suite mem={dirty_alloc,realloc,free};
    XML_Parser p=XML_ParserCreate_MM(NULL,&mem,NULL);
    if(!p)return 3;
    XML_ParsingStatus status;
    int contract=!strcmp(getenv("PANEL_STAGE"),"contract");
    if(!contract && XML_Parse(p,"<r/>",4,XML_TRUE)!=XML_STATUS_OK)return 4;
    XML_GetParsingStatus(p,&status);
    int ok=contract?(status.parsing==XML_INITIALIZED && status.finalBuffer==XML_FALSE):
                     (status.parsing==XML_FINISHED && status.finalBuffer==XML_TRUE);
    printf("parsing=%d final=%u\n",status.parsing,(unsigned)status.finalBuffer);
    XML_ParserFree(p);
    return ok?0:42;
}
