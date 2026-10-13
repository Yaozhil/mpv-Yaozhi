
#include <stdint.h>
#include <stdbool.h>
#include <inttypes.h>
#include <stddef.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
typedef void *HANDLE;
typedef unsigned long DWORD;
typedef void *CONDITION_VARIABLE;
typedef void *INIT_ONCE;
typedef void *SRWLOCK;

typedef CONDITION_VARIABLE mp_cond;
typedef INIT_ONCE          mp_once;
typedef SRWLOCK            mp_mutex;
typedef mp_mutex           mp_static_mutex;
typedef HANDLE             mp_thread;
typedef DWORD              mp_thread_id;
#include "common/ass_pacing_record.h"
#include "video/out/secondary_ass_budget.h"
#include "video/out/secondary_ass_flip_budget.h"
#include "video/out/secondary_ass_presentation.h"
#include "video/out/secondary_ass_physical.h"
#include "video/out/secondary_ass_present_plan.h"
#include "sub/secondary_ass_clock.h"
#include "video/out/secondary_ass_neutral_pose.h"
#include "video/out/secondary_ass_queue_lead.h"
#include "video/out/secondary_ass_queue_stage.h"
#include "video/out/secondary_ass_stage_prefix.h"
#include "video/out/secondary_ass_queue_stage.h"
#include "video/out/secondary_ass_stage_prefix.h"
#include "misc/mp_assert.h"
#define MPMIN(a, b) ((a) > (b) ? (b) : (a))
#define MPMAX(a, b) ((a) > (b) ? (a) : (b))
#define MPCLAMP(a, min, max) (((a) < (min)) ? (min) : (((a) > (max)) ? (max) : (a)))
#define MP_TIME_S_TO_NS(s) ((s) * INT64_C(1000000000))
#define MP_TIME_MS_TO_NS(ms) ((ms) * INT64_C(1000000))
enum {
    // VO needs to redraw
    VO_EVENT_EXPOSE                     = 1 << 0,
    // VO needs to update state to a new window size
    VO_EVENT_RESIZE                     = 1 << 1,
    // The ICC profile needs to be reloaded
    VO_EVENT_ICC_PROFILE_CHANGED        = 1 << 2,
    // Some other window state changed (position, window state, fps)
    VO_EVENT_WIN_STATE                  = 1 << 3,
    // The ambient light conditions changed and need to be reloaded
    VO_EVENT_AMBIENT_LIGHTING_CHANGED   = 1 << 4,
    // Special mechanism for making resizing with Cocoa react faster
    VO_EVENT_LIVE_RESIZING              = 1 << 5,
    // For VOCTRL_GET_HIDPI_SCALE changes.
    VO_EVENT_DPI                        = 1 << 6,
    VO_EVENT_FOCUS                      = 1 << 7,

    // Set of events the player core may be interested in.
    VO_EVENTS_USER = VO_EVENT_RESIZE | VO_EVENT_WIN_STATE | VO_EVENT_DPI |
                     VO_EVENT_FOCUS | VO_EVENT_AMBIENT_LIGHTING_CHANGED,
};
enum {
    // VO does handle mp_image_params.rotate in 90 degree steps
    VO_CAP_ROTATE90     = 1 << 0,
    // VO does framedrop itself (vo_vdpau). Untimed/encoding VOs never drop.
    VO_CAP_FRAMEDROP    = 1 << 1,
    // VO does not allow frames to be retained (vo_mediacodec_embed).
    VO_CAP_NORETAIN     = 1 << 2,
    // VO supports applying film grain
    VO_CAP_FILM_GRAIN   = 1 << 3,
    // VO is drawn untimed and is never redrawn
    VO_CAP_UNTIMED      = 1 << 4,
    // VO is responsible for freeing frames.
    VO_CAP_FRAMEOWNER   = 1 << 5,
    // VO does handle mp_image_params.vflip
    VO_CAP_VFLIP        = 1 << 6,
};
#define VO_MAX_REQ_FRAMES 10
struct vo;
struct osd_state;
struct mp_image;
struct mp_image_params;
struct mpv_global;
struct mp_osd_res;
#line 101 "options/m_option.h"
struct m_geometry {
    int x, y, w, h;
    bool xy_valid : 1, wh_valid : 1;
    bool w_per : 1, h_per : 1;
    bool x_sign : 1, y_sign : 1, x_per : 1, y_per : 1;
    int ws; // workspace; valid if !=0
};
#line 9 "options/options.h"
typedef struct mp_vo_opts {
    struct m_obj_settings *video_driver_list;

    bool taskbar_progress;
    bool snap_window;
    int drag_and_drop;
    bool ontop;
    int ontop_level;
    bool fullscreen;
    bool border;
    bool title_bar;
    bool all_workspaces;
    bool window_minimized;
    bool window_maximized;
    int focus_on;

    int screen_id;
    char *screen_name;
    int fsscreen_id;
    char *fsscreen_name;
    char *winname;
    char *appid;
    char *wayland_session;
    int x11_netwm;
    int x11_bypass_compositor;
    int x11_present;
    bool x11_wid_title;
    bool cursor_passthrough;
    bool native_keyrepeat;
    bool input_ime;

    int wl_configure_bounds;
    int wl_content_type;
    bool wl_disable_vsync;
    int wl_internal_vsync;
    int wl_edge_pixels_pointer;
    int wl_edge_pixels_touch;
    bool wl_present;

    float panscan;
    float zoom;
    float pan_x, pan_y;
    float align_x, align_y;
    float scale_x, scale_y;
    float margin_x[2];
    float margin_y[2];
    int unscaled;

    struct m_geometry geometry;
    struct m_geometry autofit;
    struct m_geometry autofit_larger;
    struct m_geometry autofit_smaller;
    double window_scale;

    bool auto_window_resize;
    bool recenter;
    bool keepaspect;
    bool keepaspect_window;
    bool hidpi_window_scale;
    bool native_fs;
    bool native_touch;
    bool show_in_taskbar;

    int64_t WinID;

    float force_monitor_aspect;
    float monitor_pixel_aspect;
    bool force_render;
    bool force_window_position;

    int backdrop_type;
    int window_affinity;
    char *mmcss_profile;
    int window_corners;

    double display_fps_override;
    double timing_offset;
    int video_sync;

    struct m_geometry android_surface_size;

    struct m_geometry d3d11_composition_size;

    int swapchain_depth;  // max number of images to render ahead

    struct m_geometry video_crop;
} mp_vo_opts;
#line 223 "video/out/vo.h"
struct vo_extra {
    struct input_ctx *input_ctx;
    struct osd_state *osd;
    struct encode_lavc_context *encode_lavc_ctx;
    void (*wakeup_cb)(void *ctx);
    void *wakeup_ctx;
};
#line 231 "video/out/vo.h"
struct vo_frame {
    // If > 0, realtime when frame should be shown, in mp_time_ns() units.
    // If 0, present immediately.
    int64_t pts;
    // Approximate frame duration, in ns.
    double duration;
    // Realtime of estimated distance between 2 vsync events.
    double vsync_interval;
    // "ideal" display time within the vsync
    double vsync_offset;
    // "ideal" frame duration (can be different from num_vsyncs*vsync_interval
    // up to a vsync) - valid for the entire frame, i.e. not changed for repeats
    double ideal_frame_duration;
    // "ideal" frame vsync point relative to the pts
    double ideal_frame_vsync;
    // "ideal" frame duration relative to the pts
    double ideal_frame_vsync_duration;
    // how often the frame will be repeated (does not include OSD redraws)
    int num_vsyncs;
    // Set if the current frame is repeated from the previous. It's guaranteed
    // that the current is the same as the previous one, even if the image
    // pointer is different.
    // The repeat flag is set if exactly the same frame should be rendered
    // again (and the OSD does not need to be redrawn).
    // A repeat frame can be redrawn, in which case repeat==redraw==true, and
    // OSD should be updated.
    bool redraw, repeat;
    // The frame is not in movement - e.g. redrawing while paused.
    bool still;
    // Frames are output as fast as possible, with implied vsync blocking.
    bool display_synced;
    // Dropping the frame is allowed if the VO is behind.
    bool can_drop;
    // The current frame to be drawn.
    // Warning: When OSD should be redrawn in --force-window --idle mode, this
    //          can be NULL. The VO should draw a black background, OSD on top.
    struct mp_image *current;
    // List of future images, starting with the current one. This does not
    // care about repeated frames - it simply contains the next real frames.
    // vo_set_queue_params() sets how many future frames this should include.
    // The actual number of frames delivered to the VO can be lower.
    // frames[0] is current, frames[1] is the next frame.
    // Note that some future frames may never be sent as current frame to the
    // VO if frames are dropped.
    int num_frames;
    struct mp_image *frames[VO_MAX_REQ_FRAMES];
    // Speed unadjusted, approximate frame duration inferred from past frames
    double approx_duration;
    // ID for frames[0] (== current). If current==NULL, the number is
    // meaningless. Otherwise, it's an unique ID for the frame. The ID for
    // a frame is guaranteed not to change (instant redraws will use the same
    // ID). frames[n] has the ID frame_id+n, with the guarantee that frame
    // drops or reconfigs will keep the guarantee.
    // The ID is never 0 (unless num_frames==0). IDs are strictly monotonous.
    uint64_t frame_id;
};
#line 290 "video/out/vo.h"
struct vo_vsync_info {
    // mp_time_ns() timestamp at which the last queued frame will likely be
    // displayed (this is in the future, unless the frame is instantly output).
    // 0 or lower if unset or unsupported.
    // This implies the latency of the output.
    int64_t last_queue_display_time;

    // Historical native-ASS phase, identified by a real displayed Present.
    // Separate from the future queue guess used by primary video sync.
    int64_t secondary_display_time;
    int64_t secondary_sync_qpc_ns, secondary_sync_time;
    uint32_t secondary_sync_refresh_count, secondary_present_refresh_count;
    uint64_t secondary_present_id;
    uint64_t secondary_submit_id;
    bool secondary_submit_valid;
    int secondary_submit_sync_interval;
    uint64_t secondary_submit_generation;
    // Explicit invalidity resets phase/history; temporary zero statistics do not.
    bool secondary_phase_reset;

    // Time between 2 vsync events in nanoseconds. The difference should be the
    // from 2 times sampled from the same reference point (it should not be the
    // difference between e.g. the end of scanout and the start of the next one;
    // it must be continuous).
    // -1 if unsupported.
    //  0 if supported, but no value available yet. It is assumed that the value
    //    becomes available after enough swap_buffers() calls were done.
    // >0 values are taken for granted. Very bad things will happen if it's
    //    inaccurate.
    int64_t vsync_duration;

    // Number of skipped physical vsyncs at some point in time. Typically, this
    // value is some time in the past by an offset that equals to the latency.
    // This value is reset and newly sampled at every swap_buffers() call.
    // This can be used to detect delayed frames iff you try to call
    // swap_buffers() for every physical vsync.
    // -1 if unset or unsupported.
    int64_t skipped_vsyncs;
};
#line 330 "video/out/vo.h"
struct vo_driver {
    // Encoding functionality, which can be invoked via --o only.
    bool encode;

    // VO_CAP_* bits
    int caps;

    const char *name;
    const char *description;

    /*
     *   returns: zero on successful initialization, non-zero on error.
     */
    int (*preinit)(struct vo *vo);

    /*
     * Whether the given image format is supported and config() will succeed.
     * format: one of IMGFMT_*
     * returns: 0 on not supported, otherwise 1
     */
    int (*query_format)(struct vo *vo, int format);

    /*
     * Initialize or reconfigure the display driver.
     *   params: video parameters, like pixel format and frame size
     * returns: < 0 on error, >= 0 on success
     */
    int (*reconfig)(struct vo *vo, struct mp_image_params *params);

    /*
     * Like reconfig(), but provides the whole mp_image for which the change is
     * required. (The image doesn't have to have real data.)
     */
    int (*reconfig2)(struct vo *vo, struct mp_image *img);

    /*
     * Control interface
     */
    int (*control)(struct vo *vo, uint32_t request, void *data);

    /*
     * lavc callback for direct rendering
     *
     * Optional. To make implementation easier, the callback is always run on
     * the VO thread. The returned mp_image's destructor callback is also called
     * on the VO thread, even if it's actually unref'ed from another thread.
     *
     * It is guaranteed that the last reference to an image is destroyed before
     * ->uninit is called (except it's not - libmpv screenshots can hold the
     * reference longer, fuck).
     *
     * The allocated image - or a part of it, can be passed to draw_frame(). The
     * point of this mechanism is that the decoder directly renders to GPU
     * staging memory, to avoid a memcpy on frame upload. But this is not a
     * guarantee. A filter could change the data pointers or return a newly
     * allocated image. It's even possible that only 1 plane uses the buffer
     * allocated by the get_image function. The VO has to check for this.
     *
     * stride_align is always a value >=1. The stride values of the returned
     * image must be divisible by this value. This may be a non power of two.
     *
     * flags is a combination of VO_DR_FLAG_* flags.
     *
     * Currently, the returned image must have exactly 1 AVBufferRef set, for
     * internal implementation simplicity.
     *
     * returns: an allocated, refcounted image; if NULL is returned, the caller
     * will silently fallback to a default allocator
     */
    struct mp_image *(*get_image)(struct vo *vo, int imgfmt, int w, int h,
                                  int stride_align, int flags);

    /*
     * Thread-safe variant of get_image. Set at most one of these callbacks.
     * This excludes _all_ synchronization magic. The only guarantee is that
     * vo_driver.uninit is not called before this function returns.
     */
    struct mp_image *(*get_image_ts)(struct vo *vo, int imgfmt, int w, int h,
                                     int stride_align, int flags);

    /* Render the given frame. Note that this is also called when repeating
     * or redrawing frames.
     *
     * frame is freed by the caller if the callee did not assume ownership
     * of the frames, but in any case the callee can still modify the
     * contained data and references.
     *
     * Return false to signal to the core that rendering is being skipped for
     * this particular frame. vo.c will sleep for the expected duration of that
     * frame before advancing forward.
     */
    bool (*draw_frame)(struct vo *vo, struct vo_frame *frame);

    /*
     * Blit/Flip buffer to the screen. Must be called after each frame!
     */
    void (*flip_page)(struct vo *vo);

    // Optional fail-closed gate for submitting a fresh frame before its
    // original wait target. The callback must validate the current swapchain
    // generation and sync policy at the final decision point.
    bool (*can_present_early)(struct vo *vo, uint64_t generation,
                              int64_t original_target,
                              void (*wait)(struct vo *, int64_t));

    /*
     * Return presentation feedback. The implementation should not touch fields
     * it doesn't support; the info fields are preinitialized to neutral values.
     * Usually called once after flip_page(), but can be called any time.
     * The values returned by this are always relative to the last flip_page()
     * call.
     */
    void (*get_vsync)(struct vo *vo, struct vo_vsync_info *info);

    /* These optional callbacks can be provided if the GUI framework used by
     * the VO requires entering a message loop for receiving events and does
     * not call vo_wakeup() from a separate thread when there are new events.
     *
     * wait_events() will wait for new events, until the timeout expires, or the
     * function is interrupted. wakeup() is used to possibly interrupt the
     * event loop (wakeup() itself must be thread-safe, and not call any other
     * VO functions; it's the only vo_driver function with this requirement).
     * wakeup() should behave like a binary semaphore; if wait_events() is not
     * being called while wakeup() is, the next wait_events() call should exit
     * immediately.
     */
    void (*wakeup)(struct vo *vo);
    void (*wait_events)(struct vo *vo, int64_t until_time_ns);

    /*
     * Closes driver. Should restore the original state of the system.
     */
    void (*uninit)(struct vo *vo);

    // Size of private struct for automatic allocation (0 doesn't allocate)
    int priv_size;

    // If not NULL, it's copied into the newly allocated private struct.
    const void *priv_defaults;

    // List of options to parse into priv struct (requires priv_size to be set)
    // This will register them as global options (with options_prefix), and
    // copy the current value at VO creation time to the priv struct.
    const struct m_option *options;

    // All options in the above array are prefixed with this string. (It's just
    // for convenience and makes no difference in semantics.)
    const char *options_prefix;

    // Registers global options that go to a separate options struct.
    const struct m_sub_options *global_opts;
};
#line 483 "video/out/vo.h"
struct vo {
    const struct vo_driver *driver;
    struct mp_log *log; // Using e.g. "[vo/vdpau]" as prefix
    void *priv;
    struct mpv_global *global;
    // Internal diagnostic identity. vo_seq is immutable after creation;
    // draw/frame scope is owned by the VO thread and cleared after feedback.
    uint64_t pacing_vo_seq, pacing_draw_seq, pacing_frame_id;
    bool pacing_spans; // default-off CPU diagnostics, immutable on the VO thread
    uint64_t pacing_wait_seq; // precise-wait identity; diagnostic VO thread only
    union {
        struct vo_x11_state *x11;
        struct vo_w32_state *w32;
        struct vo_wayland_state *wl;
        struct vo_android_state *android;
        struct vo_drm_state *drm;
    };
    struct mp_hwdec_devices *hwdec_devs;
    struct input_ctx *input_ctx;
    struct osd_state *osd;
    struct encode_lavc_context *encode_lavc_ctx;
    struct vo_internal *in;
    struct vo_extra extra;

    // --- The following fields are generally only changed during initialization.

    bool probing;

    // --- The following fields are only changed with vo_reconfig(), and can
    //     be accessed unsynchronized (read-only).

    int config_ok;      // Last config call was successful?

    // --- The following fields are synchronized by params_mutex, most of
    //     the params are set only in the vo_reconfig and safe to read
    //     unsynchronized. Some of the parameters are updated in draw_frame,
    //     which are still safe to read in the play loop, but for correctness
    //     generic getter is protected by params_mutex.
    mp_mutex params_mutex;
    // Configured parameters (changed in vo_reconfig)
    struct mp_image_params *params;
    // Whether the VO sets the max_pq_y/avg_pq_y fields on draw_frame.
    bool has_peak_detect_values;
    // Target display parameters (VO is responsible for re-/setting)
    struct mp_image_params *target_params;

    // --- The following fields can be accessed only by the VO thread, or from
    //     anywhere _if_ the VO thread is suspended (use vo->dispatch).

    struct m_config_cache *opts_cache; // cache for ->opts
    struct mp_vo_opts *opts;

    bool want_redraw;   // redraw as soon as possible
    int64_t previous_redraw_time;

    // current window state
    int dwidth;
    int dheight;
    float monitor_par;

    // current GPU context (--vo=gpu and --vo=gpu-next only)
    const char *context_name;

    // composition swapchain (--d3d11-output-mode=composition only)
    void *display_swapchain;
};
#define _WIN32 1
#line 138 "video/out/vo.c"
struct vo_internal {
    mp_thread thread;
    struct mp_dispatch_queue *dispatch;
    struct dr_helper *dr_helper;

    // --- The following fields are protected by lock
    mp_mutex lock;
    mp_cond wakeup;
#ifdef _WIN32
    // Both handles live until the VO thread has joined. Wakeups remain
    // interruptible when the physical presentation wait uses a precise timer.
    HANDLE secondary_wakeup_event, secondary_wait_timer;
    bool secondary_wait_timer_failed;
#endif

    bool need_wakeup;
    bool terminate;

    bool hasframe;
    bool hasframe_rendered;
    bool request_redraw;            // redraw request from player to VO
    bool want_redraw;               // redraw request from VO to player
    bool send_reset;                // send VOCTRL_RESET
    bool paused;
    bool visible;
    bool wakeup_on_done;
    int queued_events;              // event mask for the user
    int internal_events;            // event mask for us

    double nominal_vsync_interval;

    double vsync_interval;
    int64_t *vsync_samples;
    int num_vsync_samples;
    int64_t num_total_vsync_samples;
    int64_t prev_vsync;
    double base_vsync;
    int drop_point;
    double estimated_vsync_interval;
    double estimated_vsync_jitter;
    bool expecting_vsync;
    int64_t num_successive_vsyncs;

    int64_t flip_queue_offset; // queue flip events at most this much in advance
    int64_t timing_offset;     // same (but from options; not VO configured)
    int64_t secondary_last_draw; // VO thread only
    struct secondary_ass_presentation secondary_presentation; // VO thread only
    struct secondary_ass_physical secondary_physical; // VO thread only
    bool secondary_sync_mode_valid, secondary_sync_mode;
    bool secondary_trace; // explicitly enabled diagnostic; never on by default
    bool secondary_schedule_trace; // numeric observation only, default off
    bool secondary_present_grid; // opt-in cadence experiment, not a default
    bool secondary_fifo_present; // isolated opt-in FIFO submission experiment
    bool secondary_present_plan; // isolated planned-base consumption experiment
    bool secondary_display_forecast; // opt-in separate eligibility/display slots
    bool secondary_fixed_forecast; // opt-in stable pose offset, default off
    bool secondary_neutral_disabled; // diagnostic A/B; default behavior unchanged
    struct secondary_ass_present_fixed_offset secondary_fixed_offset; // VO only
    bool secondary_split_budget; // opt-in measured submission envelope forecast
    bool secondary_queue_lead; // opt-in coherent native queue admission
    bool secondary_queue_stage; // opt-in early ownership, normal render admission
    struct secondary_ass_queue_stage secondary_stage_admission; // core, locked
    struct secondary_ass_queue_stage secondary_stage_pending; // bound, locked
    struct secondary_ass_stage_prefix secondary_stage_prefix; // VO thread only
    struct secondary_ass_queue_hint secondary_queue_hint; // copied under lock
    struct secondary_ass_queue_token secondary_queue_admission; // core, under lock
    struct secondary_ass_queue_token secondary_queue_pending; // under lock
    int64_t secondary_queue_resume; // deferred promotion, under lock
    struct secondary_ass_flip_budget secondary_flip_budget; // VO thread only
    struct secondary_ass_neutral_pose secondary_neutral_pose; // one-use cache pose
    struct mp_ass_pacing_record pacing_draw_record; // diagnostic, VO thread only
    struct mp_ass_pacing_record pacing_plan_record;
    int64_t pacing_cpu_end;
    int64_t secondary_render_cost;
    int64_t secondary_cost_update; // VO thread only
    int64_t secondary_gpu_cost; // VO thread only
    int64_t secondary_gpu_peak; // opt-in completion diagnostics, VO thread only
    struct secondary_ass_budget secondary_budget; // VO thread only
    int64_t secondary_redraw_cost;
    int64_t secondary_redraw_block_cost;
    int64_t secondary_next_probe;
    int64_t secondary_redraw_gpu_cost; // VO thread only
    int64_t secondary_redraw_cpu_cost; // VO thread only
    struct secondary_ass_budget secondary_redraw_budget; // VO thread only
    struct secondary_ass_budget secondary_redraw_block_budget; // VO thread only

    int64_t delayed_count;
    int64_t drop_count;
    bool dropped_frame;             // the previous frame was dropped

    struct vo_frame *current_frame; // last frame queued to the VO

    int64_t wakeup_pts;             // time at which to pull frame from decoder

    bool rendering;                 // true if an image is being rendered
    struct vo_frame *frame_queued;  // should be drawn next
    int req_frames;                 // VO's requested value of num_frames
    int frame_refs;                 // max frames the VO may reference at once
    uint64_t current_frame_id;

    double display_fps;
    double reported_display_fps;

    struct stats_ctx *stats;
};
#line 388 "video/out/vo.c"
struct secondary_ass_grid_task {
    struct secondary_ass_physical_point point;
    uint64_t epoch, current_id, queued_id;
    int64_t divisor;
    int64_t interval, deadline, submit_time;
    int delay;
    double rate;
    bool plan_enabled;
    bool recovery_probe; // one bounded fixed-offset sample, not a general bypass
    struct secondary_ass_present_plan plan;
    struct secondary_ass_queue_stage stage;
};
double osd_get_secondary_refresh(struct osd_state *osd);
int64_t osd_get_secondary_physical_sample_divisor(struct osd_state *osd);
int64_t osd_get_secondary_physical_next_sample_slot(struct osd_state *osd);
int64_t osd_get_secondary_physical_next_sample_time(struct osd_state *osd);
int64_t osd_get_secondary_next_sample_time(struct osd_state *osd);
double osd_get_secondary_clock_rate(struct osd_state *osd);
void osd_hold_secondary_sample(struct osd_state *osd);
void osd_reset_secondary_clock(struct osd_state *osd);
struct secondary_ass_sample_snapshot osd_get_secondary_sample_snapshot(struct osd_state *osd);

