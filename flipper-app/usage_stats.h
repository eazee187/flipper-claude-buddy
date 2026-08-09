/**
 * Cumulative session token usage (Bridge mode), for the on-device Usage
 * info page.
 *
 * Set from MsgTypeUsage in process_message() (GUI thread) and read from
 * info_draw() (also GUI thread) — both run on the same thread per the
 * project's threading model, so no locking is needed here.
 *
 * Not persisted to flash: this represents "current session" and resets to
 * has_data=false on every app boot.
 */

#pragma once

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    uint32_t input_tokens;
    uint32_t output_tokens;
    uint32_t cache_write_tokens;
    uint32_t cache_read_tokens;
    uint32_t cost_cents;  /* estimated USD cents, computed host-side */
    bool has_data;        /* false until the first MsgTypeUsage this run */
} UsageStats;

void usage_stats_set(
    uint32_t input_tokens, uint32_t output_tokens,
    uint32_t cache_write_tokens, uint32_t cache_read_tokens,
    uint32_t cost_cents);

void usage_stats_get(UsageStats* out);

#ifdef __cplusplus
}
#endif
