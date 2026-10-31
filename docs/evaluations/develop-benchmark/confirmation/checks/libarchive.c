#include <archive.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static int opening_volumes(void){
    const int contract=!strcmp(getenv("PANEL_STAGE"),"contract");
    FILE *f=fopen("/tmp/empty.tar","wb");
    if(!f)return 3;
    char block[1024]={0}; for(int i=0;i<512;i++)if(fwrite(block,1,sizeof(block),f)!=sizeof(block))return 4;
    fclose(f);
    const char *files[]={"/tmp/empty.tar",contract?"/tmp/nonexistent-volume":NULL,NULL};
    struct archive *a=archive_read_new();
    if(!a || archive_read_support_format_all(a)!=ARCHIVE_OK)return 5;
    int rc=archive_read_open_filenames(a,files,10240);
    printf("open=%d message=%s\n",rc,archive_error_string(a)?archive_error_string(a):"(none)");
    archive_read_free(a);
    return rc==(contract?ARCHIVE_FATAL:ARCHIVE_OK)?0:42;
}

struct source {
    unsigned char bytes[16384];
    la_int64_t position;
    unsigned int end_seeks;
};

static la_ssize_t advance(struct archive *archive, void *data, const void **block) {
    struct source *src = data;
    size_t remaining = sizeof src->bytes - src->position;
    *block = src->bytes + src->position;
    src->position += remaining;
    return (la_ssize_t)remaining;
}

static la_int64_t seek(struct archive *archive, void *data, la_int64_t amount, int whence) {
    struct source *src = data;
    la_int64_t base;
    switch (whence) {
    case SEEK_SET: base = 0; break;
    case SEEK_CUR: base = src->position; break;
    case SEEK_END:
        base = sizeof src->bytes;
        src->end_seeks++;
        break;
    default: return ARCHIVE_FATAL;
    }
    la_int64_t position = base + amount;
    if (position < 0 || position > (la_int64_t)sizeof src->bytes) return ARCHIVE_FATAL;
    return src->position = position;
}

static int redundant_seeks(void) {
    struct source source = {0};
    for (size_t i = 0; i < sizeof source.bytes; ++i) source.bytes[i] = (unsigned char)((i * 17 + 73) % 251);
    struct archive *reader = archive_read_new();
    if (!reader || archive_read_support_format_all(reader) != ARCHIVE_OK ||
        archive_read_set_read_callback(reader, advance) != ARCHIVE_OK ||
        archive_read_set_seek_callback(reader, seek) != ARCHIVE_OK ||
        archive_read_set_callback_data(reader, &source) != ARCHIVE_OK) return 3;
    int status = archive_read_open1(reader);
    printf("open=%d SEEK_END=%u\n", status, source.end_seeks);
    archive_read_free(reader);
    if (status != ARCHIVE_FATAL) return 4;
    return source.end_seeks <= 1 ? 0 : 42;
}

int main(void) {
    int opened = opening_volumes();
    if (opened || strcmp(getenv("PANEL_STAGE"), "contract") != 0) return opened;
    return redundant_seeks();
}