static unsigned checks, failures, wakeups, core_wakeups, free_calls;
static int lock_depth;
static int64_t clock_ns;
static mp_mutex *tracked_lock;
static double fixture_rate;
static int64_t fixture_divisor=2;
static struct secondary_ass_sample_snapshot fixture_snapshot;
static bool fixture_v30_new_osd_scope;
static unsigned fixture_v30_new_osd_checks;
static struct secondary_ass_clock fixture_clock;
static struct secondary_ass_sampler fixture_sampler;
static bool fixture_live_sampler,fixture_sample_forced;
static unsigned feedback_frames,early_prepare_positive;
static unsigned pose_holds,pose_set_calls;
static struct secondary_ass_grid_task actual_outer_task;
static struct mp_ass_pacing_record recorded;
static struct mp_ass_pacing_record v29_records[32];
static uint32_t v29_record_kind[32];static unsigned v29_record_count;
static bool v29_clock_advances;static unsigned v29_clock_reads,v29_advance_after;
static int64_t v29_clock_after;
#define CHECK(x) do { checks++; if (!(x)) { failures++; if(failures<=20) \
 fprintf(stderr,"check failed %u:%s:%d:%s\n",checks,__FILE__,__LINE__,#x); } } while(0)
static int64_t mp_time_ns(void) {
 if(v29_clock_advances && v29_clock_reads++>=v29_advance_after)return v29_clock_after;
 return clock_ns; }
static void AcquireSRWLockExclusive(SRWLOCK *lock) {
 CHECK(!*lock);*lock=(void*)1;if(lock==tracked_lock)lock_depth++; }
static void ReleaseSRWLockExclusive(SRWLOCK *lock) {
 CHECK(*lock==(void*)1);*lock=NULL;if(lock==tracked_lock)lock_depth--; }
static void WakeAllConditionVariable(CONDITION_VARIABLE *cond) {
 (void)cond;CHECK(lock_depth==1);wakeups++; }
static int SetEvent(HANDLE event) { (void)event;return 1; }
static void integration_log(const char *fmt, ...) { (void)fmt; }
#define MP_INFO(obj, ...) integration_log(__VA_ARGS__)
static void fixture_free(void *p) { if(p)free_calls++; }
#define talloc_free(p) fixture_free(p)
double osd_get_secondary_refresh(struct osd_state *osd) {
 (void)osd;CHECK(lock_depth==0);return fixture_rate; }
double osd_get_secondary_clock_rate(struct osd_state *osd) {
 (void)osd;CHECK(lock_depth==0);return fixture_rate; }
void osd_hold_secondary_sample(struct osd_state *osd) {
 (void)osd;pose_holds++; }
int64_t osd_get_secondary_physical_sample_divisor(struct osd_state *osd) {
 (void)osd;CHECK(lock_depth==0);return fixture_divisor; }
void osd_reset_secondary_clock(struct osd_state *osd) { (void)osd; }
struct secondary_ass_sample_snapshot osd_get_secondary_sample_snapshot(struct osd_state *osd) {
 (void)osd;
 // Retain the same live lock assertion for the newly added OSD invocation.
 // Its count is separate; every old CHECK and failure remains unchanged.
 if(fixture_v30_new_osd_scope) {
  fixture_v30_new_osd_checks++;
  if(lock_depth!=0){failures++;fprintf(stderr,"check failed: V30 new OSD lock\n");}
 } else { CHECK(lock_depth==0); }
 if(!fixture_live_sampler)return fixture_snapshot;
 struct secondary_ass_sampler *s=&fixture_sampler;
 struct secondary_ass_sample_snapshot sample={
  .valid=s->valid && s->physical_slots && fixture_clock.valid && !fixture_clock.display_synced,
  .held=false,.force=s->force,.rate=fixture_rate,.speed=fixture_clock.speed,
  .requested_speed=fixture_clock.speed,.epoch=s->epoch,.divisor=s->divisor,
  .next_slot=secondary_ass_sampler_next_slot(s),.next_wall=secondary_ass_sampler_next_wall(s),
  .phase_wall=s->phase_wall,.phase_slot=s->phase_slot,.interval=s->physical_interval,
  .origin_slot=s->origin_slot,.sample_slot=secondary_ass_sampler_next_slot(s)>s->divisor && s->divisor>0
   ? secondary_ass_sampler_next_slot(s)-s->divisor:0,
  .display_forecast=s->display_forecast,.sample_forced=fixture_sample_forced};
 sample.valid=sample.valid && !sample.force && s->rate==sample.rate;
 return sample;
}
int64_t osd_get_secondary_physical_next_sample_slot(struct osd_state *osd) {
 return osd_get_secondary_sample_snapshot(osd).next_slot; }
int64_t osd_get_secondary_physical_next_sample_time(struct osd_state *osd) {
 return osd_get_secondary_sample_snapshot(osd).next_wall; }
int64_t osd_get_secondary_next_sample_time(struct osd_state *osd) {
 return osd_get_secondary_sample_snapshot(osd).next_wall; }
bool mp_ass_pacing_enabled(struct mpv_global *global) { (void)global;return true; }
void mp_ass_pacing_record(struct mpv_global *global, uint32_t kind,
                         const struct mp_ass_pacing_record *record) {
 (void)global;recorded=*record;
 if(v29_record_count<32){v29_record_kind[v29_record_count]=kind;
 v29_records[v29_record_count++]=*record;} }
static void core_callback(void *ctx) { (void)ctx;core_wakeups++; }
static bool can_early(struct vo *vo,uint64_t generation,int64_t target,
                      void (*wait)(struct vo *,int64_t)) {
 (void)vo;(void)generation;(void)target;(void)wait;return true; }

static bool secondary_set_presentation(struct vo *vo,
    struct secondary_ass_physical_point point, int64_t fallback,
    int64_t interval, int64_t submit, bool quiet_output, bool forecast,
    const struct secondary_ass_present_plan *plan)
{
 (void)vo;(void)point;(void)fallback;(void)interval;(void)submit;
 (void)quiet_output;(void)forecast;(void)plan;
 pose_set_calls++;return false;
}

#line 49 "osdep/threads-win32.h"
static inline int mp_mutex_lock(mp_mutex *mutex)
{
    AcquireSRWLockExclusive(mutex);
    return 0;
}
#line 60 "osdep/threads-win32.h"
static inline int mp_mutex_unlock(mp_mutex *mutex)
{
    ReleaseSRWLockExclusive(mutex);
    return 0;
}
#line 79 "osdep/threads-win32.h"
static inline int mp_cond_broadcast(mp_cond *cond)
{
    WakeAllConditionVariable(cond);
    return 0;
}
static int64_t secondary_stage_budget_resume(struct vo *vo,
    const struct secondary_ass_queue_stage *stage, double rate, int64_t now);
#line 245 "video/out/vo.c"
static uint32_t secondary_record_tag(const char *text)
{
    uint32_t tag = UINT32_C(2166136261);
    for (; text && *text; text++)
        tag = (tag ^ (uint8_t)*text) * UINT32_C(16777619);
    return tag;
}
#line 403 "video/out/vo.c"
static bool secondary_stage_owner(struct vo *vo,
                                  const struct secondary_ass_queue_stage *stage)
{
    struct vo_internal *in = vo->in;
    return in->secondary_queue_stage && stage->valid &&
        in->current_frame && in->frame_queued && !in->paused && in->hasframe &&
        !in->send_reset && !in->dropped_frame &&
        !(in->queued_events & VO_EVENT_LIVE_RESIZING) &&
        !(vo->driver->caps & (VO_CAP_NORETAIN | VO_CAP_UNTIMED)) &&
        !in->current_frame->still && !in->current_frame->display_synced &&
        !in->frame_queued->still && !in->frame_queued->display_synced &&
        stage->max_lead == MPMIN(in->timing_offset, MP_TIME_MS_TO_NS(50)) &&
        secondary_ass_queue_stage_current(stage, in->current_frame->frame_id,
            in->frame_queued->frame_id, in->frame_queued->pts,
            in->flip_queue_offset);
}
#line 423 "video/out/vo.c"
static bool secondary_stage_cache_current(struct vo *vo,
    const struct secondary_ass_queue_stage *stage, int64_t now,
    int64_t interval, int64_t block_cost, double rate)
{
    struct vo_internal *in = vo->in;
    const struct secondary_ass_queue_stage *pending = &in->secondary_stage_pending;
    block_cost = block_cost > 0 ? block_cost : interval;
    return secondary_stage_owner(vo, stage) && secondary_stage_owner(vo, pending) &&
        stage->old_lead == pending->old_lead &&
        stage->max_lead == pending->max_lead && stage->resume == pending->resume &&
        in->secondary_queue_resume == stage->resume && now < stage->resume &&
        secondary_ass_budget_affordable(in->secondary_render_cost,
            in->secondary_redraw_cost, in->frame_queued->duration, interval) &&
        secondary_ass_budget_before_deadline(now,
            secondary_stage_budget_resume(vo, stage, rate, now), 0, block_cost,
                                             MP_TIME_MS_TO_NS(1));
}
#line 444 "video/out/vo.c"
static int64_t secondary_stage_budget_resume(struct vo *vo,
    const struct secondary_ass_queue_stage *stage, double rate, int64_t now)
{
    struct vo_internal *in = vo->in;
    int64_t lead = stage->max_lead;
    if (isfinite(rate) && rate > 0 && rate >= 1e9 / INT64_MAX &&
        in->current_frame)
    {
        int64_t interval = MPMAX(MP_TIME_S_TO_NS(1.0 / rate), in->vsync_interval);
        int64_t duration = in->current_frame->duration;
        bool affordable = secondary_ass_budget_affordable(in->secondary_render_cost,
            in->secondary_redraw_cost, duration, interval);
        bool probe = secondary_ass_budget_probe_due(in->secondary_render_cost,
            duration, interval, now, in->secondary_next_probe);
        if (affordable || probe) {
            int64_t minimum = MP_TIME_MS_TO_NS(2);
            if (isfinite(in->reported_display_fps) && in->reported_display_fps > 0 &&
                in->reported_display_fps >= 1e9 / (INT64_MAX - minimum))
                minimum += MP_TIME_S_TO_NS(1.0 / in->reported_display_fps);
            int64_t cost = in->secondary_render_cost;
            if (cost >= 0 && cost <= INT64_MAX - MP_TIME_MS_TO_NS(2))
                lead = MPMIN(lead, MPMAX(minimum, cost + MP_TIME_MS_TO_NS(2)));
        }
    }
    return MPMIN(stage->resume, stage->due - lead);
}
#line 471 "video/out/vo.c"
static bool secondary_plan_enabled(struct vo *vo, bool display_synced,
                                   int64_t divisor)
{
    // Restrict this experiment to an established integer physical sampler.
    // Arbitrary manual cadence and no-grid scheduling keep the legacy path.
    return vo->in->secondary_present_plan && vo->in->secondary_present_grid &&
        !display_synced && divisor > 0;
}
#line 480 "video/out/vo.c"
static bool secondary_forecast_enabled(struct vo *vo, bool display_synced,
                                       int64_t divisor)
{
    return vo->in->secondary_display_forecast &&
        secondary_plan_enabled(vo, display_synced, divisor);
}
#line 487 "video/out/vo.c"
static int secondary_fixed_forecast_offset(struct vo *vo,
    struct secondary_ass_physical_point logical, int64_t divisor, double rate)
{
    struct vo_internal *in = vo->in;
    return secondary_ass_present_fixed_offset_get(&in->secondary_fixed_offset,
        &in->secondary_physical, logical, divisor, rate);
}
#line 495 "video/out/vo.c"
static struct secondary_ass_present_plan secondary_forecast_plan(struct vo *vo,
    struct secondary_ass_physical_point logical, int64_t divisor, double rate)
{
    if (vo->in->secondary_fixed_forecast) {
        if (vo->in->secondary_physical.outlier_pending ||
            !vo->in->secondary_physical.sync_segment_consistent)
            return (struct secondary_ass_present_plan){.display_forecast = true};
        return secondary_ass_present_plan_make_fixed_forecast(
            &vo->in->secondary_physical, logical,
            secondary_fixed_forecast_offset(vo, logical, divisor, rate));
    }
    return secondary_ass_present_plan_make_forecast(&vo->in->secondary_physical,
                                                   logical);
}
#line 510 "video/out/vo.c"
static struct secondary_ass_present_plan secondary_forecast_fresh_plan(
    struct vo *vo, int64_t ready, struct secondary_ass_physical_point logical,
    int64_t divisor, double rate)
{
    if (!vo->in->secondary_fixed_forecast)
        return secondary_ass_present_plan_fresh_forecast(&vo->in->secondary_physical,
                                                         ready, logical);
    if (!logical.slot && !logical.wall) {
        struct secondary_ass_physical view =
            secondary_ass_present_plan_view(&vo->in->secondary_physical);
        logical = secondary_ass_physical_predict_point(&view, ready);
    }
    return secondary_forecast_plan(vo, logical, divisor, rate);
}
#line 525 "video/out/vo.c"
static struct secondary_ass_physical_point secondary_forecast_next(struct vo *vo,
    int64_t first_slot, int64_t divisor, int64_t now, double rate)
{
    struct secondary_ass_physical *p = &vo->in->secondary_physical;
    if (!vo->in->secondary_fixed_forecast)
        return secondary_ass_present_plan_cache_next_forecast(p, first_slot,
                                                              divisor, now);
    struct secondary_ass_physical_point first =
        secondary_ass_physical_point_at(p, first_slot);
    int offset = secondary_fixed_forecast_offset(vo, first, divisor, rate);
    if (offset < 0) {
        // Before the first valid capture, choose one future G on the original
        // lattice. Subsequent choices never consult a changing historical H.
        first = secondary_ass_present_plan_cache_next_forecast(p, first_slot,
                                                               divisor, now);
        offset = secondary_fixed_forecast_offset(vo, first, divisor, rate);
    }
    return secondary_ass_present_plan_cache_next_fixed_forecast(p, first_slot,
                                                               divisor, now, offset);
}
#line 563 "video/out/vo.c"
static struct secondary_ass_present_plan secondary_cache_plan(struct vo *vo,
    struct secondary_ass_physical_point logical, int64_t divisor, double rate)
{
    return vo->in->secondary_display_forecast
        ? secondary_forecast_plan(vo, logical, divisor, rate)
        : secondary_ass_present_plan_cache(&vo->in->secondary_physical, logical);
}
#line 571 "video/out/vo.c"
static void secondary_capture_grid_plan(struct secondary_ass_grid_task *task)
{
    if (task->plan_enabled && task->plan.valid && task->plan.display_forecast) {
        task->deadline = task->plan.deadline;
        task->submit_time = task->plan.submit;
    }
}
#line 579 "video/out/vo.c"
static int64_t secondary_cache_block_cost(struct vo *vo, bool planned_audio)
{
    struct vo_internal *in = vo->in;
    if (!in->secondary_split_budget || !planned_audio ||
        !in->secondary_physical.success_contiguous)
        return in->secondary_redraw_block_cost;
    return secondary_ass_flip_budget_cost(&in->secondary_flip_budget,
        in->secondary_physical.epoch, in->secondary_physical.success_generation,
        in->secondary_physical.success_last_id, in->secondary_redraw_cost,
        in->secondary_redraw_block_cost);
}
#line 591 "video/out/vo.c"
static int64_t secondary_cache_post_cpu_cost(struct vo *vo, bool planned_audio)
{
    struct vo_internal *in = vo->in;
    if (!in->secondary_split_budget || !planned_audio ||
        !in->secondary_physical.success_contiguous)
        return 0;
    return secondary_ass_flip_budget_post_cpu_cost(&in->secondary_flip_budget,
        in->secondary_physical.epoch, in->secondary_physical.success_generation,
        in->secondary_physical.success_last_id);
}
#line 656 "video/out/vo.c"
static void secondary_trace_flip_window(struct vo *vo, unsigned location,
    uint64_t current_id,
    bool baseline, int64_t now, int64_t prepare, int64_t earliest,
    const struct secondary_ass_present_plan *plan, int64_t video_deadline,
    int64_t redraw_cost, int64_t post_cpu_cost, int64_t fresh_cost,
    int64_t margin, const struct secondary_ass_flip_window *window)
{
    if (!mp_ass_pacing_enabled(vo->global))
        return;
    // Scheduling decisions have no new draw scope. location 1 is the queued
    // prepass; 2 is the outer retained-frame scheduler. All inputs below are
    // the exact values used by the helper, including the immutable S/D/F.
    // CPUdone and reserved_end are derivable from these inputs; neither the
    // outcome nor post_cpu_done proves GPU Ready or actual Display.
    struct mp_ass_pacing_record record = {
        .event_ns = now, .vo_seq = vo->pacing_vo_seq,
        .frame_id = current_id,
        .epoch = plan->epoch, .generation = plan->generation,
        .flags = (uint64_t)baseline | ((uint64_t)window->valid << 1),
        .v = {350, location, now, prepare, redraw_cost, plan->submit,
            post_cpu_cost, fresh_cost, video_deadline, plan->deadline,
            earliest, baseline, margin, window->outcome,
            window->submit, window->post_cpu_done},
    };
    mp_ass_pacing_record(vo->global, MP_ASS_PACING_SPAN, &record);
}
#line 683 "video/out/vo.c"
static const struct secondary_ass_physical *secondary_planning_state(
    struct vo *vo, bool display_synced, int64_t divisor,
    struct secondary_ass_physical *storage)
{
    if (secondary_plan_enabled(vo, display_synced, divisor)) {
        *storage = secondary_ass_present_plan_view(&vo->in->secondary_physical);
        return storage;
    }
    return &vo->in->secondary_physical;
}
#line 694 "video/out/vo.c"
static void secondary_trace_plan(struct vo *vo, bool fresh,
                                const struct secondary_ass_present_plan *plan)
{
    if (vo->in->secondary_trace)
    MP_INFO(vo, "native-ass-plan: fresh=%d enabled=1 base_slot=%"PRId64
        " base_ns=%"PRId64" target_slot=%"PRId64" target_ns=%"PRId64
        " submit_ns=%"PRId64" deadline_ns=%"PRId64" fifo_lower_slot=%"PRId64
        " fifo_known=%d epoch=%"PRIu64" generation=%"PRIu64
        " historical_delay=%d fallback_submit_ns=%"PRId64
        " lifecycle_safe_wait_ns=%"PRId64" valid=%d\n",
        fresh, plan->base.slot, plan->base.wall, plan->target.slot,
        plan->target.wall, plan->submit, plan->deadline, plan->fifo_lower,
        plan->fifo_known, plan->epoch, plan->generation, plan->historical_delay,
        plan->fallback_submit, plan->lifecycle_safe_wait, plan->valid);
}
#line 710 "video/out/vo.c"
static void secondary_trace_plan_missed(struct vo *vo, const char *reason,
    const char *stage, const struct secondary_ass_present_plan *plan)
{
    bool actual_draw = strcmp(stage, "after-flip") == 0;
    // A missed captured task cannot close the successful stage prefix.
    if (vo->in->secondary_queue_stage)
        secondary_ass_stage_prefix_invalidate(&vo->in->secondary_stage_prefix);
    if (mp_ass_pacing_enabled(vo->global)) {
        struct mp_ass_pacing_record record = {
            .event_ns = mp_time_ns(), .vo_seq = vo->pacing_vo_seq,
            .draw_seq = vo->pacing_draw_seq, .frame_id = vo->pacing_frame_id,
            .epoch = plan->epoch, .generation = plan->generation,
            .flags = (uint64_t)actual_draw,
            .v = {plan->target.slot, plan->target.wall, plan->base.slot,
                plan->base.wall, plan->deadline, secondary_record_tag(reason),
                secondary_record_tag(stage)},
        };
        mp_ass_pacing_record(vo->global, MP_ASS_PACING_MISS, &record);
    }
    if (vo->in->secondary_trace)
    MP_INFO(vo, "native-ass-plan-missed: reason=%s stage=%s actual_draw=%d "
        "original_target_slot=%"PRId64" original_target_ns=%"PRId64
        " base_slot=%"PRId64" base_ns=%"PRId64" epoch=%"PRIu64
        " generation=%"PRIu64" now_ns=%"PRId64" deadline_ns=%"PRId64"\n",
        reason, stage, actual_draw, plan->target.slot, plan->target.wall,
        plan->base.slot, plan->base.wall, plan->epoch, plan->generation,
        mp_time_ns(), plan->deadline);
}
#line 739 "video/out/vo.c"
static const char *secondary_plan_stale_reason(
    const struct secondary_ass_physical *p,
    const struct secondary_ass_present_plan *plan)
{
    if (p->epoch != plan->epoch || p->success_generation != plan->generation)
        return "epoch_or_generation";
    struct secondary_ass_physical view = secondary_ass_present_plan_view(p);
    int64_t lower = secondary_ass_physical_fifo_lower_bound(&view);
    if (lower > 0 && lower > plan->target.slot)
        return "fifo_after_target";
    if (plan->base.slot > 0 && plan->base.slot <= p->last_base_slot)
        return "occupied_base";
    return "plan_unavailable";
}
#line 800 "video/out/vo.c"
static void read_opts(struct vo *vo)
{
    struct vo_internal *in = vo->in;

    mp_mutex_lock(&in->lock);
    int64_t timing_offset = (uint64_t)(MP_TIME_S_TO_NS(vo->opts->timing_offset));
    if (in->secondary_queue_lead && in->timing_offset != timing_offset) {
        in->secondary_queue_hint.valid = false;
        in->secondary_queue_admission.valid = false;
        struct secondary_ass_queue_token *token = &in->secondary_queue_pending;
        token->valid = false;
        if (token->old_admission > 0 && timing_offset >= 0 &&
            timing_offset < token->old_lead)
        {
            // A smaller configured cap moves baseline admission later. Keep
            // F intact and return the early queued image to that later cap.
            token->old_admission = token->fresh_due - timing_offset;
        }
    }
    if (in->secondary_queue_stage && in->timing_offset != timing_offset) {
        secondary_ass_queue_stage_clear(&in->secondary_stage_admission);
        secondary_ass_queue_stage_clear(&in->secondary_stage_pending);
        in->secondary_queue_resume = 0;
    }
    in->timing_offset = timing_offset;
    mp_mutex_unlock(&in->lock);
}
#line 998 "video/out/vo.c"
static void wakeup_core(struct vo *vo)
{
    vo->extra.wakeup_cb(vo->extra.wakeup_ctx);
}
#line 1005 "video/out/vo.c"
static void reset_vsync_timings(struct vo *vo)
{
    struct vo_internal *in = vo->in;
    in->drop_point = 0;
    in->base_vsync = 0;
    in->expecting_vsync = false;
    in->num_successive_vsyncs = 0;
}
#line 1317 "video/out/vo.c"
static void forget_frames(struct vo *vo)
{
    struct vo_internal *in = vo->in;
    in->hasframe = false;
    in->hasframe_rendered = false;
    in->drop_count = 0;
    in->delayed_count = 0;
    talloc_free(in->frame_queued);
    in->frame_queued = NULL;
    in->secondary_queue_hint = (struct secondary_ass_queue_hint){0};
    in->secondary_queue_admission = (struct secondary_ass_queue_token){0};
    in->secondary_queue_pending = (struct secondary_ass_queue_token){0};
    secondary_ass_queue_stage_clear(&in->secondary_stage_admission);
    secondary_ass_queue_stage_clear(&in->secondary_stage_pending);
    in->secondary_queue_resume = 0;
    in->current_frame_id += VO_MAX_REQ_FRAMES + 1;
    // don't unref current_frame; we always want to be able to redraw it
    if (in->current_frame) {
        in->current_frame->num_vsyncs = 0; // but reset future repeats
        in->current_frame->display_synced = false; // mark discontinuity
    }
}
#line 1481 "video/out/vo.c"
static void wakeup_locked(struct vo *vo)
{
    struct vo_internal *in = vo->in;

    mp_cond_broadcast(&in->wakeup);
#ifdef _WIN32
    if (in->secondary_wakeup_event)
        SetEvent(in->secondary_wakeup_event);
#endif
    if (vo->driver->wakeup)
        vo->driver->wakeup(vo);
    in->need_wakeup = true;
}
#line 1506 "video/out/vo.c"
static int64_t get_current_frame_end(struct vo *vo)
{
    struct vo_internal *in = vo->in;
    if (!in->current_frame)
        return -1;
    return in->current_frame->pts + MPMAX(in->current_frame->duration, 0);
}
#line 1514 "video/out/vo.c"
static int64_t get_display_synced_frame_end(struct vo *vo)
{
    struct vo_internal *in = vo->in;
    mp_assert(!in->frame_queued);
    int64_t res = 0;
    if (in->base_vsync && in->vsync_interval > 1 && in->current_frame) {
        res = in->base_vsync;
        int extra = !!in->rendering;
        res += (in->current_frame->num_vsyncs + extra) * in->vsync_interval;
        if (!in->current_frame->display_synced)
            res = 0;
    }
    return res;
}
#line 1529 "video/out/vo.c"
static bool still_displaying(struct vo *vo)
{
    struct vo_internal *in = vo->in;
    bool working = in->rendering || in->frame_queued;
    if (working)
        goto done;

    int64_t frame_end = get_display_synced_frame_end(vo);
    if (frame_end > 0) {
        working = frame_end > in->base_vsync;
        goto done;
    }

    frame_end = get_current_frame_end(vo);
    if (frame_end < 0)
        goto done;
    working = mp_time_ns() < frame_end;

done:
    return working && in->hasframe;
}
#line 1581 "video/out/vo.c"
bool vo_is_ready_for_frame(struct vo *vo, int64_t next_pts)
{
    struct vo_internal *in = vo->in;
    double secondary_rate = osd_get_secondary_refresh(vo->osd);
    struct secondary_ass_sample_snapshot queue_sample = in->secondary_queue_lead
        ? osd_get_secondary_sample_snapshot(vo->osd)
        : (struct secondary_ass_sample_snapshot){0};
    mp_mutex_lock(&in->lock);
    in->secondary_queue_admission = (struct secondary_ass_queue_token){0};
    secondary_ass_queue_stage_clear(&in->secondary_stage_admission);
    bool r = vo->config_ok && !in->frame_queued &&
             (!in->current_frame || in->current_frame->num_vsyncs < 1);
    if (r && next_pts >= 0) {
        // Don't show the frame too early - it would basically freeze the
        // display by disallowing OSD redrawing or VO interaction.
        // Actually render the frame at earliest the given offset before target
        // time.
        // Leave time between low-fps video frames for animated secondary ASS.
        // This changes queue lead time only, not video presentation timestamps.
        int64_t lead = in->timing_offset;
        int64_t now = mp_time_ns();
        int64_t interval = secondary_rate > 0
            ? MPMAX(MP_TIME_S_TO_NS(1.0 / secondary_rate), in->vsync_interval) : 0;
        int64_t duration = in->current_frame && !in->current_frame->display_synced
            ? in->current_frame->duration : 0;
        bool affordable = secondary_ass_budget_affordable(in->secondary_render_cost,
            in->secondary_redraw_cost, duration, interval);
        bool probe = secondary_ass_budget_probe_due(in->secondary_render_cost,
            duration, interval, now, in->secondary_next_probe);
        if (secondary_rate > 0 && (affordable || probe)) {
            int64_t minimum = MP_TIME_S_TO_NS(0.002);
            if (in->reported_display_fps > 0)
                minimum += MP_TIME_S_TO_NS(1.0 / in->reported_display_fps);
            lead = MPMIN(lead, MPMAX(minimum,
                in->secondary_render_cost + MP_TIME_S_TO_NS(0.002)));
        }
        if (in->secondary_queue_stage && isfinite(secondary_rate) &&
            secondary_rate > 0 && affordable && !probe && in->hasframe &&
            in->current_frame && !in->current_frame->still &&
            !in->current_frame->display_synced && !in->paused &&
            !in->dropped_frame && !in->send_reset &&
            !(in->queued_events & VO_EVENT_LIVE_RESIZING) &&
            !(vo->driver->caps & (VO_CAP_NORETAIN | VO_CAP_UNTIMED)))
        {
            struct secondary_ass_queue_stage stage = secondary_ass_queue_stage_make(
                in->current_frame->frame_id, next_pts, in->flip_queue_offset,
                lead, in->timing_offset);
            if (stage.valid) {
                lead = stage.max_lead;
                if (now >= stage.admission)
                    in->secondary_stage_admission = stage;
            }
        }
        if (in->secondary_queue_lead && affordable && !probe &&
            in->current_frame && !in->current_frame->still && !in->paused &&
            queue_sample.rate == secondary_rate &&
            in->current_frame->frame_id == in->secondary_queue_hint.retained_id &&
            in->hasframe && !in->dropped_frame && !in->send_reset &&
            !(in->queued_events & VO_EVENT_LIVE_RESIZING) &&
            !(vo->driver->caps & (VO_CAP_NORETAIN | VO_CAP_UNTIMED)) &&
            vo->driver->can_present_early &&
            in->flip_queue_offset >= 0 &&
            next_pts > in->flip_queue_offset)
        {
            struct secondary_ass_queue_token token = secondary_ass_queue_lead_make(
                &in->secondary_queue_hint, &queue_sample,
                next_pts - in->flip_queue_offset, lead, in->timing_offset,
                in->secondary_redraw_cost);
            if (token.valid && now < token.old_admission) {
                lead = token.fresh_due - token.admission;
                // An early check must schedule the new admission boundary,
                // but it does not grant an ownership token until that wake.
                if (now >= token.admission)
                    in->secondary_queue_admission = token;
            }
        }
        next_pts -= lead;
        next_pts -= in->flip_queue_offset;
        if (next_pts > now)
            r = false;
        if (!in->wakeup_pts || next_pts < in->wakeup_pts) {
            in->wakeup_pts = next_pts;
            // If we have to wait, update the vo thread's timer.
            if (!r)
                wakeup_locked(vo);
        }
    }
    mp_mutex_unlock(&in->lock);
    return r;
}
#line 1685 "video/out/vo.c"
void vo_queue_frame(struct vo *vo, struct vo_frame *frame)
{
    struct vo_internal *in = vo->in;
    struct secondary_ass_sample_snapshot queue_sample = in->secondary_queue_lead
        ? osd_get_secondary_sample_snapshot(vo->osd)
        : (struct secondary_ass_sample_snapshot){0};
    mp_mutex_lock(&in->lock);
    mp_assert(vo->config_ok && !in->frame_queued &&
           (!in->current_frame || in->current_frame->num_vsyncs < 1));
    // Copy scalar identity under the VO lock; the frame can be freed as
    // soon as we unlock. The core thread never reads VO physical state.
    bool record_queue = mp_ass_pacing_enabled(vo->global);
    bool trace_queue = in->secondary_schedule_trace || record_queue;
    int64_t queue_ns = trace_queue ? mp_time_ns() : 0;
    int64_t queue_pts = trace_queue ? frame->pts : 0;
    int64_t queue_duration = trace_queue ? frame->duration : 0;
    bool queue_ds = trace_queue && frame->display_synced;
    uint64_t retained_id = trace_queue && in->current_frame
        ? in->current_frame->frame_id : 0;
    in->secondary_queue_pending = in->secondary_queue_admission;
    in->secondary_queue_admission = (struct secondary_ass_queue_token){0};
    in->secondary_queue_resume = 0;
    struct secondary_ass_queue_token *queue_token = &in->secondary_queue_pending;
    if (queue_token->valid) {
        int64_t due = in->flip_queue_offset >= 0 && frame->pts > in->flip_queue_offset
            ? frame->pts - in->flip_queue_offset : 0;
        bool coherent = !frame->display_synced && !frame->still &&
            frame->duration >= queue_token->sample.divisor * queue_token->plan.interval &&
            secondary_ass_budget_affordable(in->secondary_render_cost,
                in->secondary_redraw_cost, frame->duration,
                MPMAX(MP_TIME_S_TO_NS(1.0 / queue_token->sample.rate),
                      queue_token->plan.interval)) &&
            in->current_frame && !in->paused && !in->send_reset &&
            !(in->queued_events & VO_EVENT_LIVE_RESIZING) &&
            secondary_ass_sample_snapshot_equal(&queue_token->sample, &queue_sample) &&
            queue_token->retained_id == in->current_frame->frame_id &&
            queue_token->fresh_due == due;
        queue_token->valid = coherent;
        if (!coherent && due > queue_token->old_lead)
            queue_token->old_admission = due - queue_token->old_lead;
        if (frame->display_synced || due <= queue_token->old_lead)
            *queue_token = (struct secondary_ass_queue_token){0};
    }
    in->hasframe = true;
    frame->frame_id = ++(in->current_frame_id);
    uint64_t queued_id = trace_queue ? frame->frame_id : 0;
    in->frame_queued = frame;
    if (in->secondary_queue_stage) {
        struct secondary_ass_queue_stage stage = secondary_ass_queue_stage_bind(
            &in->secondary_stage_admission,
            in->current_frame ? in->current_frame->frame_id : 0,
            frame->frame_id, frame->pts, in->flip_queue_offset);
        // The core proposal was not immutable. Only this accepted frame's
        // real PTS establishes F, and only within the original queue cap.
        bool eligible = stage.valid && !frame->display_synced && !frame->still &&
            in->current_frame && !in->current_frame->still &&
            !in->current_frame->display_synced && in->hasframe && !in->paused &&
            !in->dropped_frame && !in->send_reset &&
            !(in->queued_events & VO_EVENT_LIVE_RESIZING) &&
            !(vo->driver->caps & (VO_CAP_NORETAIN | VO_CAP_UNTIMED)) &&
            mp_time_ns() >= stage.admission;
        in->secondary_stage_pending = eligible ? stage
            : (struct secondary_ass_queue_stage){0};
        secondary_ass_queue_stage_clear(&in->secondary_stage_admission);
        // Publish the hold immediately: the current draw may still be in
        // flight and its first outer iteration must see the parked image.
        if (eligible)
            in->secondary_queue_resume = stage.resume;
    }
    struct secondary_ass_queue_token recorded_queue_token = *queue_token;
    struct secondary_ass_queue_stage recorded_stage = in->secondary_stage_pending;
    in->wakeup_pts = frame->display_synced
                   ? 0 : frame->pts + MPMAX(frame->duration, 0);
    wakeup_locked(vo);
    mp_mutex_unlock(&in->lock);
    if (record_queue) {
        struct mp_ass_pacing_record record = {
            .event_ns = queue_ns, .vo_seq = vo->pacing_vo_seq,
            .frame_id = queued_id, .flags = queue_ds,
            .v = {(int64_t)retained_id, queue_pts, queue_duration,
                recorded_queue_token.old_admission, recorded_queue_token.admission,
                recorded_queue_token.plan.target.slot, recorded_queue_token.valid,
                recorded_stage.valid, recorded_stage.admission, recorded_stage.resume,
                recorded_stage.due, recorded_stage.offset, recorded_stage.old_lead,
                recorded_stage.max_lead},
        };
        mp_ass_pacing_record(vo->global, MP_ASS_PACING_QUEUE, &record);
    }
    if (in->secondary_schedule_trace)
        MP_INFO(vo, "native-ass-queue-trace: frame=%"PRIu64
            " retained_id=%"PRIu64" queue_ns=%"PRId64
            " pts_ns=%"PRId64" duration_ns=%"PRId64" ds=%d\n",
            queued_id, retained_id, queue_ns, queue_pts, queue_duration, queue_ds);
}
#line 1867 "video/out/vo.c"
static struct secondary_ass_physical_point secondary_next_sample(struct vo *vo,
                                                                 int64_t divisor)
{
    struct secondary_ass_physical storage;
    bool ds = vo->in->current_frame && vo->in->current_frame->display_synced;
    const struct secondary_ass_physical *p = secondary_planning_state(vo, ds, divisor, &storage);
    struct secondary_ass_sample_snapshot sample =
        osd_get_secondary_sample_snapshot(vo->osd);
    // Refresh counts start a new namespace after a real lifecycle change.
    // An old sampler slot projected onto that namespace can be seconds ahead.
    // Let the next identified fresh presentation initialize the new sampler.
    if (sample.epoch && sample.epoch != p->epoch)
        return (struct secondary_ass_physical_point){0};
    int64_t slot = osd_get_secondary_physical_next_sample_slot(vo->osd);
    if (slot > 0)
        return secondary_ass_physical_point_at(p, slot);
    // An arbitrary manual cadence can still use the wall-time fallback. Map
    // its opportunity to an actual slot before checking queue occupancy.
    int64_t wall = osd_get_secondary_physical_next_sample_time(vo->osd);
    if (wall <= 0 || !p->phase || !p->interval)
        return (struct secondary_ass_physical_point){0};
    int64_t delta = wall - p->phase;
    int64_t steps = delta / p->interval;
    int64_t rest = delta % p->interval;
    if (rest >= p->interval / 2)
        steps++;
    if (rest <= -p->interval / 2)
        steps--;
    if ((steps > 0 && p->phase_slot > INT64_MAX - steps) ||
        (steps < 0 && p->phase_slot <= -steps))
        return (struct secondary_ass_physical_point){0};
    return secondary_ass_physical_point_at(p, p->phase_slot + steps);
}
#line 1901 "video/out/vo.c"
static struct secondary_ass_physical_point secondary_cache_next_sample(
    struct vo *vo, struct secondary_ass_physical_point first,
    int64_t divisor, int64_t effective_start, double rate)
{
    struct secondary_ass_physical storage;
    bool ds = vo->in->current_frame && vo->in->current_frame->display_synced;
    const struct secondary_ass_physical *p = secondary_planning_state(vo, ds, divisor, &storage);
    struct secondary_ass_physical_point next = secondary_plan_enabled(vo, ds, divisor)
        ? (secondary_forecast_enabled(vo, ds, divisor)
            ? secondary_forecast_next(vo, first.slot, divisor, effective_start, rate)
            : secondary_ass_present_plan_cache_next(&vo->in->secondary_physical,
                first.slot, divisor, effective_start))
        : secondary_ass_physical_cache_next(p, first.slot, divisor, effective_start);
    if (vo->in->secondary_queue_stage && next.slot > first.slot)
        secondary_ass_stage_prefix_invalidate(&vo->in->secondary_stage_prefix);
    if (vo->in->secondary_trace && next.slot > first.slot)
        MP_INFO(vo, "native-ass-cache-reschedule: first_slot=%"PRId64
            " next_slot=%"PRId64" skipped_samples=%"PRId64
            " effective_start_ns=%"PRId64" first_deadline_ns=%"PRId64
            " occupied_base_slot=%"PRId64" epoch=%"PRIu64"\n",
            first.slot, next.slot, (next.slot - first.slot) / divisor,
            effective_start, secondary_ass_physical_cache_deadline(first, p->interval, p->delay),
            p->last_base_slot, p->epoch);
    return next;
}
#line 1927 "video/out/vo.c"
static void secondary_physical_feedback(struct vo *vo,
    const struct vo_vsync_info *vsync, struct secondary_ass_physical_point intended,
    const struct secondary_ass_present_plan *plan)
{
    struct vo_internal *in = vo->in;
    int64_t seed = in->reported_display_fps > 0
        ? MP_TIME_S_TO_NS(1.0 / in->reported_display_fps) : vsync->vsync_duration;
    uint64_t submitted_id = vsync->secondary_submit_id;
    if (plan) {
        bool registered = !vsync->secondary_phase_reset &&
            vsync->secondary_submit_valid && plan->generation > 0 &&
            vsync->secondary_submit_generation == plan->generation &&
            secondary_ass_present_plan_current(&in->secondary_physical, plan) &&
            secondary_ass_physical_submit_planned_point(&in->secondary_physical,
                submitted_id, plan->epoch, plan->base, plan->target);
        if (in->secondary_trace)
        MP_INFO(vo, "native-ass-plan-register: id=%"PRIu64" registered=%d "
            "base_slot=%"PRId64" target_slot=%"PRId64" epoch=%"PRIu64
            " generation=%"PRIu64"\n", submitted_id, registered,
            plan->base.slot, plan->target.slot, plan->epoch, plan->generation);
        if (!vsync->secondary_phase_reset && vsync->secondary_submit_valid)
            in->secondary_physical.last_submit_id = submitted_id;
        // Observe the real history once, without the legacy median-based
        // registration.  Unknown/failed plans do not invent a saved base.
        submitted_id = 0;
    }
    secondary_ass_physical_update_observed(&in->secondary_physical,
        vsync->secondary_phase_reset, submitted_id, intended,
        vsync->secondary_sync_qpc_ns, vsync->secondary_sync_time,
        vsync->secondary_sync_refresh_count, vsync->secondary_present_refresh_count,
        vsync->secondary_present_id, seed);
    if (plan && vsync->secondary_phase_reset && in->secondary_trace)
        MP_INFO(vo, "native-ass-plan-reset: epoch=%"PRIu64" reason=backend_reset\n",
                in->secondary_physical.epoch);
    secondary_ass_physical_record_present(&in->secondary_physical,
        !vsync->secondary_phase_reset && vsync->secondary_submit_valid,
        vsync->secondary_submit_id, vsync->secondary_submit_generation,
        vsync->secondary_submit_sync_interval);
    if (mp_ass_pacing_enabled(vo->global)) {
        struct secondary_ass_physical *p = &in->secondary_physical;
        int64_t saved_base = 0, saved_target = 0;
        for (unsigned n = 0; n < 32; n++) {
            if (p->submitted[n].id == vsync->secondary_present_id) {
                saved_base = p->submitted[n].base_slot;
                saved_target = p->submitted[n].target_slot;
                break;
            }
        }
        struct mp_ass_pacing_record record = {
            .vo_seq = vo->pacing_vo_seq, .draw_seq = vo->pacing_draw_seq,
            .frame_id = vo->pacing_frame_id, .epoch = p->epoch,
            .generation = vsync->secondary_submit_generation,
            .flags = (uint64_t)vsync->secondary_submit_valid |
                ((uint64_t)vsync->secondary_phase_reset << 1) |
                ((uint64_t)p->outlier_pending << 2) |
                ((uint64_t)p->sync_segment_consistent << 3),
            .v = {(int64_t)vsync->secondary_submit_id,
                (int64_t)vsync->secondary_present_id, intended.slot, intended.wall,
                p->phase, p->phase_slot, p->interval, p->delay,
                p->delay_count, p->sync_slot, p->sync_qpc_ns, p->sync_count,
                saved_base, saved_target, (int64_t)p->historical_id,
                vsync->secondary_display_time},
        };
        mp_ass_pacing_record(vo->global, MP_ASS_PACING_PHYSICAL, &record);
    }
    if (in->secondary_trace && in->secondary_physical.historical_id ==
            vsync->secondary_present_id) {
        struct secondary_ass_physical *p = &in->secondary_physical;
        for (unsigned n = 0; n < 32; n++) {
            if (p->submitted[n].id != vsync->secondary_present_id ||
                p->submitted[n].target_slot <= 0)
                continue;
            if (plan)
                MP_INFO(vo, "native-ass-physical: id=%"PRIu64" target_slot=%"PRId64
                    " actual_slot=%"PRId64" late_slots=%"PRId64" epoch=%"PRIu64
                    " base_slot=%"PRId64"\n", vsync->secondary_present_id,
                    p->submitted[n].target_slot, p->phase_slot,
                    p->phase_slot - p->submitted[n].target_slot, p->epoch,
                    p->submitted[n].base_slot);
            else
                MP_INFO(vo, "native-ass-physical: id=%"PRIu64" target_slot=%"PRId64
                    " actual_slot=%"PRId64" late_slots=%"PRId64" epoch=%"PRIu64"\n",
                    vsync->secondary_present_id, p->submitted[n].target_slot,
                    p->phase_slot, p->phase_slot - p->submitted[n].target_slot, p->epoch);
            break;
        }
    }
}
#line 3735 "video/out/vo.c"
void vo_set_paused(struct vo *vo, bool paused)
{
    struct vo_internal *in = vo->in;
    mp_mutex_lock(&in->lock);
    if (in->paused != paused) {
        in->paused = paused;
        if (in->secondary_queue_stage) {
            secondary_ass_queue_stage_clear(&in->secondary_stage_admission);
            secondary_ass_queue_stage_clear(&in->secondary_stage_pending);
            in->secondary_queue_resume = 0;
        }
        if (in->paused && in->dropped_frame) {
            in->request_redraw = true;
            wakeup_core(vo);
        }
        reset_vsync_timings(vo);
        wakeup_locked(vo);
    }
    mp_mutex_unlock(&in->lock);
}
#line 3793 "video/out/vo.c"
void vo_seek_reset(struct vo *vo)
{
    struct vo_internal *in = vo->in;
    mp_mutex_lock(&in->lock);
    forget_frames(vo);
    reset_vsync_timings(vo);
    in->send_reset = true;
    wakeup_locked(vo);
    mp_mutex_unlock(&in->lock);
    osd_reset_secondary_clock(vo->osd);
}
#line 3854 "video/out/vo.c"
void vo_set_queue_params(struct vo *vo, int64_t offset_ns, int num_req_frames,
                         int num_frame_refs)
{
    struct vo_internal *in = vo->in;
    mp_mutex_lock(&in->lock);
    if (in->secondary_queue_lead && in->flip_queue_offset != offset_ns) {
        in->secondary_queue_hint.valid = false;
        in->secondary_queue_admission.valid = false;
        struct secondary_ass_queue_token *token = &in->secondary_queue_pending;
        token->valid = false;
        if (token->old_admission > 0 && in->frame_queued) {
            int64_t pts = in->frame_queued->pts;
            if (pts > 0 && offset_ns < pts && offset_ns >= pts - INT64_MAX) {
                int64_t due = pts - offset_ns;
                int64_t lead = MPMIN(token->old_lead, in->timing_offset);
                token->old_admission = due > lead ? due - lead : 0;
            }
        }
    }
    if (in->secondary_queue_stage && in->flip_queue_offset != offset_ns) {
        secondary_ass_queue_stage_clear(&in->secondary_stage_admission);
        secondary_ass_queue_stage_clear(&in->secondary_stage_pending);
        in->secondary_queue_resume = 0;
    }
    in->flip_queue_offset = offset_ns;
    in->req_frames = MPCLAMP(num_req_frames, 1, VO_MAX_REQ_FRAMES);
    in->frame_refs = MPCLAMP(num_frame_refs, in->req_frames, 2 * VO_MAX_REQ_FRAMES);
    mp_mutex_unlock(&in->lock);
}
bool vo_is_ready_v22(struct vo *vo, int64_t next_pts)
{
    struct vo_internal *in = vo->in;
    double secondary_rate = osd_get_secondary_refresh(vo->osd);
    struct secondary_ass_sample_snapshot queue_sample = in->secondary_queue_lead
        ? osd_get_secondary_sample_snapshot(vo->osd)
        : (struct secondary_ass_sample_snapshot){0};
    mp_mutex_lock(&in->lock);
    in->secondary_queue_admission = (struct secondary_ass_queue_token){0};
    bool r = vo->config_ok && !in->frame_queued &&
             (!in->current_frame || in->current_frame->num_vsyncs < 1);
    if (r && next_pts >= 0) {
        // Don't show the frame too early - it would basically freeze the
        // display by disallowing OSD redrawing or VO interaction.
        // Actually render the frame at earliest the given offset before target
        // time.
        // Leave time between low-fps video frames for animated secondary ASS.
        // This changes queue lead time only, not video presentation timestamps.
        int64_t lead = in->timing_offset;
        int64_t now = mp_time_ns();
        int64_t interval = secondary_rate > 0
            ? MPMAX(MP_TIME_S_TO_NS(1.0 / secondary_rate), in->vsync_interval) : 0;
        int64_t duration = in->current_frame && !in->current_frame->display_synced
            ? in->current_frame->duration : 0;
        bool affordable = secondary_ass_budget_affordable(in->secondary_render_cost,
            in->secondary_redraw_cost, duration, interval);
        bool probe = secondary_ass_budget_probe_due(in->secondary_render_cost,
            duration, interval, now, in->secondary_next_probe);
        if (secondary_rate > 0 && (affordable || probe)) {
            int64_t minimum = MP_TIME_S_TO_NS(0.002);
            if (in->reported_display_fps > 0)
                minimum += MP_TIME_S_TO_NS(1.0 / in->reported_display_fps);
            lead = MPMIN(lead, MPMAX(minimum,
                in->secondary_render_cost + MP_TIME_S_TO_NS(0.002)));
        }
        if (in->secondary_queue_lead && affordable && !probe &&
            in->current_frame && !in->current_frame->still && !in->paused &&
            queue_sample.rate == secondary_rate &&
            in->current_frame->frame_id == in->secondary_queue_hint.retained_id &&
            in->hasframe && !in->dropped_frame && !in->send_reset &&
            !(in->queued_events & VO_EVENT_LIVE_RESIZING) &&
            !(vo->driver->caps & (VO_CAP_NORETAIN | VO_CAP_UNTIMED)) &&
            vo->driver->can_present_early &&
            in->flip_queue_offset >= 0 &&
            next_pts > in->flip_queue_offset)
        {
            struct secondary_ass_queue_token token = secondary_ass_queue_lead_make(
                &in->secondary_queue_hint, &queue_sample,
                next_pts - in->flip_queue_offset, lead, in->timing_offset,
                in->secondary_redraw_cost);
            if (token.valid && now < token.old_admission) {
                lead = token.fresh_due - token.admission;
                // An early check must schedule the new admission boundary,
                // but it does not grant an ownership token until that wake.
                if (now >= token.admission)
                    in->secondary_queue_admission = token;
            }
        }
        next_pts -= lead;
        next_pts -= in->flip_queue_offset;
        if (next_pts > now)
            r = false;
        if (!in->wakeup_pts || next_pts < in->wakeup_pts) {
            in->wakeup_pts = next_pts;
            // If we have to wait, update the vo thread's timer.
            if (!r)
                wakeup_locked(vo);
        }
    }
    mp_mutex_unlock(&in->lock);
    return r;
}

static bool promotion_boundary(struct vo *vo) {
 struct vo_internal *in=vo->in;
 struct secondary_ass_present_plan early_plan={0};
double native_rate = osd_get_secondary_refresh(vo->osd);
int64_t sample_divisor = in->secondary_present_grid
        ? osd_get_secondary_physical_sample_divisor(vo->osd) : 0;
struct secondary_ass_sample_snapshot queue_sample =
        (in->secondary_queue_lead || in->secondary_queue_stage)
        ? osd_get_secondary_sample_snapshot(vo->osd)
        : (struct secondary_ass_sample_snapshot){0};
 mp_mutex_lock(&in->lock);
if (in->secondary_stage_prefix.initialized &&
        !secondary_ass_stage_prefix_stage_equal(&in->secondary_stage_prefix.stage,
                                                &in->secondary_stage_pending))
        secondary_ass_stage_prefix_clear(&in->secondary_stage_prefix);
if (in->secondary_stage_pending.valid) {
        struct secondary_ass_queue_stage *stage = &in->secondary_stage_pending;
        bool current = secondary_stage_owner(vo, stage);
        int64_t now = mp_time_ns();
        int64_t resume = current
            ? secondary_stage_budget_resume(vo, stage, native_rate, now) : 0;
        if (current && now < resume) {
            if (!in->secondary_stage_prefix.initialized)
                secondary_ass_stage_prefix_begin(&in->secondary_stage_prefix, stage,
                                                  &queue_sample, &in->secondary_physical);
            if (secondary_forecast_enabled(vo, false, sample_divisor) &&
                queue_sample.valid && queue_sample.rate == native_rate &&
                queue_sample.divisor == sample_divisor &&
                secondary_ass_budget_affordable(in->secondary_render_cost,
                    in->secondary_redraw_cost, in->frame_queued->duration,
                    MPMAX(MP_TIME_S_TO_NS(1.0 / native_rate),
                          in->secondary_physical.interval)) &&
                secondary_ass_stage_prefix_can_promote(&in->secondary_stage_prefix,
                    stage, &queue_sample, &in->secondary_physical))
            {
                struct secondary_ass_physical_point logical =
                    secondary_ass_physical_point_at(&in->secondary_physical,
                                                    queue_sample.next_slot);
                struct secondary_ass_present_plan plan =
                    secondary_forecast_fresh_plan(vo, stage->due, logical,
                                                   sample_divisor, native_rate);
                if (secondary_ass_present_plan_current(&in->secondary_physical, &plan) &&
                    plan.base.wall >= stage->due && now < plan.submit)
                    early_plan = plan;
            }
            if (!early_plan.valid) {
                in->secondary_queue_resume = stage->resume;
                goto done;
            }
        }
        secondary_ass_queue_stage_clear(stage);
        secondary_ass_stage_prefix_clear(&in->secondary_stage_prefix);
        in->secondary_queue_resume = 0;
    }
if (in->frame_queued && in->secondary_queue_pending.old_admission > 0) {
        struct secondary_ass_queue_token *token = &in->secondary_queue_pending;
        bool current = in->current_frame && !in->paused && !in->send_reset &&
            !in->dropped_frame && !(in->queued_events & VO_EVENT_LIVE_RESIZING) &&
            !in->frame_queued->display_synced && !in->frame_queued->still &&
            secondary_ass_budget_affordable(in->secondary_render_cost,
                in->secondary_redraw_cost, in->frame_queued->duration,
                MPMAX(MP_TIME_S_TO_NS(1.0 / token->sample.rate),
                      token->plan.interval)) &&
            in->flip_queue_offset >= 0 &&
            in->frame_queued->pts > in->flip_queue_offset &&
            secondary_ass_queue_lead_current(token, &queue_sample,
                &in->secondary_physical, in->current_frame->frame_id,
                in->frame_queued->pts - in->flip_queue_offset,
                in->secondary_redraw_cost);
        token->valid &= current; // A stale admission cannot revive later.
        int64_t now = mp_time_ns();
        if (!token->valid && !in->paused && !in->frame_queued->display_synced &&
            now < token->old_admission)
        {
            // Do not wait here or run the queued-image prepass. Until the
            // original admission boundary the outer loop still owns retained
            // cache scheduling, with its exact current/queued identities.
            in->secondary_queue_resume = token->old_admission;
            goto done;
        }
        in->secondary_queue_resume = 0;
        if (token->valid && now < token->old_admission)
            early_plan = token->plan;
    }
if (in->frame_queued) {
        talloc_free(in->current_frame);
        in->current_frame = in->frame_queued;
        in->frame_queued = NULL;
        in->secondary_queue_pending = (struct secondary_ass_queue_token){0};
        secondary_ass_queue_stage_clear(&in->secondary_stage_pending);
        secondary_ass_stage_prefix_clear(&in->secondary_stage_prefix);
        in->secondary_queue_resume = 0;
    }
 (void)early_plan;mp_mutex_unlock(&in->lock);return true;
done:
 mp_mutex_unlock(&in->lock);return false;
}


static bool actual_redraw_pose_boundary(struct vo *vo,
    const struct secondary_ass_grid_task *grid_task,bool *physical,
    bool *updated,struct secondary_ass_physical_point *selected) {
 struct vo_internal *in=vo->in;
 struct vo_frame dummy={0};
 struct vo_frame *frame=in->current_frame?in->current_frame:&dummy;
 int64_t video_duration=in->current_frame?in->current_frame->duration:0;
 int64_t grid_divisor=grid_task?grid_task->divisor:0;
    int64_t display_interval = in->vsync_interval > 1 ?
        (int64_t)in->vsync_interval : MP_TIME_S_TO_NS(1.0 / 60);
    double secondary_rate = osd_get_secondary_refresh(vo->osd);
    double clock_rate = osd_get_secondary_clock_rate(vo->osd);
    bool planned_audio = secondary_plan_enabled(vo, frame->display_synced,
                                               grid_divisor);
    struct secondary_ass_present_plan present_plan = {0};
    struct secondary_ass_physical planning_storage;
    const struct secondary_ass_physical *planning_state =
        secondary_planning_state(vo, frame->display_synced, grid_divisor,
                                 &planning_storage);
    int64_t presentation_time = clock_rate > 0 ?
        secondary_ass_predict_present(&in->secondary_presentation,
                                       mp_time_ns(), display_interval) : 0;
    struct secondary_ass_physical_point physical_point = {0};
    bool physical_phase = clock_rate > 0 && !frame->display_synced &&
        in->secondary_physical.phase && secondary_rate > 0 &&
        video_duration >= in->secondary_physical.interval &&
        (secondary_ass_budget_affordable(in->secondary_render_cost,
            in->secondary_redraw_cost, video_duration,
            MPMAX(MP_TIME_S_TO_NS(1.0 / secondary_rate), in->secondary_physical.interval)) ||
         (in->secondary_fixed_forecast && grid_task && grid_task->recovery_probe &&
          secondary_ass_budget_fixed_probe_due(in->secondary_render_cost, video_duration,
            MPMAX(MP_TIME_S_TO_NS(1.0 / secondary_rate), in->secondary_physical.interval),
            mp_time_ns(), in->secondary_next_probe)));
    if (grid_task && grid_task->plan_enabled && !physical_phase) {
        if (frame != &dummy)
            talloc_free(frame);
        secondary_trace_plan_missed(vo, "physical_path_unavailable",
                                    "before-draw", &grid_task->plan);
        return false;
    }
    if (physical_phase) {
        display_interval = in->secondary_physical.interval;
        physical_point = secondary_ass_physical_predict_point(planning_state,
            mp_time_ns() + in->secondary_redraw_cost);
        if (physical_point.slot > 0 && physical_point.wall > 0)
            presentation_time = physical_point.wall;
        struct secondary_ass_physical_point next_sample = secondary_next_sample(vo, grid_divisor);
        int64_t sample = next_sample.wall;
        int64_t prepare = secondary_ass_physical_render_slot_time(
            planning_state, sample, in->secondary_redraw_cost);
        if (sample > 0 && prepare <= mp_time_ns() + display_interval / 4 &&
            next_sample.slot >= physical_point.slot)
        {
            presentation_time = sample;
            physical_point = next_sample;
        }
        if (grid_task) {
            // Late wakeups keep the original identified slot. Re-predicting
            // here would conceal a missed refresh by moving its target.
            physical_point = grid_task->point;
            presentation_time = physical_point.wall;
            display_interval = grid_task->interval;
        }
        if (planned_audio) {
            // The captured integer sampler slot is authoritative for a
            // cached draw; manual/no-grid redraws remain on the legacy path.
            present_plan = grid_task->plan;
            if (!secondary_ass_present_plan_current(&in->secondary_physical,
                                                   &present_plan)) {
                if (frame != &dummy)
                    talloc_free(frame);
                secondary_trace_plan_missed(vo,
                    secondary_plan_stale_reason(&in->secondary_physical, &present_plan),
                    "before-draw", &present_plan);
                return false;
            }
            if (present_plan.display_forecast) {
                physical_point = present_plan.target;
                presentation_time = physical_point.wall;
            }
        }
        physical_phase = physical_point.slot > 0 && physical_point.wall > 0;
    }
    if (frame->display_synced && clock_rate > 0) {
        physical_point = secondary_ass_physical_queued_point(&in->secondary_physical);
        if (physical_point.wall > 0) {
            presentation_time = physical_point.wall;
            display_interval = in->secondary_physical.interval;
        }
    }
    bool fixed_pose_reuse = in->secondary_fixed_forecast && !grid_task &&
        !frame->display_synced;
    bool secondary_target_updated;
    if (fixed_pose_reuse) {
        // A UI/manual repaint is not a new G/D task. Retain the last pose
        // without switching the forecast sampler back to a historical-H path.
        osd_hold_secondary_sample(vo->osd);
        physical_point = (struct secondary_ass_physical_point){0};
        presentation_time = 0;
        physical_phase = false;
        secondary_target_updated = false;
    } else {
        secondary_target_updated = secondary_set_presentation(vo,
            physical_point, presentation_time, display_interval,
            planned_audio && present_plan.valid ? present_plan.submit : mp_time_ns(),
            secondary_rate <= 0 && !frame->display_synced,
            secondary_forecast_enabled(vo, frame->display_synced, grid_divisor),
            &present_plan);
    }

 *physical=physical_phase;*updated=secondary_target_updated;*selected=physical_point;
 return true;
}


static bool actual_redraw_guard_boundary(struct vo *vo,uint64_t current_id,
    uint64_t queued_id,const struct secondary_ass_grid_task *grid_task) {

    struct vo_internal *in = vo->in;

    if (!vo->config_ok)
        return false;

    // Read OSD state outside the VO lock, preserving the existing lock order.
    double grid_rate = grid_task ? osd_get_secondary_refresh(vo->osd) : 0;
    int64_t grid_divisor = grid_task
        ? osd_get_secondary_physical_sample_divisor(vo->osd) : 0;
    fixture_v30_new_osd_scope = grid_task && !grid_task->stage.valid && in->secondary_fixed_forecast;
struct secondary_ass_sample_snapshot stage_before = grid_task &&
        (grid_task->stage.valid || in->secondary_fixed_forecast)
        ? osd_get_secondary_sample_snapshot(vo->osd)
        : (struct secondary_ass_sample_snapshot){0};
fixture_v30_new_osd_scope = false;

    mp_mutex_lock(&in->lock);
    if (grid_task && (in->paused || !in->hasframe || in->send_reset ||
        in->dropped_frame || (in->queued_events & VO_EVENT_LIVE_RESIZING) ||
        !in->current_frame || in->current_frame->still ||
        in->current_frame->display_synced ||
        in->current_frame->frame_id != grid_task->current_id ||
        (in->frame_queued ? in->frame_queued->frame_id : 0) != grid_task->queued_id ||
        in->secondary_physical.epoch != grid_task->epoch ||
        grid_task->plan_enabled != secondary_plan_enabled(vo,
            in->current_frame->display_synced, grid_divisor) ||
        (grid_task->plan_enabled
            ? !secondary_ass_present_plan_current(&in->secondary_physical,
                                                 &grid_task->plan)
            : in->secondary_physical.delay != grid_task->delay ||
              grid_task->point.slot <= grid_task->delay ||
              grid_task->point.slot - grid_task->delay <= in->secondary_physical.last_base_slot) ||
        grid_rate != grid_task->rate || grid_divisor != grid_task->divisor))
    {
        mp_mutex_unlock(&in->lock);
        if (grid_task->plan_enabled)
            secondary_trace_plan_missed(vo,
                secondary_plan_stale_reason(&in->secondary_physical, &grid_task->plan),
                "before-draw", &grid_task->plan);
        return false;
    }
    if (grid_task && (grid_task->deadline <= 0 || grid_task->submit_time <= 0 ||
                     mp_time_ns() >= grid_task->deadline)) {
        int64_t now = mp_time_ns();
        mp_mutex_unlock(&in->lock);
        if (in->secondary_trace)
            MP_INFO(vo, "native-ass-cache-missed: stage=before-draw target_slot=%"PRId64
                " target_ns=%"PRId64" deadline_ns=%"PRId64
                " now_ns=%"PRId64" epoch=%"PRIu64"\n",
                grid_task->point.slot, grid_task->point.wall,
                grid_task->deadline, now, grid_task->epoch);
        if (grid_task->stage.valid)
            secondary_trace_plan_missed(vo, "cache_deadline_expired", "before-draw",
                                        &grid_task->plan);
        return false;
    }
    if (grid_task && grid_task->stage.valid &&
        !secondary_stage_cache_current(vo, &grid_task->stage, mp_time_ns(),
            MPMAX(MP_TIME_S_TO_NS(1.0 / grid_rate), grid_task->interval),
            secondary_cache_block_cost(vo, grid_task->plan_enabled), grid_rate))
    {
        mp_mutex_unlock(&in->lock);
        secondary_ass_stage_prefix_invalidate(&in->secondary_stage_prefix);
        return false;
    }
    // A seek or live resize can interrupt the short preparation wait. Take
    // the retained-frame reference only if this exact cache task still exists.
    if (current_id && (!in->hasframe || in->paused || in->send_reset ||
        in->dropped_frame || (in->queued_events & VO_EVENT_LIVE_RESIZING) ||
        !in->current_frame || !in->frame_queued || in->current_frame->still ||
        in->current_frame->display_synced || in->frame_queued->display_synced ||
        in->current_frame->frame_id != current_id ||
        in->frame_queued->frame_id != queued_id))
    {
        mp_mutex_unlock(&in->lock);
        return false;
    }

    (void)stage_before; // Fragment stops before the real later resolve use.
    mp_mutex_unlock(&in->lock);
    return true;
}


static void actual_manual_feedback_boundary(struct vo *vo,
 const struct vo_vsync_info *input,struct secondary_ass_physical_point point) {
 struct vo_vsync_info vsync=*input;
 struct secondary_ass_physical_point physical_point=point;
 bool planned_audio=false;
 struct secondary_ass_present_plan present_plan={0};
secondary_physical_feedback(vo, &vsync, physical_point,
            planned_audio ? &present_plan : NULL);
}


static void actual_feedback_resolve_boundary(struct vo *vo,
    const struct secondary_ass_grid_task *grid_task,
    const struct secondary_ass_present_plan *captured,
    const struct vo_vsync_info *input,
    const struct secondary_ass_sample_snapshot *before,
    bool updated,int64_t end,int64_t deadline,bool armed,
    int64_t begin_flip,int64_t end_flip) {
 struct vo_internal *in=vo->in;
 struct vo_vsync_info vsync=*input;
 struct secondary_ass_present_plan present_plan=*captured;
 struct secondary_ass_sample_snapshot stage_before=*before;
 bool secondary_target_updated=updated;
 bool flip_budget_guard_armed=armed;
 int64_t flip_call=begin_flip,stage_flip_end=end_flip;
 int64_t cpu_end=end,trace_deadline=deadline;
 secondary_physical_feedback(vo,&vsync,captured->target,captured);
if (grid_task && grid_task->stage.valid) {
            struct secondary_ass_sample_snapshot after =
                osd_get_secondary_sample_snapshot(vo->osd);
            mp_mutex_lock(&in->lock);
            if (!flip_budget_guard_armed || stage_flip_end >= trace_deadline) {
                // A backend fallback/long flip is not proven timely here.
                // Withdraw early preparation without calling completion a
                // Display timestamp or modifying the observed Present result.
                secondary_ass_stage_prefix_invalidate(&in->secondary_stage_prefix);
            } else if (secondary_stage_owner(vo, &grid_task->stage) &&
                secondary_ass_stage_prefix_stage_equal(&grid_task->stage,
                                                       &in->secondary_stage_pending))
                secondary_ass_stage_prefix_resolve(&in->secondary_stage_prefix,
                    &present_plan, !vsync.secondary_phase_reset &&
                        vsync.secondary_submit_valid &&
                        vsync.secondary_submit_sync_interval == 1,
                    !secondary_target_updated || cpu_end >= trace_deadline ||
                        flip_call >= trace_deadline,
                    vsync.secondary_submit_id, &stage_before, &after,
                    &in->secondary_physical);
            else
                secondary_ass_stage_prefix_invalidate(&in->secondary_stage_prefix);
            mp_mutex_unlock(&in->lock);
        }
 feedback_frames++;
}


static int64_t outer_timer_boundary(struct vo *vo,bool working,bool bound,
                                    bool *manual_redraw_allowed) {
 struct vo_internal *in=vo->in;int64_t now=clock_ns;
 bool vo_paused=in->paused;(void)bound;
 int64_t wait_until=now+MP_TIME_S_TO_NS(working ? 0 : 1000);
double staged_rate = in->secondary_queue_stage
            ? osd_get_secondary_refresh(vo->osd) : 0;
struct secondary_ass_sample_snapshot staged_sample = in->secondary_queue_stage
            ? osd_get_secondary_sample_snapshot(vo->osd)
            : (struct secondary_ass_sample_snapshot){0};
 mp_mutex_lock(&in->lock);
int64_t queue_resume = in->secondary_queue_resume;
        struct secondary_ass_queue_stage held_stage = {0};
        if (in->secondary_queue_stage &&
            secondary_stage_owner(vo, &in->secondary_stage_pending) &&
            in->secondary_stage_pending.resume == queue_resume && queue_resume > now)
            held_stage = in->secondary_stage_pending;
        bool queue_held = in->frame_queued && queue_resume > now &&
            (!in->secondary_queue_stage || held_stage.valid);
        if (held_stage.valid && !in->secondary_stage_prefix.initialized)
            secondary_ass_stage_prefix_begin(&in->secondary_stage_prefix, &held_stage,
                                              &staged_sample, &in->secondary_physical);
        if (queue_held)
            wait_until = MPMIN(wait_until, queue_resume);
        if (held_stage.valid)
            wait_until = MPMIN(wait_until,
                secondary_stage_budget_resume(vo, &held_stage, staged_rate, now));
        if (in->wakeup_pts) {
            if (in->wakeup_pts > now) {
                wait_until = MPMIN(wait_until, in->wakeup_pts);
            } else {
                in->wakeup_pts = 0;
                wakeup_core(vo);
            }
        }
        if (vo->want_redraw) {
            in->want_redraw = true;
            wakeup_core(vo);
        }
        if ((!working && !in->rendering && !in->frame_queued) && in->wakeup_on_done) {
            // Cached OSD redraws can continue before the sleep path below.
            // Keep this notification pending until the frame really ends,
            // and deliver it before any redraw/continue can consume it.
            int64_t frame_end = get_current_frame_end(vo);
            if (!still_displaying(vo)) {
                in->wakeup_on_done = false;
                in->need_wakeup = true;
                wakeup_core(vo);
            } else if (frame_end > now) {
                wait_until = MPMIN(wait_until, frame_end);
            }
        }
        vo->want_redraw = false;
        bool redraw = in->request_redraw;
        bool send_reset = in->send_reset;
        in->send_reset = false;
        bool send_pause = in->paused != vo_paused;
        vo_paused = in->paused;
        bool secondary_eligible = !in->paused && in->hasframe &&
            in->current_frame && !in->current_frame->still;
        int64_t secondary_cost = in->secondary_render_cost;
        int64_t secondary_redraw_cost = in->secondary_redraw_cost;
        int64_t secondary_block_cost = in->secondary_redraw_block_cost;
        int64_t secondary_gpu_redraw = in->secondary_redraw_gpu_cost;
        int64_t secondary_probe = in->secondary_next_probe;
        int64_t secondary_duration = in->current_frame && !in->current_frame->display_synced
            ? in->current_frame->duration : 0;
        uint64_t secondary_frame_id = in->current_frame ? in->current_frame->frame_id : 0;
        bool secondary_ds = in->current_frame && in->current_frame->display_synced;
        int64_t secondary_deadline = get_current_frame_end(vo) - in->flip_queue_offset;
        if (held_stage.valid)
            secondary_deadline = MPMIN(secondary_deadline, held_stage.due);
        // Preserve real work/end wakeups before an unbound ASS proposal can
        // replace them with an artificial now+1 preparation timer.
        int64_t real_wait_until = wait_until;

 mp_mutex_unlock(&in->lock);
double secondary_rate = osd_get_secondary_refresh(vo->osd);
        int64_t thread_divisor = in->secondary_present_plan && in->secondary_present_grid
            ? osd_get_secondary_physical_sample_divisor(vo->osd) : 0;
        secondary_block_cost = secondary_cache_block_cost(vo,
            secondary_plan_enabled(vo, secondary_ds, thread_divisor));
        struct secondary_ass_physical thread_planning_storage;
        const struct secondary_ass_physical *thread_planning_state =
            secondary_planning_state(vo, secondary_ds, 0,
                                     &thread_planning_storage);
        struct secondary_ass_grid_task grid_task = {0};
        int64_t staged_cache_wake = 0;
        if (!working && secondary_eligible && secondary_rate > 0) {
            int64_t interval = MP_TIME_S_TO_NS(1.0 / secondary_rate);
            interval = MPMAX(interval, in->secondary_physical.phase &&
                secondary_duration >= in->secondary_physical.interval
                ? in->secondary_physical.interval : in->vsync_interval);
            bool affordable = secondary_ass_budget_affordable(secondary_cost,
                secondary_redraw_cost, secondary_duration, interval);
            // Once per second, allow a bounded recovery sample. A CPU wakeup
            // stall must not leave an affordable cached redraw disabled forever.
            bool probe = !affordable && (in->secondary_fixed_forecast
                ? secondary_ass_budget_fixed_probe_due(secondary_cost,
                    secondary_duration, interval, now, secondary_probe)
                : secondary_ass_budget_probe_due(secondary_cost,
                    secondary_duration, interval, now, secondary_probe));
            if (affordable || probe) {
                int64_t next = secondary_ass_next_draw(
                    &in->secondary_presentation, in->secondary_last_draw, interval);
                // Prepare the next ASS sample at its selection boundary,
                // keeping the sampler and presentation timer on one grid.
                int64_t sample_time = osd_get_secondary_next_sample_time(vo->osd);
                struct secondary_ass_physical_point physical_sample = {0};
                struct secondary_ass_present_plan fixed_cache_plan = {0};
                int64_t sample_prepare = secondary_ass_sample_prepare_time(
                    sample_time, (int64_t)in->vsync_interval);
                if (secondary_duration >= in->secondary_physical.interval &&
                    in->secondary_physical.phase)
                {
                    int64_t plan_sample_divisor = (!probe || in->secondary_fixed_forecast) &&
                        thread_divisor > 0 &&
                        thread_divisor <= INT64_MAX / in->secondary_physical.interval &&
                        secondary_duration >= thread_divisor * in->secondary_physical.interval
                        ? thread_divisor : 0;
                    physical_sample = secondary_next_sample(vo, plan_sample_divisor);
                    if (in->secondary_present_grid && (!probe || in->secondary_fixed_forecast)) {
                        int64_t divisor = in->secondary_present_plan ? thread_divisor :
                            osd_get_secondary_physical_sample_divisor(vo->osd);
                        if (divisor > 0 && divisor <= INT64_MAX / in->secondary_physical.interval &&
                            secondary_duration >= divisor * in->secondary_physical.interval) {
                            thread_planning_state = secondary_planning_state(vo,
                                secondary_ds, divisor, &thread_planning_storage);
                            physical_sample = secondary_cache_next_sample(vo, physical_sample,
                                divisor, MPMAX(now, vo->previous_redraw_time +
                                    (int64_t)in->vsync_interval), secondary_rate);
                        }
                    }
                    sample_time = physical_sample.wall;
                    sample_prepare = secondary_ass_physical_render_slot_time(
                        thread_planning_state, sample_time, secondary_redraw_cost);
                    if (in->secondary_fixed_forecast && thread_divisor > 0) {
                        fixed_cache_plan = secondary_cache_plan(vo, physical_sample,
                                                               thread_divisor, secondary_rate);
                        sample_prepare = fixed_cache_plan.valid
                            ? secondary_ass_physical_render_slot_time(thread_planning_state,
                                fixed_cache_plan.target.wall, secondary_redraw_cost)
                            : 0;
                    }
                }
                if (sample_prepare > 0)
                    next = sample_prepare;
                int64_t cost = secondary_block_cost > 0 ? secondary_block_cost : interval;
                if (probe)
                    cost = MPMAX(secondary_gpu_redraw, MPMIN(cost, interval));
                bool headroom = secondary_ass_budget_headroom(secondary_duration,
                    MPMAX(now, next), secondary_deadline, secondary_cost,
                    cost, MP_TIME_S_TO_NS(0.002));
                if (!headroom && in->secondary_physical.phase &&
                    secondary_duration >= in->secondary_physical.interval)
                {
                    int64_t deadline = secondary_ass_physical_predict(
                        (struct secondary_ass_physical *)thread_planning_state,
                        secondary_deadline);
                    deadline -= thread_planning_state->delay *
                        thread_planning_state->interval +
                        thread_planning_state->interval / 4;
                    headroom = secondary_ass_budget_before_deadline(
                        MPMAX(now, next), deadline, secondary_cost, cost,
                        MP_TIME_MS_TO_NS(1));
                }
                if (in->secondary_fixed_forecast) {
                    int64_t post_cpu = secondary_cache_post_cpu_cost(vo,
                        secondary_plan_enabled(vo, secondary_ds, thread_divisor));
                    if (post_cpu > 0) {
                        // Preserve the original headroom boundary. Recover
                        // its preparation wake without charging CPU R twice.
                        // An accepted queued image rechecks its actual F in
                        // render_frame; no future video deadline is invented.
                        bool baseline = headroom && fixed_cache_plan.valid;
                        int64_t earliest = vo->previous_redraw_time +
                            in->secondary_physical.interval;
                        struct secondary_ass_flip_window window =
                            secondary_ass_flip_budget_window(baseline, now, next,
                                earliest, fixed_cache_plan.submit,
                                fixed_cache_plan.deadline, secondary_deadline,
                                secondary_redraw_cost, post_cpu, secondary_cost,
                                MP_TIME_S_TO_NS(0.002));
                        secondary_trace_flip_window(vo, 2, secondary_frame_id,
                            baseline, now, next,
                            earliest, &fixed_cache_plan, secondary_deadline,
                            secondary_redraw_cost, post_cpu, secondary_cost,
                            MP_TIME_S_TO_NS(0.002), &window);
                        headroom = window.valid;
                        if (headroom)
                            next = window.prepare;
                    } else {
                        headroom &= fixed_cache_plan.valid &&
                        secondary_ass_budget_headroom(secondary_duration,
                            MPMAX(now, fixed_cache_plan.submit), secondary_deadline,
                            secondary_cost, cost, MP_TIME_S_TO_NS(0.002));
                    }
                }
                if (held_stage.valid) {
                    // A staged cache draw must finish before promotion and
                    // reserve the accepted incoming frame's real budget.
                    mp_mutex_lock(&in->lock);
                    headroom &= secondary_stage_cache_current(vo, &held_stage,
                        MPMAX(now, next), interval, cost, secondary_rate);
                    mp_mutex_unlock(&in->lock);
                }
                if (headroom) {
                    redraw |= now >= next;
                    wait_until = MPMIN(wait_until, MPMAX(now + 1, next));
                    if (held_stage.valid && !probe && physical_sample.slot > 0 && next > now) {
                        mp_mutex_lock(&in->lock);
                        struct secondary_ass_present_plan pending_cache =
                            secondary_cache_plan(vo, physical_sample,
                                                 thread_divisor, secondary_rate);
                        if (secondary_stage_cache_current(vo, &held_stage, next,
                                                          interval, cost, secondary_rate) &&
                            secondary_ass_present_plan_current(&in->secondary_physical,
                                                               &pending_cache))
                            staged_cache_wake = next;
                        mp_mutex_unlock(&in->lock);
                    }
                    if (in->secondary_present_grid && physical_sample.slot > 0 &&
                        now >= next && (!probe || in->secondary_fixed_forecast)) {
                        int64_t divisor = in->secondary_present_plan ? thread_divisor :
                            osd_get_secondary_physical_sample_divisor(vo->osd);
                        mp_mutex_lock(&in->lock);
                        struct secondary_ass_present_plan held_cache_plan = queue_held
                            ? secondary_cache_plan(vo, physical_sample, divisor, secondary_rate)
                            : (struct secondary_ass_present_plan){0};
                        if (divisor > 0 && in->current_frame &&
                            (!in->frame_queued || queue_held) &&
                            (!queue_held || (in->hasframe && !in->paused &&
                                !in->dropped_frame && !in->send_reset && !send_reset &&
                                !(in->queued_events & VO_EVENT_LIVE_RESIZING) &&
                                !in->current_frame->still &&
                                !in->current_frame->display_synced &&
                                secondary_ass_present_plan_current(&in->secondary_physical,
                                                                  &held_cache_plan))) &&
                            (!held_stage.valid ||
                                secondary_stage_cache_current(vo, &held_stage, now,
                                                              interval, cost, secondary_rate)) &&
                            divisor <= INT64_MAX / in->secondary_physical.interval &&
                            secondary_duration >= divisor * in->secondary_physical.interval)
                            grid_task = (struct secondary_ass_grid_task){
                                .point = physical_sample,
                                .epoch = in->secondary_physical.epoch,
                                .current_id = in->current_frame->frame_id,
                                .queued_id = queue_held && in->frame_queued
                                    ? in->frame_queued->frame_id : 0,
                                .divisor = divisor, .delay = thread_planning_state->delay,
                                .rate = secondary_rate,
                                .stage = held_stage,
                                .interval = in->secondary_physical.interval,
                                .deadline = secondary_ass_physical_cache_deadline(physical_sample,
                                    thread_planning_state->interval, thread_planning_state->delay),
                                .submit_time = secondary_ass_physical_submit_time(
                                    thread_planning_state, physical_sample.wall),
                                .plan_enabled = secondary_plan_enabled(vo,
                                    secondary_ds, divisor),
                                .recovery_probe = in->secondary_fixed_forecast && probe,
                                .plan = secondary_plan_enabled(vo, secondary_ds, divisor)
                                    ? secondary_cache_plan(vo, physical_sample, divisor, secondary_rate)
                                    : (struct secondary_ass_present_plan){0},
                            };
                        secondary_capture_grid_plan(&grid_task);
                        mp_mutex_unlock(&in->lock);
                    }
                } else if (in->secondary_trace) {
                    MP_INFO(vo, "native-ass-schedule: now_ns=%"PRId64
                        " next_ns=%"PRId64" deadline_ns=%"PRId64
                        " fresh_cost_ns=%"PRId64" redraw_cost_ns=%"PRId64
                        " block_cost_ns=%"PRId64" headroom=0\n",
                        now, next, secondary_deadline, secondary_cost,
                        secondary_redraw_cost, cost);
                }
            }
        }


if (queue_held && grid_task.point.slot <= 0) {
            redraw = false;
            // The unbound scheduler may already have proposed now+1. Keep
            // the finite captured boundary instead of spinning on that task;
            // normal wait_vo wakeups still interrupt this wait.
            wait_until = held_stage.valid
                ? MPMIN(real_wait_until, queue_resume) : queue_resume;
            if (held_stage.valid && staged_cache_wake > now)
                wait_until = MPMIN(wait_until, staged_cache_wake);
        }
 (void)send_pause; // Driver pause work is outside this CPU boundary.
 actual_outer_task=grid_task;
 *manual_redraw_allowed=redraw;return wait_until;
}


static unsigned flag_bits;
static char *fixture_getenv(const char *name) {
 const char *names[]={"MPV_NATIVE_QUEUE_LEAD","MPV_NATIVE_ASS_DIAGNOSTIC",
  "MPV_NATIVE_ASS_TRACE","MPV_NATIVE_PRESENT_GRID","MPV_NATIVE_PRESENT_PLAN",
  "MPV_NATIVE_QUEUE_STAGE"};
 for(unsigned n=0;n<6;n++)if(!strcmp(names[n],name))return flag_bits&(1u<<n)?"1":NULL;
 return NULL;
}
#define getenv fixture_getenv
static void initialize_flags(struct vo *vo) {
const char *queue_lead = getenv("MPV_NATIVE_QUEUE_LEAD");
    const char *queue_diagnostic = getenv("MPV_NATIVE_ASS_DIAGNOSTIC");
    const char *queue_trace = getenv("MPV_NATIVE_ASS_TRACE");
    const char *queue_grid = getenv("MPV_NATIVE_PRESENT_GRID");
    const char *queue_plan = getenv("MPV_NATIVE_PRESENT_PLAN");
    const char *queue_stage = getenv("MPV_NATIVE_QUEUE_STAGE");
    const char *queue_forecast = getenv("MPV_NATIVE_DISPLAY_FORECAST");
    vo->in->secondary_queue_stage = queue_stage && !strcmp(queue_stage, "1") &&
        ((queue_diagnostic && !strcmp(queue_diagnostic, "1")) ||
         (queue_trace && !strcmp(queue_trace, "1"))) &&
        queue_grid && !strcmp(queue_grid, "1") &&
        queue_plan && !strcmp(queue_plan, "1");
    vo->in->secondary_queue_lead = queue_lead && !strcmp(queue_lead, "1") &&
        !vo->in->secondary_queue_stage &&
        !(queue_forecast && !strcmp(queue_forecast, "1")) &&
        ((queue_diagnostic && !strcmp(queue_diagnostic, "1")) ||
         (queue_trace && !strcmp(queue_trace, "1"))) &&
        queue_grid && !strcmp(queue_grid, "1") &&
        queue_plan && !strcmp(queue_plan, "1");

}
#undef getenv

static void reference_selected_bodies(void) {
 (void)&forget_frames;
 (void)&get_current_frame_end;
 (void)&get_display_synced_frame_end;
 (void)&read_opts;
 (void)&reset_vsync_timings;
 (void)&secondary_cache_block_cost;
 (void)&secondary_cache_next_sample;
 (void)&secondary_cache_plan;
 (void)&secondary_cache_post_cpu_cost;
 (void)&secondary_capture_grid_plan;
 (void)&secondary_fixed_forecast_offset;
 (void)&secondary_forecast_enabled;
 (void)&secondary_forecast_fresh_plan;
 (void)&secondary_forecast_next;
 (void)&secondary_forecast_plan;
 (void)&secondary_next_sample;
 (void)&secondary_physical_feedback;
 (void)&secondary_plan_enabled;
 (void)&secondary_plan_stale_reason;
 (void)&secondary_planning_state;
 (void)&secondary_record_tag;
 (void)&secondary_stage_budget_resume;
 (void)&secondary_stage_cache_current;
 (void)&secondary_stage_owner;
 (void)&secondary_trace_flip_window;
 (void)&secondary_trace_plan;
 (void)&secondary_trace_plan_missed;
 (void)&still_displaying;
 (void)&vo_is_ready_for_frame;
 (void)&vo_queue_frame;
 (void)&vo_seek_reset;
 (void)&vo_set_paused;
 (void)&vo_set_queue_params;
 (void)&wakeup_core;
 (void)&wakeup_locked;
 (void)&SetEvent;
}


static unsigned fixture_wait_calls,fixture_plan_wait_calls;
static int64_t fixture_wait_target;
static unsigned fixture_v30_media_operand_reads;
static double fixture_media_pts(const struct mp_image *image) {
 (void)image;fixture_v30_media_operand_reads++;return 0;
}
void osd_anchor_secondary_clock(struct osd_state *osd, double pts, int64_t wall,
                                bool display_synced){ (void)osd;(void)pts;(void)wall;(void)display_synced; }
static void wait_until(struct vo *vo, int64_t target)
{ (void)vo;fixture_wait_calls++;fixture_wait_target=target; }
static void secondary_plan_wait_until(struct vo *vo, int64_t target)
{ (void)vo;fixture_plan_wait_calls++;fixture_wait_target=target; }
#line 348 "video/out/vo.c"
static void secondary_reset_physical(struct vo *vo, const char *reason)
{
    struct vo_internal *in = vo->in;
    uint64_t previous_epoch = in->secondary_physical.epoch;
    secondary_ass_physical_reset(&in->secondary_physical);
    in->secondary_fixed_offset = (struct secondary_ass_present_fixed_offset){0};
    secondary_ass_flip_budget_reset(&in->secondary_flip_budget);
    secondary_ass_neutral_pose_clear(&in->secondary_neutral_pose);
    if (mp_ass_pacing_enabled(vo->global)) {
        struct mp_ass_pacing_record record = {
            .event_ns = mp_time_ns(), .vo_seq = vo->pacing_vo_seq,
            .draw_seq = vo->pacing_draw_seq, .frame_id = vo->pacing_frame_id,
            .epoch = in->secondary_physical.epoch,
            .v = {(int64_t)previous_epoch, secondary_record_tag(reason)},
        };
        mp_ass_pacing_record(vo->global, MP_ASS_PACING_LIFECYCLE, &record);
    }
    if (in->secondary_trace && in->secondary_present_plan)
        MP_INFO(vo, "native-ass-plan-reset: epoch=%"PRIu64" reason=%s\n",
                in->secondary_physical.epoch, reason);
}
#line 546 "video/out/vo.c"
static struct secondary_ass_present_plan secondary_forecast_fresh_clock_plan(
    struct vo *vo, int64_t ready, int64_t video_submit,
    struct secondary_ass_physical_point logical, int64_t divisor, double rate)
{
    if (!logical.slot && !logical.wall) {
        struct secondary_ass_physical view =
            secondary_ass_present_plan_view(&vo->in->secondary_physical);
        logical = secondary_ass_physical_predict_point(&view, ready);
    }
    // Bootstrap only this new task's fixed offset through the existing rules.
    // The original physical phase, sampler origin and delay learner are kept.
    logical = secondary_forecast_next(vo, logical.slot, divisor, ready, rate);
    return secondary_ass_present_plan_fresh_clock(&vo->in->secondary_physical,
        logical, divisor, secondary_fixed_forecast_offset(vo, logical, divisor, rate),
        ready, video_submit);
}
struct fresh_clock_boundary_result {
 struct secondary_ass_present_plan plan;
 struct secondary_ass_physical_point point;
 int64_t target,present_ready,presentation_time,display_interval;
 bool physical,planned_audio,updated;
};
static struct fresh_clock_boundary_result actual_fresh_selection_boundary(
 struct vo *vo,struct vo_frame *frame,int64_t original_video_target,
 const struct secondary_ass_present_plan *early,
 struct secondary_ass_physical_point native_point) {
 struct vo_internal *in=vo->in;
 // This provider executes only the unchanged old zero-lease test scope.
 if(in->secondary_neutral_pose.valid) {
  failures++;fprintf(stderr,"check failed: legacy scope has neutral lease\n");
  return (struct fresh_clock_boundary_result){0};
 }
 struct secondary_ass_present_plan early_plan=*early;
 struct secondary_ass_sample_snapshot queue_sample=osd_get_secondary_sample_snapshot(vo->osd);
 double native_rate=osd_get_secondary_refresh(vo->osd);
 int64_t sample_divisor=osd_get_secondary_physical_sample_divisor(vo->osd);
 int64_t duration=frame->duration,target=original_video_target;
        int64_t display_interval = in->vsync_interval > 1 ?
            (int64_t)in->vsync_interval : MP_TIME_S_TO_NS(1.0 / 60);
        // Clock eligibility is independent of whether an animated event is
        // visible right now. Keep authority/phase accurate through ASS gaps.
        double clock_rate = early_plan.valid ? queue_sample.rate :
            osd_get_secondary_clock_rate(vo->osd);
        int64_t present_ready = MPMAX(mp_time_ns(), target);
        int64_t presentation_time = clock_rate > 0 ?
            secondary_ass_predict_present(&in->secondary_presentation,
                                           present_ready, display_interval) : 0;
        struct secondary_ass_physical_point physical_point = {0};
        struct secondary_ass_present_plan present_plan = {0};
        bool planned_audio = secondary_plan_enabled(vo, frame->display_synced,
                                                  sample_divisor);
        bool secondary_affordable = native_rate > 0 && secondary_ass_budget_affordable(
            in->secondary_render_cost, in->secondary_redraw_cost, duration,
            MPMAX(MP_TIME_S_TO_NS(1.0 / native_rate), in->secondary_physical.interval));
        // Cache protection controls extra work, not time on a video draw which
        // is already mandatory. Keep the normal/early captured plans unchanged.
        bool fresh_clock_only = in->secondary_fixed_forecast && !frame->repeat &&
            secondary_forecast_enabled(vo, frame->display_synced, sample_divisor) &&
            !early_plan.valid && !secondary_affordable;
        bool physical_phase = clock_rate > 0 && !frame->display_synced &&
            in->secondary_physical.phase && native_rate > 0 &&
            duration >= in->secondary_physical.interval &&
            (secondary_affordable || fresh_clock_only);
        if (in->secondary_sync_mode_valid &&
            in->secondary_sync_mode != frame->display_synced)
            secondary_reset_physical(vo, "sync_mode");
        in->secondary_sync_mode = frame->display_synced;
        in->secondary_sync_mode_valid = true;
        int64_t physical_now = mp_time_ns();
        struct secondary_ass_neutral_pose neutral_source = in->secondary_neutral_pose;
        struct secondary_ass_present_plan neutral_next = {0};
        bool neutral_admitted = false;
        bool media_anchored = false;
        int64_t neutral_release = 0;
        if (neutral_source.valid && clock_rate > 0 && frame->current &&
            !frame->display_synced && !frame->repeat)
        {
            // A discontinuity may invalidate the sampled pose. Apply the
            // normal media authority once before considering its reuse.
            osd_anchor_secondary_clock(vo->osd, fixture_media_pts(frame->current),
                                       frame->pts, false);
            media_anchored = true;
            physical_now = mp_time_ns();
        }
        if (in->secondary_fixed_forecast && !in->secondary_neutral_disabled &&
            planned_audio && !frame->repeat &&
            !early_plan.valid && !in->secondary_queue_stage &&
            !in->secondary_queue_lead && !in->paused && !in->send_reset &&
            !in->dropped_frame && in->visible &&
            !(in->queued_events & VO_EVENT_LIVE_RESIZING) &&
            in->secondary_render_cost >= 0 && in->secondary_redraw_cost >= 0)
        {
            fixture_v30_new_osd_scope = true;
struct secondary_ass_sample_snapshot sample =
                osd_get_secondary_sample_snapshot(vo->osd);
fixture_v30_new_osd_scope = false;
            neutral_next = secondary_forecast_plan(vo, native_point,
                                                   sample_divisor, native_rate);
            int64_t post_cpu = secondary_cache_post_cpu_cost(vo, true);
            if (post_cpu > 0 &&
                physical_now <= INT64_MAX - in->secondary_render_cost)
            {
                int64_t release = MPMAX(original_video_target,
                    physical_now + in->secondary_render_cost);
                int64_t margin = MP_TIME_MS_TO_NS(2);
                if (release <= INT64_MAX - post_cpu &&
                    release + post_cpu <= INT64_MAX - margin &&
                    neutral_next.submit > in->secondary_redraw_cost) {
                    neutral_release = release + post_cpu + margin;
                    neutral_admitted = secondary_ass_neutral_pose_admit(
                        &neutral_source, &in->secondary_physical, &sample,
                        &neutral_next, true, physical_now, original_video_target,
                        neutral_release,
                        neutral_next.submit - in->secondary_redraw_cost);
                }
            }
        }
        // A lease is tied to the latest cache submission and may cover one
        // intervening video frame only, regardless of admission outcome.
        secondary_ass_neutral_pose_clear(&in->secondary_neutral_pose);
        if (neutral_admitted) {
            // Reuse its actually submitted pose; do not sample a future G or
            // register a second H sample for the previous ASS target.
            target = original_video_target;
            presentation_time = 0;
            present_plan = (struct secondary_ass_present_plan){
                .display_forecast = true, .epoch = neutral_source.plan.epoch,
                .generation = neutral_source.plan.generation,
                .submit = original_video_target,
                .fallback_submit = original_video_target,
                .lifecycle_safe_wait = original_video_target,
            };
        } else if (physical_phase && in->secondary_physical.phase &&
            in->secondary_render_cost >= 0 &&
            physical_now <= INT64_MAX - in->secondary_render_cost) {
            int64_t physical_ready = MPMAX(present_ready,
                physical_now + in->secondary_render_cost);
            if (planned_audio) {
                if (fresh_clock_only) {
                    present_plan = secondary_forecast_fresh_clock_plan(vo,
                        physical_ready, original_video_target, native_point,
                        sample_divisor, native_rate);
                } else {
                    present_plan = early_plan.valid ? early_plan :
                    (secondary_forecast_enabled(vo, false, sample_divisor)
                        ? secondary_forecast_fresh_plan(vo, physical_ready, native_point,
                                                       sample_divisor, native_rate)
                        : secondary_ass_present_plan_fresh(
                            &in->secondary_physical, physical_ready, native_point));
                }
                bool uncaptured_fixed_fresh = in->secondary_fixed_forecast &&
                    !frame->repeat && !early_plan.valid &&
                    !in->secondary_queue_stage && secondary_affordable &&
                    secondary_forecast_enabled(vo, frame->display_synced,
                                               sample_divisor) &&
                    present_plan.display_forecast && !present_plan.fresh_clock_only &&
                    present_plan.epoch == in->secondary_physical.epoch &&
                    present_plan.generation == in->secondary_physical.success_generation &&
                    present_plan.base.slot == native_point.slot &&
                    present_plan.base.wall == native_point.wall &&
                    present_plan.submit > 0 && present_plan.fallback_submit > 0 &&
                    present_plan.deadline > 0 &&
                    present_plan.deadline == present_plan.target.wall;
                bool fresh_clock_retry = false;
                if (present_plan.display_forecast && present_plan.valid &&
                    !present_plan.fresh_clock_only &&
                    present_plan.base.wall < original_video_target &&
                    (!uncaptured_fixed_fresh ||
                     present_plan.submit < original_video_target)) {
                    // Fixed forecasts submit in D's window, while base G keeps
                    // its original feedback identity. Only a new uncaptured
                    // proposal may use that actual window to satisfy video F.
                    // Captured/legacy tasks retain the original rejection.
                    secondary_trace_plan_missed(vo, "before_video_due", "before-draw",
                                                &present_plan);
                    fresh_clock_retry = uncaptured_fixed_fresh;
                    present_plan.valid = false;
                }
                if (in->secondary_fixed_forecast && present_plan.target.slot > 0 &&
                    ((!present_plan.valid && present_plan.fifo_known &&
                      present_plan.fifo_lower > present_plan.target.slot) ||
                     (present_plan.valid && mp_time_ns() >= present_plan.deadline)))
                {
                    secondary_trace_plan_missed(vo, present_plan.valid
                        ? "fixed_display_deadline_expired" : "fixed_fifo_after_target",
                        "before-draw", &present_plan);
                    fresh_clock_retry = uncaptured_fixed_fresh;
                    present_plan.valid = false;
                }
                if (fresh_clock_retry) {
                    // The rejected proposal and its original G/D remain a MISS.
                    // Only this uncaptured mandatory draw may select a new task;
                    // captured early/cache plans and ordinary valid plans stay put.
                    int64_t retry_now = mp_time_ns();
                    if (retry_now > 0 && in->secondary_render_cost >= 0 &&
                        retry_now <= INT64_MAX - in->secondary_render_cost) {
                        int64_t retry_ready = MPMAX(present_ready,
                            retry_now + in->secondary_render_cost);
                        present_plan = secondary_forecast_fresh_clock_plan(vo,
                            retry_ready, original_video_target, native_point,
                            sample_divisor, native_rate);
                    }
                }
            }
            struct secondary_ass_physical_point candidate =
                planned_audio ? present_plan.target :
                (native_point.slot > in->secondary_physical.last_base_slot &&
                 native_point.wall > 0 ? native_point :
                 secondary_ass_physical_predict_point(&in->secondary_physical,
                                                      physical_ready));
            int64_t submit = planned_audio
                ? (present_plan.valid ? present_plan.submit : 0)
                : secondary_ass_physical_submit_time(
                    &in->secondary_physical, candidate.wall);
            if (candidate.slot > 0 && candidate.wall > 0 && submit > 0) {
                display_interval = in->secondary_physical.interval;
                physical_point = candidate;
                presentation_time = physical_point.wall;
                // Keep the existing submit policy for valid identified slots.
                // Otherwise preserve the primary video's original target.
                target = present_plan.fresh_clock_only ? original_video_target : submit;
                present_ready = target;
            }
        } else if (clock_rate > 0 && frame->display_synced) {
            // Only sample the identified queued display slot. Primary video's
            // draw/flip timing and ideal-frame authority remain unchanged.
            physical_point = secondary_ass_physical_queued_point(&in->secondary_physical);
            if (physical_point.wall > 0) {
                presentation_time = physical_point.wall;
                display_interval = in->secondary_physical.interval;
            }
        }
        physical_phase = physical_point.slot > 0 && !frame->display_synced;
        bool secondary_target_updated = false;
        if (neutral_admitted)
            osd_hold_secondary_sample(vo->osd);
        else
            secondary_target_updated = secondary_set_presentation(vo,
                physical_point, presentation_time, display_interval, present_ready,
                native_rate <= 0 && !frame->display_synced,
                secondary_forecast_enabled(vo, frame->display_synced, sample_divisor),
                &present_plan);

 (void)media_anchored; // The full render_frame reads it after this extracted scope.
 return (struct fresh_clock_boundary_result){present_plan,physical_point,target,present_ready,
  presentation_time,display_interval,physical_phase,planned_audio,secondary_target_updated};
}
static void actual_fresh_wait_boundary(struct vo *vo,struct vo_frame *frame,
 const struct fresh_clock_boundary_result *input) {
 struct vo_internal *in=vo->in;
 struct secondary_ass_present_plan present_plan=input->plan;
 struct secondary_ass_physical_point physical_point=input->point;
 int64_t target=input->target;
 int64_t original_video_target=input->target; // Neutral disabled in legacy wait scope.
 bool physical_phase=input->physical,planned_audio=input->planned_audio;
 bool secondary_target_updated=input->updated;
 bool neutral_admitted=false; // Legacy tests have no successful neutral lease.
        bool early_present = false;
        bool plan_guard_armed = false;
        if (neutral_admitted) {
            plan_guard_armed = in->secondary_physical.epoch == present_plan.epoch &&
                in->secondary_physical.success_generation == present_plan.generation &&
                vo->driver->can_present_early &&
                vo->driver->can_present_early(vo, present_plan.generation,
                    original_video_target, secondary_plan_wait_until);
        } else if (planned_audio && present_plan.valid) {
            // Arming lifecycle protection is distinct from skipping the VO
            // wait.  Normal Sync1 submission also needs final Sync0/resize
            // protection; an elapsed original S must not bypass this guard.
            plan_guard_armed =
                secondary_ass_present_plan_current(&in->secondary_physical,
                                                   &present_plan) &&
                vo->driver->can_present_early &&
                vo->driver->can_present_early(vo, present_plan.generation,
                    present_plan.lifecycle_safe_wait, secondary_plan_wait_until);
            early_present = plan_guard_armed && !present_plan.display_forecast &&
                !in->secondary_queue_stage && in->secondary_fifo_present &&
                in->visible && !frame->repeat && physical_phase &&
                secondary_target_updated && present_plan.fifo_known &&
                present_plan.fifo_lower == present_plan.target.slot &&
                present_plan.submit > mp_time_ns();
            if (early_present && in->secondary_trace)
                MP_INFO(vo, "native-ass-early-present: target_slot=%"PRId64
                    " fifo_lower_slot=%"PRId64" generation=%"PRIu64
                    " original_submit_ns=%"PRId64"\n", present_plan.target.slot,
                    present_plan.fifo_lower, present_plan.generation,
                    present_plan.submit);
        }
        int64_t fifo_lower = secondary_ass_physical_fifo_lower_bound(
            &in->secondary_physical);
        if (!planned_audio && !in->secondary_display_forecast &&
            !in->secondary_queue_stage && in->secondary_fifo_present &&
            in->visible && !frame->repeat &&
            physical_phase &&
            secondary_target_updated && fifo_lower > 0 && target > mp_time_ns() &&
            fifo_lower == physical_point.slot &&
            vo->driver->can_present_early &&
            vo->driver->can_present_early(vo,
                in->secondary_physical.success_generation, target, wait_until))
        {
            early_present = true;
            if (in->secondary_trace)
                MP_INFO(vo, "native-ass-early-present: target_slot=%"PRId64
                    " fifo_lower_slot=%"PRId64" generation=%"PRIu64
                    " original_submit_ns=%"PRId64"\n",
                    physical_point.slot, fifo_lower,
                    in->secondary_physical.success_generation, target);
        }
        if (planned_audio && present_plan.valid && !plan_guard_armed)
            secondary_plan_wait_until(vo, present_plan.lifecycle_safe_wait);
        else
            wait_until(vo, early_present ? 0 : target);


}
static void actual_fresh_late_miss_boundary(struct vo *vo,
 const struct secondary_ass_present_plan *input) {
 struct secondary_ass_present_plan present_plan=*input;
int64_t flip_call = mp_time_ns();
if (present_plan.valid && present_plan.fresh_clock_only &&
            flip_call >= present_plan.deadline)
            secondary_trace_plan_missed(vo, "fresh_clock_vo_flip_after_target",
                                        "after-flip", &present_plan);
}

struct pressure_result { int64_t cost,resume,old_lead,new_native_lead,new_native_admission,effective_resume;
 bool affordable,probe,owner,cache; };
static struct pressure_result pressure[6];
static void setup(struct vo *vo,struct vo_internal *in,struct vo_frame *retained,
                  struct vo_driver *driver,struct mp_vo_opts *opts) {
 const int64_t T=6944481;
 *retained=(struct vo_frame){.duration=16666666,.frame_id=42};
 *driver=(struct vo_driver){.can_present_early=can_early};
 *opts=(struct mp_vo_opts){.timing_offset=.05};
 *in=(struct vo_internal){.current_frame=retained,.current_frame_id=42,
  .hasframe=true,.hasframe_rendered=true,.timing_offset=50000000,
  .vsync_interval=T,.reported_display_fps=1e9/T,.secondary_render_cost=2000000,
  .secondary_redraw_cost=500000,.secondary_next_probe=2000000000,
  .secondary_queue_stage=true,.secondary_present_grid=true,.secondary_present_plan=true,
  .secondary_physical={.phase=1000000000,.phase_slot=100,.interval=T,.epoch=5,
   .last_base_slot=108,.success_generation=3,.success_contiguous=true,
   .sync_segment_consistent=true,.historical_id=10,.success_first_id=11,.success_last_id=11}};
 *vo=(struct vo){.in=in,.driver=driver,.opts=opts,.config_ok=1,
  .extra={.wakeup_cb=core_callback}};
 tracked_lock=&in->lock;fixture_rate=1e9/(2*T);
 fixture_live_sampler=false;fixture_sample_forced=false;
 fixture_clock=(struct secondary_ass_clock){0};
 fixture_sampler=(struct secondary_ass_sampler){0};
 fixture_snapshot=(struct secondary_ass_sample_snapshot){0};
}
static void legacy_same(void) {
 struct vo vo;struct vo_internal in;struct vo_frame retained,queued;
 struct vo_driver driver;struct mp_vo_opts opts;
 const int rates[]={60,120,144,165,240,360};
 const int64_t F=1100000000;
 for(unsigned rate=0;rate<6;rate++)for(unsigned state=0;state<8;state++)
 for(unsigned budget=0;budget<6;budget++)for(int edge=-2;edge<=2;edge++)
 for(unsigned oldflag=0;oldflag<2;oldflag++) {
  setup(&vo,&in,&retained,&driver,&opts);in.secondary_queue_stage=false;
  in.secondary_queue_lead=oldflag;in.reported_display_fps=rates[rate];
  in.vsync_interval=1e9/rates[rate];
  fixture_rate=budget==0?0:(rates[rate]>120?rates[rate]/2.0:rates[rate]);
  retained.duration=budget<2?41666667:budget<4?16666666:5000000;
  in.secondary_render_cost=budget%2?7000000:2000000;
  in.secondary_redraw_cost=budget%3?1000000:8000000;
  in.secondary_next_probe=budget%2?0:2000000000;
  in.timing_offset=state%2?2000000:50000000;
  retained.display_synced=state==2;retained.num_vsyncs=state==3?1:0;
  if(state==4)in.frame_queued=&queued;
  if(state==5)in.current_frame=NULL;
  if(state==6)vo.config_ok=0;
  in.rendering=state==7;
  struct vo_internal a=in,b=in;struct vo va=vo,vb=vo;va.in=&a;vb.in=&b;
  clock_ns=F-(int64_t)(in.vsync_interval+2000000)+edge;
  unsigned first=wakeups;tracked_lock=&a.lock;bool candidate=vo_is_ready_for_frame(&va,F);
  unsigned candidate_wakes=wakeups-first;first=wakeups;
  tracked_lock=&b.lock;bool original=vo_is_ready_v22(&vb,F);
  CHECK(candidate==original);CHECK(a.wakeup_pts==b.wakeup_pts);
  CHECK(candidate_wakes==wakeups-first);
  CHECK(!a.secondary_stage_admission.valid);
 }
}
static void legacy_active_token(void) {
 struct vo vo;struct vo_internal in;struct vo_frame retained;
 struct vo_driver driver;struct mp_vo_opts opts;unsigned positives=0;
 for(int shift=-1;shift<=1;shift++)for(int edge=-1;edge<=1;edge++) {
  setup(&vo,&in,&retained,&driver,&opts);in.secondary_queue_stage=false;
  in.secondary_queue_lead=true;
  struct secondary_ass_physical_point point=
   secondary_ass_physical_point_at(&in.secondary_physical,110);
  fixture_snapshot=(struct secondary_ass_sample_snapshot){.valid=true,
   .rate=fixture_rate,.speed=1,.requested_speed=1,.epoch=5,
   .next_slot=110,.next_wall=point.wall,.divisor=2,
   .phase_wall=1000000000,.phase_slot=100,.interval=in.secondary_physical.interval};
  in.secondary_queue_hint=(struct secondary_ass_queue_hint){.valid=true,
   .retained_id=42,.duration=retained.duration,.sample=fixture_snapshot,
   .physical=in.secondary_physical};
  int64_t F=point.wall-1000000+shift;
  clock_ns=F-2*in.secondary_physical.interval-2000000+edge;
  struct vo_internal a=in,b=in;struct vo va=vo,vb=vo;va.in=&a;vb.in=&b;
  tracked_lock=&a.lock;bool candidate=vo_is_ready_for_frame(&va,F);
  tracked_lock=&b.lock;bool original=vo_is_ready_v22(&vb,F);
  CHECK(candidate==original && a.wakeup_pts==b.wakeup_pts);
  CHECK(a.secondary_queue_admission.valid==b.secondary_queue_admission.valid);
  CHECK(a.secondary_queue_admission.old_admission==b.secondary_queue_admission.old_admission);
  CHECK(a.secondary_queue_admission.plan.target.slot==b.secondary_queue_admission.plan.target.slot);
  positives+=a.secondary_queue_admission.valid;
 }
 CHECK(positives>0); // the legacy comparison is not an all-reject fixture
}
static void stage_and_binding(void) {
 struct vo vo;struct vo_internal in;struct vo_frame retained,incoming;
 struct vo_driver driver;struct mp_vo_opts opts;
 const int64_t F=1080000000,A=F-50000000;
 setup(&vo,&in,&retained,&driver,&opts);clock_ns=A-1;
 CHECK(!vo_is_ready_for_frame(&vo,F));
 CHECK(!in.secondary_stage_admission.valid && in.wakeup_pts==A);
 clock_ns=A;in.rendering=true;
 CHECK(vo_is_ready_for_frame(&vo,F));
 CHECK(in.secondary_stage_admission.valid && in.secondary_stage_admission.admission==A);
 int64_t resume=in.secondary_stage_admission.resume;
 incoming=(struct vo_frame){.pts=F,.duration=16666666};vo_queue_frame(&vo,&incoming);
 CHECK(in.frame_queued==&incoming && incoming.frame_id==43 && in.current_frame==&retained);
 CHECK(in.secondary_stage_pending.valid && in.secondary_stage_pending.bound);
 CHECK(in.secondary_queue_resume==resume && !in.secondary_stage_admission.valid);
 CHECK(!in.secondary_queue_pending.valid && incoming.pts==F);
 for(int n=0;n<64;n++) {
  clock_ns=A+n*(resume-A)/64;
  CHECK(!promotion_boundary(&vo));
  CHECK(in.frame_queued==&incoming && in.current_frame==&retained);
  CHECK(in.secondary_stage_pending.resume==resume && in.secondary_queue_resume==resume);
 }
 clock_ns=resume;
 CHECK(promotion_boundary(&vo));CHECK(in.current_frame==&incoming && !in.frame_queued);
 CHECK(!in.secondary_stage_pending.valid && !in.secondary_queue_resume);
 for(int shift=-1;shift<=1;shift++) {
  setup(&vo,&in,&retained,&driver,&opts);clock_ns=A;
  CHECK(vo_is_ready_for_frame(&vo,F));
  incoming=(struct vo_frame){.pts=F+shift*5000000,.duration=16666666};
  vo_queue_frame(&vo,&incoming);
  CHECK(in.frame_queued==&incoming && incoming.pts==F+shift*5000000);
  CHECK(in.secondary_stage_pending.valid==(shift<=0));
  if(shift<=0)CHECK(in.secondary_queue_resume==resume+shift*5000000);
  else CHECK(!in.secondary_queue_resume);
 }
 for(int state=0;state<11;state++) {
  setup(&vo,&in,&retained,&driver,&opts);clock_ns=A;
  switch(state) {
   case 0: in.flip_queue_offset=-1;break;
   case 1: retained.display_synced=true;break;
   case 2: retained.still=true;break;
   case 3: in.current_frame=NULL;break;
   case 4: in.paused=true;break;
   case 5: in.send_reset=true;break;
   case 6: in.queued_events=VO_EVENT_LIVE_RESIZING;break;
   case 7: in.dropped_frame=true;break;
   case 8: in.hasframe=false;break;
   case 9: in.secondary_render_cost=50000000;break;
   case 10: driver.caps=VO_CAP_NORETAIN;break;
  }
  (void)vo_is_ready_for_frame(&vo,F);CHECK(!in.secondary_stage_admission.valid);
 }
 // Pressure after acceptance removes early preparation authority, not
 // ownership/finite hold. The actual advance guard is tested separately.
 setup(&vo,&in,&retained,&driver,&opts);retained.duration=50000000;
 in.secondary_render_cost=11000000;clock_ns=A;
 CHECK(vo_is_ready_for_frame(&vo,F));
 incoming=(struct vo_frame){.pts=F,.duration=5000000};vo_queue_frame(&vo,&incoming);
 CHECK(in.frame_queued==&incoming && in.secondary_stage_pending.valid);
 CHECK(!promotion_boundary(&vo));CHECK(in.secondary_queue_resume>A);
}
static void lifecycle(void) {
 struct vo vo;struct vo_internal in;struct vo_frame retained,incoming;
 struct vo_driver driver;struct mp_vo_opts opts;
 const int64_t F=1080000000,A=F-50000000;
 for(int state=0;state<10;state++) {
  setup(&vo,&in,&retained,&driver,&opts);clock_ns=A;
  CHECK(vo_is_ready_for_frame(&vo,F));
  incoming=(struct vo_frame){.pts=F,.duration=16666666};vo_queue_frame(&vo,&incoming);
  switch(state) {
   case 0: in.paused=true;break;
   case 1: in.send_reset=true;break;
   case 2: in.queued_events=VO_EVENT_LIVE_RESIZING;break;
   case 3: in.dropped_frame=true;break;
   case 4: retained.still=true;break;
   case 5: retained.display_synced=true;break;
   case 6: incoming.still=true;break;
   case 7: incoming.display_synced=true;break;
   case 8: incoming.pts++;break;
   case 9: incoming.frame_id++;break;
  }
  CHECK(promotion_boundary(&vo));
  CHECK(!in.secondary_stage_pending.valid && !in.secondary_queue_resume);
 }
 for(int kind=0;kind<3;kind++) {
  setup(&vo,&in,&retained,&driver,&opts);clock_ns=A;
  CHECK(vo_is_ready_for_frame(&vo,F));
  incoming=(struct vo_frame){.pts=F,.duration=16666666};vo_queue_frame(&vo,&incoming);
  if(kind==0) { opts.timing_offset=.002;read_opts(&vo); }
  if(kind==1)vo_set_queue_params(&vo,1000000,1,2);
  if(kind==2)vo_set_queue_params(&vo,-1000000,1,2);
  CHECK(!in.secondary_stage_pending.valid && !in.secondary_queue_resume);
 }
 setup(&vo,&in,&retained,&driver,&opts);clock_ns=A;
 CHECK(vo_is_ready_for_frame(&vo,F));
 incoming=(struct vo_frame){.pts=F,.duration=16666666};vo_queue_frame(&vo,&incoming);
 mp_mutex_lock(&in.lock);forget_frames(&vo);mp_mutex_unlock(&in.lock);
 CHECK(!in.frame_queued && !in.hasframe && !in.secondary_queue_resume);
 CHECK(!in.secondary_stage_admission.valid && !in.secondary_stage_pending.valid);
 setup(&vo,&in,&retained,&driver,&opts);clock_ns=A;
 CHECK(vo_is_ready_for_frame(&vo,F));
 incoming=(struct vo_frame){.pts=F,.duration=16666666};vo_queue_frame(&vo,&incoming);
 vo_set_paused(&vo,true);
 CHECK(!in.secondary_stage_admission.valid && !in.secondary_stage_pending.valid);
 CHECK(!in.secondary_queue_resume && in.paused);
 setup(&vo,&in,&retained,&driver,&opts);clock_ns=A;
 CHECK(vo_is_ready_for_frame(&vo,F));
 incoming=(struct vo_frame){.pts=F,.duration=16666666};vo_queue_frame(&vo,&incoming);
 vo_seek_reset(&vo);
 CHECK(!in.frame_queued && !in.secondary_stage_pending.valid && !in.secondary_queue_resume);
 CHECK(in.send_reset && !in.hasframe);
}
static void cache_and_pre_render_guards(void) {
 struct vo vo;struct vo_internal in;struct vo_frame retained,incoming;
 struct vo_driver driver;struct mp_vo_opts opts;
 const int64_t F=1080000000,A=F-50000000;
 for(int state=0;state<15;state++) {
  setup(&vo,&in,&retained,&driver,&opts);clock_ns=A;
  if(state==10)retained.duration=50000000;
  CHECK(vo_is_ready_for_frame(&vo,F));
  incoming=(struct vo_frame){.pts=F,.duration=16666666};vo_queue_frame(&vo,&incoming);
  struct secondary_ass_grid_task task={.current_id=42,.queued_id=43,
   .epoch=5,.divisor=2,.rate=fixture_rate,.interval=in.secondary_physical.interval,
   .stage=in.secondary_stage_pending,.plan_enabled=true};
  task.point=secondary_ass_physical_point_at(&in.secondary_physical,110);
  task.plan=secondary_ass_present_plan_cache(&in.secondary_physical,task.point);
  task.deadline=task.plan.deadline;task.submit_time=task.plan.submit;
  CHECK(task.plan.valid);
  switch(state) {
   case 1: in.paused=true;break;
   case 2: in.send_reset=true;break;
   case 3: in.queued_events=VO_EVENT_LIVE_RESIZING;break;
   case 4: in.flip_queue_offset=1;break;
   case 5: incoming.pts++;break;
   case 6: incoming.frame_id++;break;
   case 7: retained.frame_id++;break;
   case 8: clock_ns=in.secondary_stage_pending.resume;break;
   case 9: in.secondary_stage_pending.valid=false;break;
   case 10: incoming.duration=5000000;in.secondary_render_cost=11000000;break;
   case 11: in.secondary_queue_resume++;break;
   case 12: task.stage.resume++;break;
   case 13: in.timing_offset=2000000;break;
   case 14: clock_ns=task.deadline;break;
  }
  bool result=actual_redraw_guard_boundary(&vo,42,43,&task);
  CHECK(result==(state==0));
  CHECK(!in.lock && !lock_depth);
 }
 setup(&vo,&in,&retained,&driver,&opts);clock_ns=A;
 CHECK(vo_is_ready_for_frame(&vo,F));
 incoming=(struct vo_frame){.pts=F,.duration=16666666};vo_queue_frame(&vo,&incoming);
 struct secondary_ass_queue_stage stage=in.secondary_stage_pending;
 int64_t interval=2*in.secondary_physical.interval,block=1000000;
 for(int edge=-1;edge<=1;edge++) {
  clock_ns=stage.resume-block-1000000+edge;
  mp_mutex_lock(&in.lock);
  bool pass=secondary_stage_cache_current(&vo,&stage,clock_ns,interval,block,fixture_rate);
  mp_mutex_unlock(&in.lock);
  CHECK(pass==(edge<0)); // strict budget boundary; no relaxed tolerance
 }
}
static void pressure_change_diagnostic(void) {
 struct vo vo;struct vo_internal in;struct vo_frame retained,incoming;
 struct vo_driver driver;struct mp_vo_opts opts;
 const int64_t F=1080000000,A=F-50000000;
 const int64_t costs[]={1000000,2000000,5000000,10000000,11000000,20000000};
 for(unsigned n=0;n<6;n++) {
  setup(&vo,&in,&retained,&driver,&opts);clock_ns=A;
  CHECK(vo_is_ready_for_frame(&vo,F));
  incoming=(struct vo_frame){.pts=F,.duration=16666666};vo_queue_frame(&vo,&incoming);
  struct secondary_ass_queue_stage stage=in.secondary_stage_pending;
  in.secondary_render_cost=costs[n];
  mp_mutex_lock(&in.lock);
  bool owner=secondary_stage_owner(&vo,&stage);
  bool cache=secondary_stage_cache_current(&vo,&stage,clock_ns,
   2*in.secondary_physical.interval,1000000,fixture_rate);
  int64_t effective=secondary_stage_budget_resume(&vo,&stage,fixture_rate,clock_ns);
  mp_mutex_unlock(&in.lock);
  int64_t interval=2*in.secondary_physical.interval;
  bool affordable=secondary_ass_budget_affordable(costs[n],in.secondary_redraw_cost,
   retained.duration,interval);
  bool probe=secondary_ass_budget_probe_due(costs[n],retained.duration,interval,
   clock_ns,in.secondary_next_probe);
  struct vo_internal baseline=in;baseline.frame_queued=NULL;baseline.wakeup_pts=0;
  baseline.secondary_queue_stage=false;baseline.secondary_queue_lead=false;
  struct vo original=vo;original.in=&baseline;tracked_lock=&baseline.lock;
  (void)vo_is_ready_v22(&original,F);
  pressure[n]=(struct pressure_result){.cost=costs[n],.resume=stage.resume,
   .old_lead=stage.old_lead,.new_native_lead=F-baseline.wakeup_pts,
   .new_native_admission=baseline.wakeup_pts,.affordable=affordable,.probe=probe,
   .owner=owner,.cache=cache,.effective_resume=effective};
  CHECK(effective==MPMIN(stage.resume,baseline.wakeup_pts));
  CHECK(stage.resume==in.secondary_stage_pending.resume);
  tracked_lock=&in.lock;bool manual=false;in.wakeup_pts=0;
  CHECK(outer_timer_boundary(&vo,false,false,&manual)==effective);
  if(effective>A) {
   clock_ns=effective-1;
   CHECK(!promotion_boundary(&vo));
  }
  clock_ns=effective;
  CHECK(promotion_boundary(&vo));
 }
}
static void budget_resume_matrix(void) {
 struct vo vo;struct vo_internal in;struct vo_frame retained,incoming;
 struct vo_driver driver;struct mp_vo_opts opts;
 const int rates[]={60,120,144,165,240,360};
 const int64_t durations[]={5000000,16666666,41666667,50000000};
 const int64_t costs[]={0,1000000,2000000,5000000,10000000,11000000,20000000,49000000,51000000};
 const int64_t caps[]={25000000,50000000,100000000};
 const int64_t F=1080000000;
 for(unsigned r=0;r<6;r++)for(unsigned d=0;d<4;d++)
 for(unsigned c=0;c<9;c++)for(unsigned cap=0;cap<3;cap++)for(unsigned probe=0;probe<2;probe++) {
  setup(&vo,&in,&retained,&driver,&opts);
  in.reported_display_fps=rates[r];in.vsync_interval=1e9/rates[r];
  fixture_rate=rates[r]>120?rates[r]/2.0:rates[r];
  retained.duration=durations[d];in.timing_offset=caps[cap];
  clock_ns=F-MPMIN(caps[cap],50000000);
  CHECK(vo_is_ready_for_frame(&vo,F));CHECK(in.secondary_stage_admission.valid);
  incoming=(struct vo_frame){.pts=F,.duration=durations[d]};vo_queue_frame(&vo,&incoming);
  struct secondary_ass_queue_stage captured=in.secondary_stage_pending;
  CHECK(captured.valid && secondary_stage_owner(&vo,&captured));
  in.secondary_render_cost=costs[c];in.secondary_next_probe=probe?0:2000000000;
  struct vo_internal original_in=in;original_in.frame_queued=NULL;original_in.wakeup_pts=0;
  original_in.secondary_queue_stage=false;original_in.secondary_queue_lead=false;
  struct vo original=vo;original.in=&original_in;tracked_lock=&original_in.lock;
  (void)vo_is_ready_v22(&original,F);
  // The independent scalar stage caps standard early ownership at 50 ms.
  // For configurations above that cap, original readiness may already have
  // elapsed before legal queue acceptance: then finite park ends immediately.
  int64_t expected=MPMIN(captured.resume,
   MPMAX(captured.admission,original_in.wakeup_pts));
  tracked_lock=&in.lock;mp_mutex_lock(&in.lock);
  int64_t effective=secondary_stage_budget_resume(&vo,&captured,fixture_rate,clock_ns);
  mp_mutex_unlock(&in.lock);
  CHECK(effective==expected && effective<=captured.resume);
  CHECK(!memcmp(&captured,&in.secondary_stage_pending,sizeof(captured)));
  in.wakeup_pts=0;bool manual=true;
  CHECK(outer_timer_boundary(&vo,false,false,&manual)==effective);
  CHECK(!manual);
  // Test the real cache completion boundary. Unknown/insufficient incoming
  // budget rejects as well; no generated formula replaces the actual function.
  int64_t interval=MPMAX(MP_TIME_S_TO_NS(1.0/fixture_rate),in.vsync_interval);
  bool affordable=secondary_ass_budget_affordable(in.secondary_render_cost,
    in.secondary_redraw_cost,incoming.duration,interval);
  if(effective-2000000>clock_ns) {
   for(int edge=-1;edge<=1;edge++) {
    int64_t t=effective-2000000+edge;
    mp_mutex_lock(&in.lock);
    bool current=secondary_stage_cache_current(&vo,&captured,t,interval,1000000,fixture_rate);
    mp_mutex_unlock(&in.lock);
    CHECK(current==(affordable && edge<0));
   }
  }
  if(effective>clock_ns) {
   clock_ns=effective-1;CHECK(!promotion_boundary(&vo));
  }
  clock_ns=effective;CHECK(promotion_boundary(&vo));
  CHECK(in.current_frame==&incoming && !in.frame_queued && !in.secondary_stage_pending.valid);
 }
}
static bool actual_sampler_selection(struct vo_internal *in,
 const struct secondary_ass_present_plan *plan) {
 bool forced=fixture_sampler.force;
 bool changed=secondary_ass_sampler_update_physical_forecast(&fixture_sampler,
  &fixture_clock,fixture_rate,plan->target.wall,plan->base.slot,plan->target.slot,
  in->secondary_physical.phase,in->secondary_physical.phase_slot,
  in->secondary_physical.interval,in->secondary_physical.epoch);
 fixture_sample_forced=forced;
 return changed;
}
static struct vo_vsync_info host_vsync(struct vo_internal *in,
 const struct secondary_ass_present_plan *plan,uint64_t id,
 const struct secondary_ass_present_plan *historical,uint64_t history_id,int64_t end) {
 struct secondary_ass_physical *p=&in->secondary_physical;
 int64_t slot=p->phase_slot+(end-p->phase)/p->interval;
 int64_t qpc=p->phase+(slot-p->phase_slot)*p->interval;
 return (struct vo_vsync_info){.secondary_submit_valid=true,
  .secondary_submit_id=id,.secondary_submit_generation=plan->generation,
  .secondary_submit_sync_interval=1,.secondary_sync_qpc_ns=qpc,
  .secondary_sync_time=qpc,.secondary_sync_refresh_count=(uint32_t)slot,
  .secondary_present_refresh_count=(uint32_t)historical->target.slot,
  .secondary_present_id=history_id,.secondary_display_time=historical->target.wall,
  .vsync_duration=p->interval};
}
static struct secondary_ass_present_plan initialize_actual_chain(
 struct vo *vo,struct vo_internal *in,struct vo_frame *retained,struct vo_frame *incoming,
 struct vo_driver *driver,struct mp_vo_opts *opts,int hz,int N,int H,bool initial_unknown) {
 setup(vo,in,retained,driver,opts);
 const int64_t T=1000000000LL/hz,O=1000000000;
 in->vsync_interval=T;in->reported_display_fps=1e9/T;
 in->secondary_redraw_cost=100000;in->secondary_redraw_block_cost=100000;
 in->secondary_display_forecast=true;retained->duration=100000000;
 in->secondary_physical=(struct secondary_ass_physical){.phase=O,.phase_slot=100,
  .interval=T,.epoch=7,.sync_qpc_ns=O,.sync_count=100,.sync_slot=100,
  .sync_segment_consistent=true,.measure_qpc_ns=O,.measure_count=100,
  .periods={T,T,T},.period_count=3,.period_next=3,
  .delay=H,.delay_samples={H,H,H},.delay_count=3,.success_generation=3};
 fixture_clock=(struct secondary_ass_clock){.valid=true,.pts=10,.speed=1,.wall=O};
 fixture_rate=1e9/(N*(double)T);fixture_divisor=N;fixture_live_sampler=true;
 struct secondary_ass_present_plan seed=secondary_ass_present_plan_cache_forecast(
  &in->secondary_physical,secondary_ass_physical_point_at(&in->secondary_physical,110));
 CHECK(seed.valid && actual_sampler_selection(in,&seed));
 clock_ns=seed.target.wall+10000;
 retained->pts=seed.base.wall;
 struct vo_vsync_info vsync=host_vsync(in,&seed,1,&seed,1,clock_ns);
 secondary_physical_feedback(vo,&vsync,seed.target,&seed);feedback_frames++;
 CHECK(in->secondary_physical.success_last_id==1 && in->secondary_physical.historical_id==1);
 struct secondary_ass_sample_snapshot s=osd_get_secondary_sample_snapshot(vo->osd);
 CHECK(secondary_ass_stage_prefix_snapshot_valid(&s));
 int64_t F=secondary_ass_physical_point_at(&in->secondary_physical,s.next_slot+N).wall-1;
 clock_ns=MPMAX(clock_ns,F-50000000);
 CHECK(vo_is_ready_for_frame(vo,F));CHECK(in->secondary_stage_admission.valid);
 *incoming=(struct vo_frame){.pts=F,.duration=100000000};vo_queue_frame(vo,incoming);
 CHECK(in->secondary_stage_pending.valid && !in->secondary_stage_prefix.initialized);
 // The actual guard, not a hand-written prefix.valid=true, initializes it.
 if(initial_unknown)fixture_live_sampler=false;
 CHECK(!promotion_boundary(vo));
 CHECK(in->secondary_stage_prefix.initialized && in->secondary_stage_prefix.valid==!initial_unknown);
 fixture_live_sampler=true;
 return seed;
}
static void actual_prefix_chains(void) {
 struct vo vo;struct vo_internal in;struct vo_frame retained,incoming;
 struct vo_driver driver;struct mp_vo_opts opts;
 const int rates[]={60,120,144,165,240,360};
 for(unsigned r=0;r<6;r++)for(int H=0;H<=1;H++)for(int mode=0;mode<14;mode++) {
  struct secondary_ass_present_plan seed=initialize_actual_chain(&vo,&in,&retained,&incoming,
   &driver,&opts,rates[r],2,H,mode==13);
  if(mode==13) {
   CHECK(!promotion_boundary(&vo));
   CHECK(in.secondary_stage_prefix.initialized && !in.secondary_stage_prefix.valid);
   CHECK(in.secondary_stage_pending.valid);continue;
  }
  struct secondary_ass_queue_stage captured=in.secondary_stage_pending;
  struct secondary_ass_sample_snapshot before=osd_get_secondary_sample_snapshot(vo.osd);
  struct secondary_ass_present_plan plan=secondary_ass_present_plan_cache_forecast(
   &in.secondary_physical,secondary_ass_physical_point_at(&in.secondary_physical,before.next_slot));
  CHECK(plan.valid && plan.base.wall<captured.due);
  struct secondary_ass_grid_task task={.point=plan.base,.epoch=plan.epoch,.current_id=42,.queued_id=43,
   .divisor=2,.rate=fixture_rate,.stage=captured,.interval=in.secondary_physical.interval,
   .deadline=plan.deadline,.submit_time=plan.submit,.plan_enabled=true,.plan=plan};
  struct secondary_ass_physical view=secondary_ass_present_plan_view(&in.secondary_physical);
  int64_t next=secondary_ass_physical_render_slot_time(&view,plan.base.wall,in.secondary_redraw_cost);
  CHECK(next>clock_ns);
  bool manual=true;in.wakeup_pts=0;in.request_redraw=true;
  int64_t timer=outer_timer_boundary(&vo,false,false,&manual);
  if(timer!=next || manual)fprintf(stderr,"timer r=%d H=%d mode=%d now=%lld next=%lld timer=%lld resume=%lld manual=%d\n",
   rates[r],H,mode,(long long)clock_ns,(long long)next,(long long)timer,(long long)captured.resume,manual);
  CHECK(timer==next && timer<captured.resume && !manual);
  CHECK(in.secondary_stage_prefix.valid);
  // The unknown/manual path must not create an artificial now+1 timer.
  if(mode==12) {
   fixture_snapshot=(struct secondary_ass_sample_snapshot){0};fixture_live_sampler=false;
   timer=outer_timer_boundary(&vo,false,false,&manual);
   CHECK(timer==captured.resume && !manual);continue;
  }
  clock_ns=next;CHECK(actual_redraw_guard_boundary(&vo,42,43,&task));
  if(mode==1)fixture_sampler.force=true;
  if(mode==2) {
   plan=secondary_ass_present_plan_cache_forecast(&in.secondary_physical,
    secondary_ass_physical_point_at(&in.secondary_physical,before.next_slot+2));
   task.plan=plan;task.point=plan.base;task.deadline=plan.deadline;task.submit_time=plan.submit;
  }
  CHECK(actual_sampler_selection(&in,&plan));
  int64_t entry=plan.submit,finish=entry+10000,cpu_end=entry-10000;
  bool armed=true,updated=true;
  if(mode==3)entry=finish=plan.deadline;
  if(mode==4) { armed=false;entry=finish=plan.deadline; }
  if(mode==5)finish=plan.deadline;
  if(mode==6)updated=false;
  struct vo_vsync_info vsync=host_vsync(&in,&plan,2,&seed,1,finish);
  if(mode==7)vsync.secondary_submit_valid=false;
  if(mode==8)vsync.secondary_submit_sync_interval=0;
  clock_ns=finish;
  actual_feedback_resolve_boundary(&vo,&task,&plan,&vsync,&before,updated,
   cpu_end,plan.deadline,armed,entry,finish);
  CHECK(in.secondary_physical.delay==H);
  // Raw successful Present stays successful under late/UNKNOWN timing.
  if(mode>=3 && mode<=6)CHECK(in.secondary_physical.success_last_id==2);
  bool proof_expected=mode==0 || mode==9 || mode==10 || mode==11;
  CHECK(in.secondary_stage_prefix.valid==proof_expected);
  CHECK(secondary_ass_queue_stage_current(&captured,42,43,incoming.pts,0));
  if(mode==9) {
   incoming.duration=1000000;
   in.secondary_render_cost=MP_TIME_S_TO_NS(1.0/fixture_rate)*.8;
  }
  if(mode==10)in.flip_queue_offset=1;
  if(mode==11)fixture_sample_forced=true;
  int64_t effective=secondary_stage_budget_resume(&vo,&captured,fixture_rate,clock_ns);
  if(mode==0 || mode==9 || mode==10 || mode==11)CHECK(clock_ns<effective);
  bool promoted=promotion_boundary(&vo);
  bool expected=clock_ns>=effective || mode==0 || mode==10;
  if(promoted!=expected)fprintf(stderr,"promote r=%d H=%d mode=%d now=%lld effective=%lld promoted=%d prefix=%d\n",
   rates[r],H,mode,(long long)clock_ns,(long long)effective,promoted,in.secondary_stage_prefix.valid);
  CHECK(promoted==expected);
  if(mode==0) {
   early_prepare_positive++;
   CHECK(in.current_frame==&incoming && !in.frame_queued && !in.secondary_stage_pending.valid);
  }
  if(mode==9)CHECK(in.secondary_stage_prefix.valid); // pressure withholds permission, owns same finite park
  CHECK(!in.lock && !lock_depth);
 }
 CHECK(early_prepare_positive==12);
 fixture_live_sampler=false;
}
static void timers_and_flags(void) {
 struct vo vo;struct vo_internal in;struct vo_frame retained,incoming;
 struct vo_driver driver;struct mp_vo_opts opts;bool manual=false;
 const int64_t F=1080000000,A=F-50000000;
 setup(&vo,&in,&retained,&driver,&opts);clock_ns=A;
 CHECK(vo_is_ready_for_frame(&vo,F));
 incoming=(struct vo_frame){.pts=F,.duration=16666666};vo_queue_frame(&vo,&incoming);
 in.request_redraw=true;in.rendering=false;
 int64_t resume=in.secondary_queue_resume;
 // Synthetic timer input tests only the extracted timer-priority contract;
 // it is not evidence this timer state occurred in actual media playback.
 in.wakeup_pts=A+500000;
 int64_t wait=outer_timer_boundary(&vo,false,false,&manual);
 CHECK(!manual && wait==A+500000 && wait<resume);
 in.wakeup_pts=F+16666666;
 wait=outer_timer_boundary(&vo,true,false,&manual);
 CHECK(!manual && wait<=clock_ns); // first outer after current fresh draw
 in.frame_queued=NULL;secondary_ass_queue_stage_clear(&in.secondary_stage_pending);
 in.secondary_queue_resume=0;in.request_redraw=false;in.wakeup_on_done=true;
 retained.pts=A;retained.duration=2000000;in.rendering=false;in.wakeup_pts=0;
 clock_ns=A+1000000;unsigned wakes=core_wakeups;
 wait=outer_timer_boundary(&vo,false,false,&manual);
 CHECK(in.wakeup_on_done && wait==A+2000000 && core_wakeups==wakes);
 clock_ns=A+2000000;
 (void)outer_timer_boundary(&vo,false,false,&manual);
 CHECK(!in.wakeup_on_done && core_wakeups==wakes+1);
 for(flag_bits=0;flag_bits<64;flag_bits++) {
  initialize_flags(&vo);
  bool prerequisite=(flag_bits&6)&&(flag_bits&8)&&(flag_bits&16);
  bool stage=prerequisite&&(flag_bits&32);
  bool lead=prerequisite&&(flag_bits&1)&&!stage;
  CHECK(in.secondary_queue_stage==stage);
  CHECK(in.secondary_queue_lead==lead);
 }
 CHECK(!in.lock && !lock_depth);
}
static void actual_fixed_outer_and_pose(void) {
 struct vo vo;struct vo_internal in;struct vo_frame retained;
 struct vo_driver driver;struct mp_vo_opts opts;
 const int rates[]={60,120,144,165,240,360};
 for(unsigned r=0;r<6;r++)for(int N=1;N<=4;N++) {
  setup(&vo,&in,&retained,&driver,&opts);
  const int64_t T=1000000000LL/rates[r],O=1000000000;
  in.secondary_queue_stage=false;in.secondary_display_forecast=true;
  in.secondary_fixed_forecast=true;in.vsync_interval=T;in.reported_display_fps=1e9/T;
  retained.duration=20*N*T;retained.pts=O;
  in.secondary_physical=(struct secondary_ass_physical){.phase=O,.phase_slot=100,
   .interval=T,.epoch=7,.sync_qpc_ns=O,.sync_count=100,.sync_slot=100,
   .sync_segment_consistent=true,.measure_qpc_ns=O,.measure_count=100,
   .periods={T,T,T},.period_count=3,.period_next=3,.delay=1,
   .delay_samples={1,1,1},.delay_count=3,.success_generation=3,.success_contiguous=true};
  fixture_clock=(struct secondary_ass_clock){.valid=true,.pts=10,.speed=1,.wall=O};
  fixture_rate=1e9/(N*(double)T);fixture_divisor=N;fixture_live_sampler=true;
  struct secondary_ass_present_plan seed=secondary_forecast_plan(&vo,
   secondary_ass_physical_point_at(&in.secondary_physical,110),N,fixture_rate);
  CHECK(seed.valid && seed.captured_forecast==1 && seed.submit==seed.fallback_submit);
  CHECK(actual_sampler_selection(&in,&seed));
  clock_ns=seed.target.wall+10000;retained.pts=seed.base.wall;
  struct vo_vsync_info vsync=host_vsync(&in,&seed,1,&seed,1,clock_ns);
  secondary_physical_feedback(&vo,&vsync,seed.target,&seed);
  CHECK(in.secondary_physical.success_last_id==1);
  // Recovery probe retains the identified G/D grid and original budget.
  in.secondary_render_cost=N*T/4;in.secondary_redraw_cost=N*T*4/5;
  in.secondary_redraw_block_cost=100000;in.secondary_next_probe=0;
  CHECK(!secondary_ass_budget_affordable(in.secondary_render_cost,
   in.secondary_redraw_cost,retained.duration,N*T));
  bool manual=false;
  int64_t wake=outer_timer_boundary(&vo,false,false,&manual);
  if(!manual) {
   CHECK(wake>clock_ns && wake<retained.pts+retained.duration);
   clock_ns=wake;
   (void)outer_timer_boundary(&vo,false,false,&manual);
  }
  CHECK(manual && actual_outer_task.recovery_probe && actual_outer_task.plan_enabled);
  CHECK(actual_outer_task.point.slot>110 && actual_outer_task.plan.valid);
  CHECK(actual_outer_task.plan.target.slot-actual_outer_task.plan.base.slot==1);
  CHECK(actual_outer_task.submit_time==actual_outer_task.plan.fallback_submit);
  unsigned calls=pose_set_calls,holds=pose_holds;
  bool physical=false,updated=true;struct secondary_ass_physical_point point={0};
  CHECK(actual_redraw_guard_boundary(&vo,0,0,&actual_outer_task));
  CHECK(actual_redraw_pose_boundary(&vo,&actual_outer_task,&physical,&updated,&point));
  CHECK(physical && point.slot==actual_outer_task.plan.target.slot);
  CHECK(pose_set_calls==calls+1 && pose_holds==holds && !updated);
  // Removing the probe bit must not bypass the original affordable guard.
  struct secondary_ass_grid_task no_probe=actual_outer_task;no_probe.recovery_probe=false;
  calls=pose_set_calls;
  CHECK(!actual_redraw_pose_boundary(&vo,&no_probe,&physical,&updated,&point));
  CHECK(pose_set_calls==calls);
  // A manual repaint keeps the old pose; it creates no new sample task.
  struct secondary_ass_sampler saved=fixture_sampler;
  struct secondary_ass_present_fixed_offset fixed=in.secondary_fixed_offset;
  calls=pose_set_calls;holds=pose_holds;
  CHECK(actual_redraw_pose_boundary(&vo,NULL,&physical,&updated,&point));
  CHECK(!physical && !updated && !point.slot && !point.wall);
  CHECK(pose_set_calls==calls && pose_holds==holds+1);
  CHECK(memcmp(&saved,&fixture_sampler,sizeof(saved))==0);
  CHECK(memcmp(&fixed,&in.secondary_fixed_offset,sizeof(fixed))==0);
  // The actual successful Present ledger survives an unbound/manual pose.
  vsync=host_vsync(&in,&actual_outer_task.plan,2,&seed,1,clock_ns);
  actual_manual_feedback_boundary(&vo,&vsync,point);
  CHECK(in.secondary_physical.success_last_id==2 && in.secondary_physical.historical_id==1);
  CHECK(memcmp(&saved,&fixture_sampler,sizeof(saved))==0);
  in.secondary_physical.success_generation=0;
  struct secondary_ass_present_plan lost=secondary_forecast_plan(&vo,
   secondary_ass_physical_point_at(&in.secondary_physical,120),N,fixture_rate);
  CHECK(!lost.valid && memcmp(&fixed,&in.secondary_fixed_offset,sizeof(fixed))==0);
  in.secondary_physical.success_generation=3;in.secondary_physical.success_contiguous=false;
  lost=secondary_forecast_plan(&vo,secondary_ass_physical_point_at(&in.secondary_physical,120),N,fixture_rate);
  CHECK(!lost.valid && memcmp(&fixed,&in.secondary_fixed_offset,sizeof(fixed))==0);
  in.secondary_physical.success_contiguous=true;in.secondary_physical.delay=3;
  lost=secondary_forecast_plan(&vo,secondary_ass_physical_point_at(&in.secondary_physical,120),N,fixture_rate);
  CHECK(lost.valid && lost.captured_forecast==1 && lost.historical_delay==3);
 }
 fixture_live_sampler=false;
}

static unsigned v28_checks,v28_positive_plans,v28_matrix_cases,v28_model_draws;
static void v28_setup(struct vo *vo,struct vo_internal *in,struct vo_frame *frame,
 struct vo_driver *driver,struct mp_vo_opts *opts,int hz,int fps) {
 setup(vo,in,frame,driver,opts);
 const int64_t T=1000000000LL/hz,O=1000000000;
 const int64_t N=(hz+119)/120;
 fixture_divisor=N;fixture_rate=1e9/(N*(double)T);
 in->secondary_queue_stage=false;in->secondary_display_forecast=true;
 in->secondary_fixed_forecast=true;in->secondary_render_cost=3974400;
 in->secondary_redraw_cost=14742100;in->secondary_redraw_block_cost=15058200;
 in->vsync_interval=T;in->reported_display_fps=1e9/T;
 frame->duration=1000000000LL/fps;
 in->secondary_physical=(struct secondary_ass_physical){.phase=O,.phase_slot=100,
  .interval=T,.epoch=7,.sync_qpc_ns=O,.sync_count=100,.sync_slot=100,
  .sync_segment_consistent=true,.measure_qpc_ns=O,.measure_count=100,
  .periods={T,T,T},.period_count=3,.period_next=3,.delay=1,
  .delay_samples={1,1,1},.delay_count=3,.success_generation=3,.success_contiguous=true};
 fixture_clock=(struct secondary_ass_clock){.valid=true,.pts=10,.speed=1,.wall=O};
 fixture_live_sampler=true;
 struct secondary_ass_present_plan seed=secondary_forecast_plan(vo,
  secondary_ass_physical_point_at(&in->secondary_physical,110),N,fixture_rate);
 CHECK(seed.valid && actual_sampler_selection(in,&seed));
 in->secondary_physical.last_base_slot=seed.base.slot;
 in->secondary_sync_mode_valid=true;in->secondary_sync_mode=false;
 clock_ns=seed.target.wall+10000;
}
static void v28_basic_pressure(int64_t redraw,int64_t stale_for) {
 struct vo vo;struct vo_internal in;struct vo_frame frame;
 struct vo_driver driver;struct mp_vo_opts opts;
 v28_setup(&vo,&in,&frame,&driver,&opts,144,50);
 struct secondary_ass_physical saved=in.secondary_physical;
 int offset=in.secondary_fixed_offset.offset;
 in.secondary_redraw_cost=redraw;
 clock_ns+=stale_for;
 int64_t F=clock_ns+in.secondary_render_cost;
 frame.pts=F;
 struct secondary_ass_present_plan early={0};
 struct secondary_ass_physical_point native=secondary_next_sample(&vo,fixture_divisor);
 CHECK(!secondary_ass_budget_affordable(in.secondary_render_cost,redraw,
  frame.duration,fixture_divisor*in.secondary_physical.interval));
 struct fresh_clock_boundary_result r=actual_fresh_selection_boundary(&vo,&frame,F,&early,native);
 CHECK(r.plan.valid && r.plan.fresh_clock_only && r.plan.display_forecast);
 CHECK(r.physical && r.point.slot==r.plan.target.slot && r.point.wall==r.plan.target.wall);
 CHECK(r.target==F && r.plan.submit==F && r.plan.fallback_submit==F && r.plan.lifecycle_safe_wait==F);
 CHECK(r.plan.target.wall>F && r.plan.target.slot-r.plan.base.slot==offset);
 CHECK((r.plan.base.slot-native.slot)%fixture_divisor==0);
 CHECK(r.plan.base.slot>saved.last_base_slot);
 CHECK(!memcmp(&saved,&in.secondary_physical,sizeof(saved)));
 CHECK(in.secondary_fixed_offset.offset==offset);
 fixture_wait_calls=fixture_plan_wait_calls=0;fixture_wait_target=-1;
 actual_fresh_wait_boundary(&vo,&frame,&r);
 CHECK(fixture_wait_calls==1 && fixture_plan_wait_calls==0 && fixture_wait_target==F);
 driver.can_present_early=NULL;
 fixture_wait_calls=fixture_plan_wait_calls=0;fixture_wait_target=-1;
 actual_fresh_wait_boundary(&vo,&frame,&r);
 CHECK(fixture_wait_calls==0 && fixture_plan_wait_calls==1 && fixture_wait_target==F);
 CHECK(actual_sampler_selection(&in,&r.plan));
 CHECK(fixture_sampler.pts>10 && fixture_sampler.physical_slots && fixture_sampler.display_forecast);
 v28_positive_plans++;
 fixture_live_sampler=false;
}
static void v28_feature_matrix(void) {
 for(unsigned mask=0;mask<16;mask++)for(unsigned zero=0;zero<2;zero++)
 for(unsigned repeat=0;repeat<2;repeat++)for(unsigned early_valid=0;early_valid<2;early_valid++)
 for(unsigned ds=0;ds<2;ds++)for(unsigned queue_stage=0;queue_stage<2;queue_stage++) {
  struct vo vo;struct vo_internal in;struct vo_frame frame;
  struct vo_driver driver;struct mp_vo_opts opts;
  v28_setup(&vo,&in,&frame,&driver,&opts,144,50);
  in.secondary_redraw_cost=100000000;
  clock_ns+=1000000000;
  int64_t F=clock_ns+in.secondary_render_cost;frame.pts=F;
  struct secondary_ass_physical_point native=secondary_next_sample(&vo,fixture_divisor);
  struct secondary_ass_present_plan early=secondary_forecast_plan(&vo,native,fixture_divisor,fixture_rate);
  CHECK(early.valid);
  early.valid=early_valid;
  struct secondary_ass_present_plan saved=early;
  in.secondary_fixed_forecast=!!(mask&1);in.secondary_display_forecast=!!(mask&2);
  in.secondary_present_grid=!!(mask&4);in.secondary_present_plan=!!(mask&8);
  fixture_divisor=zero?0:2;frame.repeat=repeat;frame.display_synced=ds;
  in.secondary_queue_stage=queue_stage;
  struct fresh_clock_boundary_result r=actual_fresh_selection_boundary(&vo,&frame,F,&early,native);
  bool expected=mask==15 && !zero && !repeat && !early_valid && !ds;
  CHECK(r.plan.fresh_clock_only==expected);
  CHECK(r.target==F);
  CHECK(!memcmp(&early,&saved,sizeof(early)));
  CHECK(expected?r.plan.valid:!r.plan.valid);
 }
 fixture_live_sampler=false;
}
static void v28_invalid_helper_and_math(void) {
 struct vo vo;struct vo_internal in;struct vo_frame frame;
 struct vo_driver driver;struct mp_vo_opts opts;
 v28_setup(&vo,&in,&frame,&driver,&opts,144,50);
 struct secondary_ass_physical p=in.secondary_physical;
 struct secondary_ass_physical_point first=secondary_next_sample(&vo,fixture_divisor);
 int offset=in.secondary_fixed_offset.offset;
 for(unsigned fault=0;fault<14;fault++) {
  struct secondary_ass_physical q=p;
  struct secondary_ass_physical_point given=first;
  int changed_offset=offset;
  int64_t divisor=fixture_divisor,ready=2000000000,F=2000000000;
  if(fault==0)given.wall++;
  if(fault==1)changed_offset=-1;
  if(fault==2)divisor=0;
  if(fault==3)ready=0;
  if(fault==4)F=0;
  if(fault==5)q.epoch=0;
  if(fault==6)q.success_generation=0;
  if(fault==7)q.epoch_exhausted=true;
  if(fault==8)q.outlier_pending=true;
  if(fault==9)q.sync_segment_consistent=false;
  if(fault==10)q.success_contiguous=false;
  if(fault==11)given=(struct secondary_ass_physical_point){INT64_MAX,INT64_MAX};
  if(fault==12)divisor=INT64_MAX;
  if(fault==13)ready=F=INT64_MAX;
  struct secondary_ass_physical saved=q;
  struct secondary_ass_present_plan bad=secondary_ass_present_plan_fresh_clock(&q,given,divisor,changed_offset,ready,F);
  CHECK(!bad.valid && bad.fresh_clock_only);
  CHECK(!memcmp(&saved,&q,sizeof(q)));
 }
 for(unsigned mode=0;mode<5;mode++) {
  v28_setup(&vo,&in,&frame,&driver,&opts,144,50);
  struct secondary_ass_present_plan early={0};
  first=secondary_next_sample(&vo,fixture_divisor);
  int64_t F=2000000000;clock_ns=F-3974400;frame.pts=F;
  in.secondary_redraw_cost=100000000;
  if(mode==0)fixture_rate=0;
  if(mode==1)in.secondary_render_cost=-1;
  if(mode==2)in.secondary_physical.phase=0;
  if(mode==3)frame.duration=0;
  if(mode==4)clock_ns=INT64_MAX-in.secondary_render_cost+1;
  struct fresh_clock_boundary_result bad=actual_fresh_selection_boundary(&vo,&frame,F,&early,first);
  CHECK(!bad.plan.valid && !bad.plan.fresh_clock_only && bad.target==F);
 }
 fixture_live_sampler=false;
}
static void v28_no_extra_cache_and_late_miss(void) {
 struct vo vo;struct vo_internal in;struct vo_frame frame;
 struct vo_driver driver;struct mp_vo_opts opts;
 v28_setup(&vo,&in,&frame,&driver,&opts,144,50);
 clock_ns=2000000000;
 in.secondary_next_probe=0;in.secondary_redraw_cost=14742100;
 frame.pts=clock_ns-frame.duration+500000;
 bool manual=true;(void)outer_timer_boundary(&vo,false,false,&manual);
 CHECK(!manual && actual_outer_task.point.slot==0 && !actual_outer_task.plan.valid);
 int64_t F=clock_ns+in.secondary_render_cost;frame.pts=F;
 struct secondary_ass_present_plan early={0};
 struct secondary_ass_physical_point native=secondary_next_sample(&vo,fixture_divisor);
 struct fresh_clock_boundary_result r=actual_fresh_selection_boundary(&vo,&frame,F,&early,native);
 CHECK(r.plan.valid && r.plan.fresh_clock_only && r.target==F);
 for(unsigned queue_stage=0;queue_stage<2;queue_stage++)for(int edge=-1;edge<=1;edge++) {
  struct secondary_ass_present_plan saved=r.plan;
  recorded=(struct mp_ass_pacing_record){0};
  in.secondary_queue_stage=queue_stage;
  in.secondary_stage_prefix.valid=true;
  clock_ns=r.plan.deadline+edge;
  actual_fresh_late_miss_boundary(&vo,&r.plan);
  CHECK(!memcmp(&saved,&r.plan,sizeof(saved)));
  if(edge<0)CHECK(recorded.v[0]==0 && in.secondary_stage_prefix.valid);
  else {
   CHECK(recorded.v[0]==saved.target.slot && recorded.v[1]==saved.target.wall);
   CHECK(recorded.v[2]==saved.base.slot && recorded.v[3]==saved.base.wall && recorded.v[4]==saved.deadline);
   CHECK(recorded.v[5]==secondary_record_tag("fresh_clock_vo_flip_after_target"));
   CHECK(recorded.v[6]==secondary_record_tag("after-flip"));
   CHECK(recorded.flags==1);
   CHECK(in.secondary_stage_prefix.valid==!queue_stage);
  }
 }
 recorded=(struct mp_ass_pacing_record){0};
 secondary_trace_plan_missed(&vo,"fixed_fifo_after_target","before-draw",&r.plan);
 CHECK(recorded.flags==0 && recorded.v[0]==r.plan.target.slot && recorded.v[1]==r.plan.target.wall);
 fixture_live_sampler=false;
}
static void v28_long_models(void) {
 if(failures)return; // A rejected fault needs no 340200-draw negative replay.
 const int hz_values[]={60,120,144,165,240,360};
 const int fps_values[]={24,25,30,50,60};
 for(unsigned h=0;h<6;h++)for(unsigned f=0;f<5;f++) {
  struct vo vo;struct vo_internal in;struct vo_frame frame;
  struct vo_driver driver;struct mp_vo_opts opts;
  v28_setup(&vo,&in,&frame,&driver,&opts,hz_values[h],fps_values[f]);
  in.secondary_redraw_cost=100000000;
  struct secondary_ass_physical original=in.secondary_physical;
  struct secondary_ass_present_fixed_offset fixed=in.secondary_fixed_offset;
  struct secondary_ass_present_plan early={0};
  int64_t origin=fixture_sampler.origin_slot,previous_slot=0;
  double previous_pts=fixture_sampler.pts;
  const int64_t F0=2000000000;
  unsigned count=(unsigned)fps_values[f]*300;
  for(unsigned i=0;i<count;i++) {
   int64_t F=F0+(int64_t)i*1000000000LL/fps_values[f];
   int64_t jitter=i%97==0?100000:i%101==0?-100000:0;
   clock_ns=F-in.secondary_render_cost+jitter;frame.pts=F;
   struct secondary_ass_physical_point native=secondary_next_sample(&vo,fixture_divisor);
   struct fresh_clock_boundary_result r=actual_fresh_selection_boundary(&vo,&frame,F,&early,native);
   CHECK(r.plan.valid && r.plan.fresh_clock_only && r.physical);
   CHECK(r.target==F && r.plan.submit==F && r.plan.fallback_submit==F && r.plan.lifecycle_safe_wait==F);
   CHECK(r.plan.target.wall>MPMAX(F,clock_ns+in.secondary_render_cost));
   CHECK(r.plan.base.slot>previous_slot && (r.plan.base.slot-origin)%fixture_divisor==0);
   CHECK(r.plan.target.slot-r.plan.base.slot==fixed.offset);
   CHECK(!memcmp(&original,&in.secondary_physical,sizeof(original)));
   CHECK(!memcmp(&fixed,&in.secondary_fixed_offset,sizeof(fixed)));
   CHECK(actual_sampler_selection(&in,&r.plan));
   CHECK(fixture_sampler.pts>previous_pts && fixture_sampler.origin_slot==origin);
   previous_pts=fixture_sampler.pts;previous_slot=r.plan.base.slot;
   v28_model_draws++;
   if(failures)return;
  }
  v28_matrix_cases++;
 }
 fixture_live_sampler=false;
}
static void v28_tests(void) {
 unsigned start=checks;
 v28_basic_pressure(11239000,15419561000LL);
 v28_basic_pressure(14742100,1518247200LL);
 v28_feature_matrix();
 v28_invalid_helper_and_math();
 v28_no_extra_cache_and_late_miss();
 v28_long_models();
 v28_checks=checks-start;
 fprintf(stderr,"V28 fresh clock checks=%u plans=%u matrix=%u draws=%u failures=%u\n",v28_checks,v28_positive_plans,v28_matrix_cases,v28_model_draws,failures);
}


static unsigned v29_checks,v29_positive_plans,v29_rejected_scopes,v29_time_edges;
static unsigned v29_matrix_cases,v29_model_draws;
static void v29_clear_observation(void) {
 v29_record_count=0;recorded=(struct mp_ass_pacing_record){0};
 v29_clock_advances=false;v29_clock_reads=0;
}
static void v29_setup(struct vo *vo,struct vo_internal *in,struct vo_frame *frame,
 struct vo_driver *driver,struct mp_vo_opts *opts) {
 v28_setup(vo,in,frame,driver,opts,144,50);
 in->secondary_render_cost=1000000;in->secondary_redraw_cost=1000000;
 in->secondary_redraw_block_cost=1000000;
 in->secondary_physical.success_first_id=1;
 in->secondary_physical.historical_id=1;
 in->secondary_physical.success_last_id=2;
 v29_clear_observation();
 CHECK(secondary_ass_budget_affordable(in->secondary_render_cost,
  in->secondary_redraw_cost,frame->duration,fixture_divisor*in->secondary_physical.interval));
}
static void v29_original_miss(const struct secondary_ass_present_plan *old,
 const char *reason) {
 CHECK(v29_record_count==1);
 if(v29_record_count!=1)return;
 CHECK(v29_record_kind[0]==MP_ASS_PACING_MISS);
 const struct mp_ass_pacing_record *m=&v29_records[0];
 CHECK(m->flags==0 && m->epoch==old->epoch && m->generation==old->generation);
 CHECK(m->v[0]==old->target.slot && m->v[1]==old->target.wall);
 CHECK(m->v[2]==old->base.slot && m->v[3]==old->base.wall && m->v[4]==old->deadline);
 CHECK(m->v[5]==secondary_record_tag(reason));
 CHECK(m->v[6]==secondary_record_tag("before-draw"));
}
static void v29_waits(struct vo *vo,struct vo_frame *frame,
 struct vo_driver *driver,const struct fresh_clock_boundary_result *r,int64_t F) {
 fixture_wait_calls=fixture_plan_wait_calls=0;fixture_wait_target=-1;
 actual_fresh_wait_boundary(vo,frame,r);
 CHECK(fixture_wait_calls==1 && fixture_plan_wait_calls==0 && fixture_wait_target==F);
 driver->can_present_early=NULL;
 fixture_wait_calls=fixture_plan_wait_calls=0;fixture_wait_target=-1;
 actual_fresh_wait_boundary(vo,frame,r);
 CHECK(fixture_wait_calls==0 && fixture_plan_wait_calls==1 && fixture_wait_target==F);
 driver->can_present_early=can_early;
}
// 0: G<F<D, permitting the same G/D on the new uncaptured task.
// 1: authoritative FIFO passed D; 2/3: deadline equality/after equality.
// 4/5: ordinary candidate and D-1 remain the original normal policy.
static void v29_candidate(unsigned mode,unsigned scope) {
 struct vo vo;struct vo_internal in;struct vo_frame frame;
 struct vo_driver driver;struct mp_vo_opts opts;
 v29_setup(&vo,&in,&frame,&driver,&opts);
 struct secondary_ass_physical_point native=secondary_next_sample(&vo,fixture_divisor);
 struct secondary_ass_physical before_fifo=in.secondary_physical;
 int64_t T=in.secondary_physical.interval,F=native.wall;
 clock_ns=native.wall-in.secondary_render_cost-100000;
 if(mode==0)F=native.wall+T/2;
 if(mode==1) {
  struct secondary_ass_physical_point shifted=secondary_ass_physical_point_at(
   &in.secondary_physical,native.slot-3);
  in.secondary_physical.phase=shifted.wall;
  in.secondary_physical.phase_slot=shifted.slot;
  in.secondary_physical.success_last_id=9;
 }
 struct secondary_ass_present_plan old=secondary_forecast_fresh_plan(&vo,F,native,
  fixture_divisor,fixture_rate);
 if(mode==2)clock_ns=old.deadline;
 if(mode==3)clock_ns=old.deadline+1;
 if(mode==5)clock_ns=old.deadline-1;
 CHECK(old.target.slot>0 && old.deadline==old.target.wall && old.deadline>0);
 CHECK(mode==1?(!old.valid && old.fifo_lower>old.target.slot):old.valid);
 struct secondary_ass_present_plan early={0};
 if(scope==1)in.secondary_queue_stage=true;
 if(scope==2)early=secondary_ass_present_plan_make_fixed_forecast(&before_fifo,native,
  in.secondary_fixed_offset.offset);
 if(scope==3)frame.repeat=true;
 frame.pts=F;
 struct secondary_ass_present_plan saved_early=early;
 struct secondary_ass_physical physical=in.secondary_physical;
 struct secondary_ass_present_fixed_offset fixed=in.secondary_fixed_offset;
 struct secondary_ass_sampler sampler=fixture_sampler;
 v29_clear_observation();
 struct fresh_clock_boundary_result r=actual_fresh_selection_boundary(&vo,&frame,F,&early,native);
 CHECK(!memcmp(&early,&saved_early,sizeof(early)));
 CHECK(!memcmp(&physical,&in.secondary_physical,sizeof(physical)));
 CHECK(!memcmp(&fixed,&in.secondary_fixed_offset,sizeof(fixed)));
 CHECK(!memcmp(&sampler,&fixture_sampler,sizeof(sampler)));
 if(mode<4) {
  if(mode==1 && scope==2) {
   // This already captured early task retains its original proposal even
   // after FIFO advances. Its historical semantics are not changed here.
   CHECK(!v29_record_count && !r.plan.fresh_clock_only);
   CHECK(!memcmp(&r.plan,&saved_early,sizeof(saved_early)) && r.target==saved_early.submit);
   v29_rejected_scopes++;fixture_live_sampler=false;return;
  }
  v29_original_miss(&old,mode==0?"before_video_due":mode==1?"fixed_fifo_after_target":
   "fixed_display_deadline_expired");
  if(scope) {
   CHECK(!r.plan.valid && !r.plan.fresh_clock_only && !r.physical && r.target==F);
   v29_rejected_scopes++;
  } else {
   CHECK(r.plan.valid && r.plan.fresh_clock_only && r.plan.display_forecast && r.physical);
   CHECK(r.target==F && r.plan.submit==F && r.plan.fallback_submit==F && r.plan.lifecycle_safe_wait==F);
   CHECK(r.plan.deadline==r.plan.target.wall && r.plan.target.wall>MPMAX(F,clock_ns+in.secondary_render_cost));
   CHECK(r.plan.base.slot>physical.last_base_slot &&
    (r.plan.base.slot-native.slot)%fixture_divisor==0);
   CHECK(r.plan.target.slot-r.plan.base.slot==fixed.offset);
   CHECK(r.plan.epoch==old.epoch && r.plan.generation==old.generation);
   if(mode==0)CHECK(r.plan.base.slot==old.base.slot && r.plan.target.slot==old.target.slot);
   else CHECK(r.plan.base.slot>old.base.slot && r.plan.target.slot>old.target.slot);
   if(mode==1)CHECK(r.plan.fifo_known && r.plan.target.slot>=r.plan.fifo_lower);
   v29_waits(&vo,&frame,&driver,&r,F);
   CHECK(actual_sampler_selection(&in,&r.plan));
   CHECK(fixture_sampler.pts>sampler.pts && fixture_sampler.origin_slot==sampler.origin_slot);
   v29_positive_plans++;
  }
 } else {
  CHECK(!v29_record_count && r.plan.valid && !r.plan.fresh_clock_only);
  CHECK(!memcmp(&r.plan,&old,sizeof(old)) && r.target==old.submit);
 }
 fixture_live_sampler=false;
}
static void v29_feature_and_authority(void) {
 for(unsigned mask=0;mask<15;mask++) {
  struct vo vo;struct vo_internal in;struct vo_frame frame;
  struct vo_driver driver;struct mp_vo_opts opts;
  v29_setup(&vo,&in,&frame,&driver,&opts);
  struct secondary_ass_physical_point native=secondary_next_sample(&vo,fixture_divisor);
  int64_t F=native.wall+in.secondary_physical.interval/2;
  clock_ns=native.wall-in.secondary_render_cost-100000;frame.pts=F;
  in.secondary_fixed_forecast=!!(mask&1);in.secondary_display_forecast=!!(mask&2);
  in.secondary_present_grid=!!(mask&4);in.secondary_present_plan=!!(mask&8);
  struct secondary_ass_present_plan early={0};
  struct fresh_clock_boundary_result r=actual_fresh_selection_boundary(&vo,&frame,F,&early,native);
  CHECK(!r.plan.fresh_clock_only);v29_rejected_scopes++;
 }
 for(unsigned fault=0;fault<12;fault++) {
  struct vo vo;struct vo_internal in;struct vo_frame frame;
  struct vo_driver driver;struct mp_vo_opts opts;
  v29_setup(&vo,&in,&frame,&driver,&opts);
  struct secondary_ass_physical_point native=secondary_next_sample(&vo,fixture_divisor);
  int64_t F=native.wall+in.secondary_physical.interval/2;
  clock_ns=native.wall-in.secondary_render_cost-100000;frame.pts=F;
  if(fault==0)fixture_divisor=0;
  if(fault==1)fixture_rate=0;
  if(fault==2)in.secondary_physical.epoch=0;
  if(fault==3)in.secondary_physical.success_generation=0;
  if(fault==4)in.secondary_physical.epoch_exhausted=true;
  if(fault==5)in.secondary_physical.outlier_pending=true;
  if(fault==6)in.secondary_physical.sync_segment_consistent=false;
  if(fault==7)in.secondary_physical.success_contiguous=false;
  if(fault==8)in.secondary_physical.phase=0;
  if(fault==9)in.secondary_render_cost=-1;
  if(fault==10)clock_ns=INT64_MAX-in.secondary_render_cost+1;
  if(fault==11)frame.display_synced=true;
  struct secondary_ass_present_plan early={0};
  struct fresh_clock_boundary_result r=actual_fresh_selection_boundary(&vo,&frame,F,&early,native);
  int64_t expected_target=fault==0?secondary_ass_physical_submit_time(
   &in.secondary_physical,native.wall):F;
  if(r.plan.fresh_clock_only || r.plan.valid || r.target!=expected_target)
   fprintf(stderr,"V29 authority fault=%u clock_only=%d valid=%d target=%lld F=%lld\n",
    fault,r.plan.fresh_clock_only,r.plan.valid,(long long)r.target,(long long)F);
  CHECK(!r.plan.fresh_clock_only && !r.plan.valid && r.target==expected_target);
  v29_rejected_scopes++;
 }
 // A FIFO label must not revive a malformed/occupied proposal (deadline=0).
 for(unsigned bad=0;bad<2;bad++) {
  struct vo vo;struct vo_internal in;struct vo_frame frame;
  struct vo_driver driver;struct mp_vo_opts opts;
  v29_setup(&vo,&in,&frame,&driver,&opts);
  struct secondary_ass_physical_point native=secondary_next_sample(&vo,fixture_divisor);
  struct secondary_ass_physical_point shift=secondary_ass_physical_point_at(&in.secondary_physical,native.slot-3);
  in.secondary_physical.phase=shift.wall;in.secondary_physical.phase_slot=shift.slot;
  in.secondary_physical.success_last_id=9;
  if(bad==0)native.wall++;
  else in.secondary_physical.last_base_slot=native.slot;
  int64_t F=native.wall;clock_ns=F-in.secondary_render_cost;frame.pts=F;
  struct secondary_ass_present_plan old=secondary_forecast_fresh_plan(&vo,F,native,fixture_divisor,fixture_rate);
  CHECK(!old.valid && old.deadline==0 && old.fifo_known && old.fifo_lower>old.target.slot);
  struct secondary_ass_present_plan early={0};
  v29_clear_observation();
  struct fresh_clock_boundary_result r=actual_fresh_selection_boundary(&vo,&frame,F,&early,native);
  v29_original_miss(&old,"fixed_fifo_after_target");
  CHECK(!r.plan.valid && !r.plan.fresh_clock_only && r.target==F);
  v29_rejected_scopes++;
 }
 fixture_live_sampler=false;
}
static void v29_clock_edges(void) {
 for(unsigned mode=0;mode<3;mode++) {
  struct vo vo;struct vo_internal in;struct vo_frame frame;
  struct vo_driver driver;struct mp_vo_opts opts;
  v29_setup(&vo,&in,&frame,&driver,&opts);
  struct secondary_ass_physical_point native=secondary_next_sample(&vo,fixture_divisor);
  int64_t F=native.wall+in.secondary_physical.interval/2;
  clock_ns=native.wall-in.secondary_render_cost-100000;frame.pts=F;
  struct secondary_ass_present_plan old=secondary_forecast_fresh_plan(&vo,F,native,fixture_divisor,fixture_rate);
  struct secondary_ass_physical saved=in.secondary_physical;
  struct secondary_ass_present_fixed_offset fixed=in.secondary_fixed_offset;
  struct secondary_ass_present_plan early={0};
  v29_clear_observation();v29_clock_advances=true;v29_advance_after=2;
  v29_clock_after=mode==0?old.deadline+3*in.secondary_physical.interval:mode==1?INT64_MAX:0;
  struct fresh_clock_boundary_result r=actual_fresh_selection_boundary(&vo,&frame,F,&early,native);
  CHECK(v29_clock_reads>=4);v29_clock_advances=false;
  v29_original_miss(&old,"before_video_due");
  CHECK(!memcmp(&saved,&in.secondary_physical,sizeof(saved)));
  CHECK(!memcmp(&fixed,&in.secondary_fixed_offset,sizeof(fixed)));
  if(mode==0) {
   CHECK(r.plan.valid && r.plan.fresh_clock_only && r.target==F);
   CHECK(r.plan.target.wall>v29_clock_after+in.secondary_render_cost);
   CHECK(r.plan.target.slot>old.target.slot);
   CHECK(r.plan.submit==F && r.plan.fallback_submit==F && r.plan.lifecycle_safe_wait==F);
   v29_positive_plans++;
  } else CHECK(!r.plan.valid && !r.plan.fresh_clock_only && r.target==F);
  v29_time_edges++;
 }
 fixture_live_sampler=false;
}
static void v29_long_models(void) {
 if(failures)return;
 const int hz_values[]={60,120,144,165,240,360};
 const int fps_values[]={24,25,30,50,60};
 for(unsigned h=0;h<6;h++)for(unsigned f=0;f<5;f++) {
  struct vo vo;struct vo_internal in;struct vo_frame frame;
  struct vo_driver driver;struct mp_vo_opts opts;
  v28_setup(&vo,&in,&frame,&driver,&opts,hz_values[h],fps_values[f]);
  in.secondary_render_cost=1000000;in.secondary_redraw_cost=1000000;
  in.secondary_redraw_block_cost=1000000;
  struct secondary_ass_physical physical=in.secondary_physical;
  struct secondary_ass_present_fixed_offset fixed=in.secondary_fixed_offset;
  struct secondary_ass_present_plan early={0};
  int64_t origin=fixture_sampler.origin_slot,previous_slot=0;
  double previous_pts=fixture_sampler.pts;
  const int64_t F0=2000000000;
  unsigned count=(unsigned)fps_values[f]*300;
  for(unsigned i=0;i<count;i++) {
   int64_t F=F0+(int64_t)i*1000000000LL/fps_values[f];
   int64_t jitter=i%97==0?100000:i%101==0?-100000:0;
   clock_ns=F-in.secondary_render_cost+jitter;frame.pts=F;
   v29_clear_observation();
   struct secondary_ass_physical_point native=secondary_next_sample(&vo,fixture_divisor);
   struct secondary_ass_present_plan old=secondary_forecast_fresh_plan(&vo,F,native,
    fixture_divisor,fixture_rate);
   CHECK(secondary_ass_budget_affordable(in.secondary_render_cost,in.secondary_redraw_cost,
    frame.duration,fixture_divisor*in.secondary_physical.interval));
   struct fresh_clock_boundary_result r=actual_fresh_selection_boundary(&vo,&frame,F,&early,native);
   CHECK(r.plan.valid && r.physical && r.plan.display_forecast);
   CHECK(r.plan.base.slot>previous_slot && (r.plan.base.slot-origin)%fixture_divisor==0);
   CHECK(r.plan.target.slot-r.plan.base.slot==fixed.offset && r.plan.deadline==r.plan.target.wall);
   CHECK(!memcmp(&physical,&in.secondary_physical,sizeof(physical)));
   CHECK(!memcmp(&fixed,&in.secondary_fixed_offset,sizeof(fixed)));
   if(r.plan.fresh_clock_only) {
    CHECK(r.target==F && r.plan.submit==F && r.plan.fallback_submit==F && r.plan.lifecycle_safe_wait==F);
    CHECK(r.plan.target.wall>MPMAX(F,clock_ns+in.secondary_render_cost));
    v29_original_miss(&old,old.base.wall<F?"before_video_due":"fixed_display_deadline_expired");
    v29_waits(&vo,&frame,&driver,&r,F);
   } else {
    CHECK(!v29_record_count && r.target==old.submit && !memcmp(&r.plan,&old,sizeof(old)));
   }
   CHECK(actual_sampler_selection(&in,&r.plan));
   CHECK(fixture_sampler.pts>previous_pts && fixture_sampler.origin_slot==origin);
   previous_pts=fixture_sampler.pts;previous_slot=r.plan.base.slot;v29_model_draws++;
   if(failures)return;
  }
  v29_matrix_cases++;
 }
 fixture_live_sampler=false;
}
static void v29_tests(void) {
 unsigned start=checks,before_failures=failures;
 for(unsigned mode=0;mode<4;mode++)for(unsigned scope=0;scope<4;scope++)v29_candidate(mode,scope);
 v29_candidate(4,0);v29_candidate(5,0);
 v29_feature_and_authority();v29_clock_edges();v29_long_models();
 v29_checks=checks-start;
 fprintf(stderr,"V29 fresh retry checks=%u plans=%u rejected=%u time_edges=%u matrix=%u draws=%u failures=%u\n",
  v29_checks,v29_positive_plans,v29_rejected_scopes,v29_time_edges,v29_matrix_cases,v29_model_draws,failures-before_failures);
}


static void fresh_window_new_case(void) {
 struct vo vo;struct vo_internal in;struct vo_frame frame;
 struct vo_driver driver;struct mp_vo_opts opts;
 v29_setup(&vo,&in,&frame,&driver,&opts);
 // An established nonzero fixed offset; no learner reset or input phase change.
 in.secondary_fixed_offset.offset=3;in.secondary_physical.delay=3;
 struct secondary_ass_physical_point native=secondary_next_sample(&vo,fixture_divisor);
 int64_t T=in.secondary_physical.interval,F=native.wall+T;
 clock_ns=native.wall-in.secondary_render_cost-100000;
 struct secondary_ass_physical saved=in.secondary_physical;
 struct secondary_ass_present_plan early={0};
 struct secondary_ass_present_plan proposal=secondary_forecast_fresh_plan(&vo,F,native,fixture_divisor,fixture_rate);
 CHECK(proposal.valid && proposal.base.wall<F && proposal.submit>=F);
 struct fresh_clock_boundary_result r=actual_fresh_selection_boundary(&vo,&frame,F,&early,native);
 CHECK(r.plan.valid && !r.plan.fresh_clock_only);
 CHECK(r.plan.target.wall==proposal.target.wall && r.plan.base.wall==proposal.base.wall);
 CHECK(r.target==proposal.submit && r.target>=F);
 CHECK(v29_record_count==0);
 CHECK(in.secondary_fixed_offset.offset==3 && in.secondary_physical.delay==3);
 CHECK(in.secondary_physical.phase==saved.phase && in.secondary_physical.phase_slot==saved.phase_slot);
 actual_fresh_wait_boundary(&vo,&frame,&r);
 CHECK(fixture_wait_target==proposal.submit);
 printf("fresh_window_new_case_completed\n");
}

int main(void) {
 reference_selected_bodies();
 legacy_same();legacy_active_token();stage_and_binding();lifecycle();
 cache_and_pre_render_guards();pressure_change_diagnostic();budget_resume_matrix();actual_prefix_chains();timers_and_flags();
 unsigned legacy_checks=checks;
 CHECK(legacy_checks==103149);
 actual_fixed_outer_and_pose();
 printf("{\"checks\":%u,\"v24_checks\":%u,\"failures\":%u,\"wakeups\":%u,\"core_wakeups\":%u,\"actual_feedback_frames\":%u,\"early_prepare_positive\":%u,\"pressure_changes\":[",
        legacy_checks,checks-legacy_checks,failures,wakeups,core_wakeups,feedback_frames,early_prepare_positive);
 for(unsigned n=0;n<6;n++)printf("%s{\"cost_ns\":%lld,\"captured_old_lead_ns\":%lld,"
   "\"fixed_resume_ns\":%lld,\"new_native_lead_ns\":%lld,\"new_native_admission_ns\":%lld,\"effective_resume_ns\":%lld,"
   "\"affordable\":%s,\"probe\":%s,\"owner\":%s,\"cache\":%s}",n?",":"",
   (long long)pressure[n].cost,(long long)pressure[n].old_lead,(long long)pressure[n].resume,
   (long long)pressure[n].new_native_lead,(long long)pressure[n].new_native_admission,
   (long long)pressure[n].effective_resume,
   pressure[n].affordable?"true":"false",pressure[n].probe?"true":"false",
   pressure[n].owner?"true":"false",pressure[n].cache?"true":"false");
 printf("]}\n");
 v28_tests();
 v29_tests();
 fresh_window_new_case();
 return failures ? 7 : 0;
}
