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
    /* Claude account-wide rate-limit usage (0-100), from MsgTypeRatelimit.
     * Independent of the fields above: set on its own timer, not per
     * response, and each has_ratelimit_* flag tracks its own field so a
     * message reporting only one percentage doesn't blank out the other. */
    int32_t ratelimit_session_pct;
    int32_t ratelimit_week_pct;
    bool has_ratelimit_session;
    bool has_ratelimit_week;
} UsageStats;

void usage_stats_set(
    uint32_t input_tokens, uint32_t output_tokens,
    uint32_t cache_write_tokens, uint32_t cache_read_tokens,
    uint32_t cost_cents);

/* session_pct/week_pct: pass -1 for "not present in this update" to leave
 * that field (and its has_ratelimit_* flag) unchanged. Never touches the
 * token/cost fields above. */
void usage_stats_set_ratelimit(int32_t session_pct, int32_t week_pct);

void usage_stats_get(UsageStats* out);

#ifdef __cplusplus
}
#endif
