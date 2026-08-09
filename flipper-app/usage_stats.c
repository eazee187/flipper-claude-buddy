#include "usage_stats.h"
#include <string.h>

static UsageStats s_stats;

void usage_stats_set(
    uint32_t input_tokens, uint32_t output_tokens,
    uint32_t cache_write_tokens, uint32_t cache_read_tokens,
    uint32_t cost_cents) {
    s_stats.input_tokens = input_tokens;
    s_stats.output_tokens = output_tokens;
    s_stats.cache_write_tokens = cache_write_tokens;
    s_stats.cache_read_tokens = cache_read_tokens;
    s_stats.cost_cents = cost_cents;
    s_stats.has_data = true;
}

void usage_stats_get(UsageStats* out) {
    if(!out) return;
    memcpy(out, &s_stats, sizeof(UsageStats));
}
