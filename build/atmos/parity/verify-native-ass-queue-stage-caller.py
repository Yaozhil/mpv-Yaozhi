#!/usr/bin/env python3
"""CPU replay of real V24 VO declarations/functions and selected loop fragments.

No mpv structure is synthesized. Platform endpoints and the OSD getter are
explicit boundaries; the getter's true prototype is compiled, but its actual
_Atomic osd_state/body still requires the separate GCC gate. This is neither
a full VO thread, an OS/GPU timing test nor permission for CI/deployment.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = BASELINE = CC = GATE = None


def execute_c(cpath, flags=()):
    common = [str(CC), '-Wall', '-Werror', *flags, '-I' + str(ROOT)]
    if CC.name.lower().startswith('tcc'):
        command = [*common, '-run', str(cpath)]
        done = subprocess.run(command, text=True, capture_output=True, timeout=45)
        return {'command': command, 'compile_and_run': True,
                'exit_code': done.returncode, 'stdout': done.stdout, 'stderr': done.stderr}
    binary = cpath.with_suffix('.exe' if os.name == 'nt' else '.host')
    command = [*common, '-std=c99', str(cpath), '-o', str(binary), '-lm']
    compiled = subprocess.run(command, text=True, capture_output=True, timeout=60)
    if compiled.returncode:
        return {'command': command, 'compile_returncode': compiled.returncode,
                'exit_code': compiled.returncode, 'stdout': compiled.stdout,
                'stderr': compiled.stderr, 'compiled': False}
    ran = subprocess.run([str(binary)], text=True, capture_output=True, timeout=45)
    return {'command': command, 'run_command': [str(binary)], 'compiled': True,
            'compile_returncode': 0, 'compile_diagnostics': compiled.stdout+compiled.stderr,
            'exit_code': ran.returncode, 'stdout': ran.stdout, 'stderr': ran.stderr}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load_gate():
    spec = importlib.util.spec_from_file_location('queue_stage_real_decl_gate', GATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build(gate, read, baseline):
    vo = read('video/out/vo.c')
    header = read('video/out/vo.h')
    fs = gate.functions(vo)
    producer = gate.functions(read('sub/osd.c'))['osd_get_secondary_sample_snapshot']
    original = gate.functions(baseline)['vo_is_ready_for_frame']['text']
    original = original.replace('vo_is_ready_for_frame(', 'vo_is_ready_v22(', 1)
    declarations, fragments, full = [], [], []
    legacy_dependencies = []
    for path in gate.HEADERS:
        if not (BASELINE / path).is_file():
            if path not in ('video/out/secondary_ass_queue_stage.h',
                            'video/out/secondary_ass_stage_prefix.h'):
                raise ValueError('unexpected absent baseline header: ' + path)
            legacy_dependencies.append({'file': path, 'new_V23_header': True,
                'baseline_file_present': False, 'candidate_sha256': sha(read(path).encode())})
            continue
        old = (BASELINE / path).read_text(encoding='utf-8')
        current_functions = gate.functions(read(path))
        for name, old_function in gate.functions(old).items():
            current = current_functions.get(name)
            same = current is not None and current['text'] == old_function['text']
            legacy_dependencies.append({'file': path, 'function': name,
                'same_verbatim_V22_function': same,
                'baseline_sha256': sha(old_function['text'].encode()),
                'candidate_sha256': sha(current['text'].encode()) if current else None})
            if not same:
                raise ValueError('shared old inline behavior changed: ' + path + ':' + name)
    chunks = [r'''
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
''']
    thread = read('osdep/threads-win32.h')
    aliases = re.findall(r'^typedef[^;]+\bmp_(?:cond|once|mutex|static_mutex|thread|thread_id)\s*;', thread, re.M)
    if len(aliases) != 6:
        raise ValueError('real thread typedef closure changed')
    chunks.extend(aliases)
    chunks.extend('#include "' + path + '"' for path in gate.HEADERS)
    for path in gate.HEADERS:
        read(path)
    read('video/out/secondary_ass_queue_stage.h')
    chunks.append('#include "video/out/secondary_ass_queue_stage.h"')
    read('video/out/secondary_ass_stage_prefix.h')
    chunks.append('#include "video/out/secondary_ass_stage_prefix.h"')
    read('misc/mp_assert.h')
    chunks.append('#include "misc/mp_assert.h"')
    for name in ('MPMIN', 'MPMAX', 'MPCLAMP'):
        found = re.findall(r'^#define\s+' + name + r'\([^\n]+', read('common/common.h'), re.M)
        if len(found) != 1:
            raise ValueError('actual macro closure changed: ' + name)
        chunks.extend(found)
    for name in ('MP_TIME_S_TO_NS', 'MP_TIME_MS_TO_NS'):
        found = re.findall(r'^#define\s+' + name + r'\([^\n]+', read('osdep/timer.h'), re.M)
        if len(found) != 1:
            raise ValueError('actual timer macro closure changed: ' + name)
        chunks.extend(found)
    masked = gate.mask_c(header)
    for token in ('VO_EVENT_LIVE_RESIZING', 'VO_CAP_NORETAIN'):
        matches = []
        for match in re.finditer(r'\benum\s*\{', masked):
            end = gate.balanced(masked, masked.index('{', match.start()))
            if re.search(r'\b' + token + r'\b', masked[match.start():end]):
                matches.append(header[match.start():end] + ';')
        if len(matches) != 1:
            raise ValueError('actual enum closure changed: ' + token)
        chunks.extend(matches)
    chunks.extend(re.findall(r'^#define\s+VO_MAX_REQ_FRAMES\s+[^\n]+', header, re.M))
    chunks.extend(re.findall(r'^struct\s+\w+\s*;', header, re.M))

    def declaration(path, name):
        source = read(path)
        if name == 'mp_vo_opts':
            masked = gate.mask_c(source)
            matches = list(re.finditer(r'\btypedef\s+struct\s+mp_vo_opts\s*\{', masked))
            if len(matches) != 1:
                raise ValueError('real mp_vo_opts typedef closure changed')
            start = matches[0].start()
            end = gate.balanced(masked, masked.index('{', start))
            suffix = re.match(r'\s*mp_vo_opts\s*;', masked[end:])
            if not suffix:
                raise ValueError('real mp_vo_opts alias suffix changed')
            text = source[start:end + suffix.end()]
            line = source.count('\n', 0, start) + 1
        else:
            text, line = gate.declaration(source, name)
        declarations.append({'file': path, 'struct': name, 'line': line, 'sha256': sha(text.encode())})
        chunks.append(f'#line {line} "{path}"\n{text}')

    declaration('options/m_option.h', 'm_geometry')
    declaration('options/options.h', 'mp_vo_opts')
    for name in gate.STRUCTS:
        declaration('video/out/vo.h', name)
    chunks.append('#define _WIN32 1')
    declaration('video/out/vo.c', 'vo_internal')
    declaration('video/out/vo.c', 'secondary_ass_grid_task')
    osd = read('sub/osd.h')
    for name, return_type in (('osd_get_secondary_refresh', 'double'),
                             ('osd_get_secondary_physical_sample_divisor', 'int64_t'),
                             ('osd_get_secondary_physical_next_sample_slot', 'int64_t'),
                             ('osd_get_secondary_physical_next_sample_time', 'int64_t'),
                             ('osd_get_secondary_next_sample_time', 'int64_t'),
                             ('osd_get_secondary_clock_rate', 'double'),
                             ('osd_hold_secondary_sample', 'void'),
                             ('osd_reset_secondary_clock', 'void'),
                             ('osd_get_secondary_sample_snapshot', 'struct secondary_ass_sample_snapshot')):
        pattern = r'\b' + return_type + r'\s+' + name + r'\s*\([^;{}]*\)\s*;'
        found = list(re.finditer(pattern, gate.mask_c(osd)))
        if len(found) != 1:
            raise ValueError('actual OSD prototype closure changed: ' + name)
        chunks.append(osd[found[0].start():found[0].end()])
    chunks.append(r'''
static unsigned checks, failures, wakeups, core_wakeups, free_calls;
static int lock_depth;
static int64_t clock_ns;
static mp_mutex *tracked_lock;
static double fixture_rate;
static int64_t fixture_divisor=2;
static struct secondary_ass_sample_snapshot fixture_snapshot;
static struct secondary_ass_clock fixture_clock;
static struct secondary_ass_sampler fixture_sampler;
static bool fixture_live_sampler,fixture_sample_forced;
static unsigned feedback_frames,early_prepare_positive;
static unsigned pose_holds,pose_set_calls;
static struct secondary_ass_grid_task actual_outer_task;
static struct mp_ass_pacing_record recorded;
#define CHECK(x) do { checks++; if (!(x)) { failures++; if(failures<=20) \
 fprintf(stderr,"check failed %u:%s:%d:%s\n",checks,__FILE__,__LINE__,#x); } } while(0)
static int64_t mp_time_ns(void) { return clock_ns; }
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
 (void)osd;CHECK(lock_depth==0);
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
 (void)global;(void)kind;recorded=*record; }
static void core_callback(void *ctx) { (void)ctx;core_wakeups++; }
static bool can_early(struct vo *vo,uint64_t generation,int64_t target,
                      void (*wait)(struct vo *,int64_t)) {
 (void)vo;(void)generation;(void)target;(void)wait;return true; }
''')
    # The full Atomic setter remains in the independent GCC integration gate.
    # This endpoint is deliberately observable rather than synthesizing its
    # behavior: fixed/no-grid must not call it; physical-grid may reach it.
    setter = fs['secondary_set_presentation']['text']
    setter_signature = setter[:gate.mask_c(setter).index('{')]
    chunks.append(setter_signature + r'''{
 (void)vo;(void)point;(void)fallback;(void)interval;(void)submit;
 (void)quiet_output;(void)forecast;(void)plan;
 pose_set_calls++;return false;
}
''')
    thread_fs = gate.functions(thread)
    for name in ('mp_mutex_lock', 'mp_mutex_unlock', 'mp_cond_broadcast'):
        f = thread_fs[name]
        chunks.append(f'#line {f["line"]} "osdep/threads-win32.h"\n{f["text"]}')
        full.append({'file': 'osdep/threads-win32.h', 'function': name, 'sha256': sha(f['text'].encode())})

    required = ('wakeup_locked', 'wakeup_core', 'get_current_frame_end', 'secondary_record_tag',
                'get_display_synced_frame_end', 'still_displaying',
                'vo_is_ready_for_frame', 'vo_queue_frame', 'read_opts',
                'vo_set_queue_params', 'forget_frames', 'reset_vsync_timings',
                'vo_set_paused', 'vo_seek_reset', 'secondary_plan_enabled',
                'secondary_plan_stale_reason', 'secondary_trace_plan',
                'secondary_trace_plan_missed', 'secondary_cache_block_cost',
                'secondary_forecast_enabled', 'secondary_physical_feedback',
                'secondary_fixed_forecast_offset', 'secondary_forecast_plan',
                'secondary_forecast_fresh_plan', 'secondary_forecast_next',
                'secondary_cache_plan', 'secondary_capture_grid_plan',
                'secondary_planning_state', 'secondary_next_sample',
                'secondary_cache_next_sample')
    selected = set(required)
    # Any newly factored stage helpers are actual full functions, not guessed
    # substitutes. Preserve their order in the source declaration closure.
    selected.update(name for name in fs if re.match(r'^secondary_.*stage', name))
    prototype = re.search(r'\bstatic\s+int64_t\s+secondary_stage_budget_resume\s*\([^;{}]+\)\s*;',
                          gate.mask_c(vo))
    if not prototype:
        raise ValueError('actual budget-resume forward declaration missing')
    budget_prototype = vo[prototype.start():prototype.end()]
    chunks.append(budget_prototype)
    fragments.append({'context': 'vo.c.actual_budget_resume_forward_declaration',
                      'sha256': sha(budget_prototype.encode()), 'text': budget_prototype})
    for name in sorted(selected, key=lambda name: fs[name]['line']):
        f = fs[name]
        chunks.append(f'#line {f["line"]} "video/out/vo.c"\n{f["text"]}')
        full.append({'file': 'video/out/vo.c', 'function': name, 'line': f['line'], 'sha256': sha(f['text'].encode())})
    chunks.append(original)

    def block(text, marker, name):
        start = text.index(marker)
        opening = gate.mask_c(text).index('{', start)
        end = gate.balanced(gate.mask_c(text), opening)
        piece = text[start:end]
        fragments.append({'context': name, 'sha256': sha(piece.encode()), 'text': piece})
        return piece

    render = fs['render_frame']['text']
    native_getter = re.search(r'\bdouble\s+native_rate\s*=\s*osd_get_secondary_refresh\([^;]+;',
                             gate.mask_c(render))
    if not native_getter:
        raise ValueError('actual render native_rate getter missing')
    native_rate = render[native_getter.start():native_getter.end()]
    fragments.append({'context': 'render_frame.actual_native_rate_getter',
                      'sha256': sha(native_rate.encode()), 'text': native_rate})
    def actual_statement(text, pattern, context):
        match = re.search(pattern, gate.mask_c(text))
        if not match:
            raise ValueError('actual statement missing: ' + context)
        statement = text[match.start():match.end()]
        fragments.append({'context': context, 'sha256': sha(statement.encode()),
                          'text': statement})
        return statement

    sample_divisor = actual_statement(render,
        r'\bint64_t\s+sample_divisor\s*=[^;]+;', 'render_frame.actual_sample_divisor_getter')
    queue_sample = actual_statement(render,
        r'\bstruct\s+secondary_ass_sample_snapshot\s+queue_sample\s*=[^;]+;',
        'render_frame.actual_queue_sample_getter')
    stage_prefix_clear = actual_statement(render,
        r'\bif\s*\(in->secondary_stage_prefix\.initialized\s*&&[^;]+;',
        'render_frame.stage_prefix_identity_clear')
    stage_guard = block(render, 'if (in->secondary_stage_pending.valid)', 'render_frame.stage_guard')
    legacy_guard = block(render, 'if (in->frame_queued && in->secondary_queue_pending.old_admission > 0)', 'render_frame.legacy_guard')
    promotion = block(render, 'if (in->frame_queued) {', 'render_frame.promotion')
    chunks.append(r'''
static bool promotion_boundary(struct vo *vo) {
 struct vo_internal *in=vo->in;
 struct secondary_ass_present_plan early_plan={0};
''' + native_rate + '\n' + sample_divisor + '\n' + queue_sample + r'''
 mp_mutex_lock(&in->lock);
''' + stage_prefix_clear + '\n' + stage_guard + '\n' + legacy_guard + '\n' + promotion + r'''
 (void)early_plan;mp_mutex_unlock(&in->lock);return true;
done:
 mp_mutex_unlock(&in->lock);return false;
}
''')
    redraw = fs['do_redraw']['text']
    pose_begin = redraw.index('    int64_t display_interval =')
    pose_end = redraw.index('    if (!secondary_target_updated && in->secondary_trace)', pose_begin)
    pose = redraw[pose_begin:pose_end]
    fragments.append({'context': 'do_redraw.actual_physical_and_pose_selection',
                      'sha256': sha(pose.encode()), 'text': pose})
    chunks.append(r'''
static bool actual_redraw_pose_boundary(struct vo *vo,
    const struct secondary_ass_grid_task *grid_task,bool *physical,
    bool *updated,struct secondary_ass_physical_point *selected) {
 struct vo_internal *in=vo->in;
 struct vo_frame dummy={0};
 struct vo_frame *frame=in->current_frame?in->current_frame:&dummy;
 int64_t video_duration=in->current_frame?in->current_frame->duration:0;
 int64_t grid_divisor=grid_task?grid_task->divisor:0;
''' + pose + r'''
 *physical=physical_phase;*updated=secondary_target_updated;*selected=physical_point;
 return true;
}
''')
    # The entire pre-render guard prefix is verbatim actual do_redraw source.
    # Stop before it acquires image references or enters GPU/driver work.
    redraw = fs['do_redraw']['text']
    opening = gate.mask_c(redraw).index('{')
    prefix_end = redraw.index('    in->request_redraw = false;', opening)
    redraw_prefix = redraw[opening + 1:prefix_end]
    fragments.append({'context': 'do_redraw.complete_pre_render_guard_prefix',
                      'sha256': sha(redraw_prefix.encode()), 'text': redraw_prefix})
    chunks.append(r'''
static bool actual_redraw_guard_boundary(struct vo *vo,uint64_t current_id,
    uint64_t queued_id,const struct secondary_ass_grid_task *grid_task) {
''' + redraw_prefix + r'''
    (void)stage_before; // Fragment stops before the real later resolve use.
    mp_mutex_unlock(&in->lock);
    return true;
}
''')
    feedback_start = redraw.index('secondary_physical_feedback(vo, &vsync, physical_point,')
    feedback_end = redraw.index(';', feedback_start) + 1
    feedback_call = redraw[feedback_start:feedback_end]
    fragments.append({'context': 'do_redraw.actual_physical_feedback_invocation',
                      'sha256': sha(feedback_call.encode()), 'text': feedback_call})
    chunks.append(r'''
static void actual_manual_feedback_boundary(struct vo *vo,
 const struct vo_vsync_info *input,struct secondary_ass_physical_point point) {
 struct vo_vsync_info vsync=*input;
 struct secondary_ass_physical_point physical_point=point;
 bool planned_audio=false;
 struct secondary_ass_present_plan present_plan={0};
''' + feedback_call + r'''
}
''')
    resolve = block(redraw[feedback_start:], 'if (grid_task && grid_task->stage.valid)',
                    'do_redraw.actual_after_feedback_prefix_resolve')
    chunks.append(r'''
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
''' + resolve + r'''
 feedback_frames++;
}
''')
    thread_text = fs['vo_thread']['text']
    staged_getter = re.search(r'\bdouble\s+staged_rate\s*=\s*in->secondary_queue_stage\s*\?\s*osd_get_secondary_refresh\([^;]+;',
                             gate.mask_c(thread_text))
    if not staged_getter:
        raise ValueError('actual outer staged_rate getter missing')
    staged_rate = thread_text[staged_getter.start():staged_getter.end()]
    fragments.append({'context': 'vo_thread.actual_staged_rate_getter',
                      'sha256': sha(staged_rate.encode()), 'text': staged_rate})
    staged_sample = actual_statement(thread_text,
        r'\bstruct\s+secondary_ass_sample_snapshot\s+staged_sample\s*=[^;]+;',
        'vo_thread.actual_staged_sample_getter')
    begin = thread_text.index('int64_t queue_resume =')
    end = thread_text.index('        mp_mutex_unlock(&in->lock);', begin)
    timer = thread_text[begin:end]
    fragments.append({'context': 'vo_thread.timer_and_end', 'sha256': sha(timer.encode()), 'text': timer})
    unbound = block(thread_text, 'if (queue_held && grid_task.point.slot <= 0) {', 'vo_thread.unbound')
    real_wait = re.search(r'\bint64_t\s+real_wait_until\s*=\s*wait_until\s*;', thread_text)
    if not real_wait:
        raise ValueError('actual real_wait_until capture missing')
    captured_real_wait = thread_text[real_wait.start():real_wait.end()]
    fragments.append({'context': 'vo_thread.real_wait_until_capture',
                      'sha256': sha(captured_real_wait.encode()), 'text': captured_real_wait})
    scheduler_start = thread_text.index('double secondary_rate =', end)
    scheduler_end = thread_text.index('        if (send_reset) {', scheduler_start)
    scheduler = thread_text[scheduler_start:scheduler_end]
    fragments.append({'context': 'vo_thread.complete_real_cache_scheduler_before_driver',
                      'sha256': sha(scheduler.encode()), 'text': scheduler})
    chunks.append(r'''
static int64_t outer_timer_boundary(struct vo *vo,bool working,bool bound,
                                    bool *manual_redraw_allowed) {
 struct vo_internal *in=vo->in;int64_t now=clock_ns;
 bool vo_paused=in->paused;(void)bound;
 int64_t wait_until=now+MP_TIME_S_TO_NS(working ? 0 : 1000);
''' + staged_rate + '\n' + staged_sample + r'''
 mp_mutex_lock(&in->lock);
''' + timer + r'''
 mp_mutex_unlock(&in->lock);
''' + scheduler + r'''
''' + unbound + r'''
 (void)send_pause; // Driver pause work is outside this CPU boundary.
 actual_outer_task=grid_task;
 *manual_redraw_allowed=redraw;return wait_until;
}
''')
    flag_begin = vo.index('const char *queue_lead = getenv(')
    flag_end = vo.index('    mp_dispatch_set_wakeup_fn', flag_begin)
    flag = vo[flag_begin:flag_end]
    fragments.append({'context': 'vo_create.flags_before_thread', 'sha256': sha(flag.encode()), 'text': flag})
    chunks.append(r'''
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
''' + flag + r'''
}
#undef getenv
''')
    compile_refs = '\n'.join(' (void)&' + name + ';' for name in sorted(selected))
    chunks.append('static void reference_selected_bodies(void) {\n' + compile_refs + '\n (void)&SetEvent;\n}')
    chunks.append(FIXTURE)
    return '\n'.join(chunks), {'real_complete_declarations': declarations,
            'actual_full_functions': full, 'actual_fragments': fragments,
            'nonexecuting_selected_body_address_references': sorted(selected),
            'V22_shared_inline_functions_unchanged': legacy_dependencies,
            'V22_readiness_renamed_sha256': sha(original.encode()),
            'OSD_snapshot_boundary': {'actual_producer_body_compiled': False,
                'mode': 'EXTERNAL_SCALAR_GETTER_WITH_REAL_CLOCK_AND_FORECAST_SAMPLER_CHAIN',
                'actual_producer_sha256': sha(producer['text'].encode()),
                'fixture_parameters': ['held=false', 'speed=requested_speed=1',
                    'has_output=true', 'physical_phase=true', 'actual sample_forced latch supplied'],
                'limitation': 'The full real Atomic OSD state/getter remains for the GCC gate; '
                    'no substitute osd_state declaration or removed Atomic field is used'}}


FIXTURE = r'''
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
int main(void) {
 reference_selected_bodies();
 legacy_same();legacy_active_token();stage_and_binding();lifecycle();
 cache_and_pre_render_guards();pressure_change_diagnostic();budget_resume_matrix();actual_prefix_chains();timers_and_flags();
 unsigned legacy_checks=checks;
 CHECK(legacy_checks==102298);
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
 return failures ? 7 : 0;
}
'''


def main():
    global ROOT, BASELINE, CC, GATE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--cc', required=True)
    parser.add_argument('--gate', type=Path,
        default=Path(__file__).with_name('verify-native-ass-integration.py'))
    parser.add_argument('--output', '--out', dest='out', type=Path, required=True)
    parser.add_argument('--mutants', action='store_true')
    args = parser.parse_args()
    ROOT, BASELINE, GATE = args.source.resolve(), args.baseline.resolve(), args.gate.resolve()
    found = shutil.which(args.cc)
    if not found:
        parser.error('compiler not found: ' + args.cc)
    CC = Path(found).resolve()
    if ROOT == BASELINE or not ROOT.is_dir() or not BASELINE.is_dir() or not GATE.is_file():
        parser.error('require distinct existing source/baseline and a real declaration gate')
    args.out.mkdir(parents=True, exist_ok=False)
    captured = {}

    def read(path):
        if path not in captured:
            captured[path] = (ROOT / path).read_bytes()
        return captured[path].decode('utf-8')

    baseline = (BASELINE / 'video/out/vo.c').read_bytes()
    if sha(baseline) != 'e4e7bd710c84c43af548a66e8950cfb69814db478a4a889239572d3292bafefd':
        parser.error('baseline VO is not the frozen V22 reference')
    report = {'status': 'SOURCE_IN_PROGRESS_NOT_FROZEN', 'GPU_started': False,
              'CI_started': False, 'pacing_acceptance': False,
              'scope': 'REAL_VO_DECLARATIONS_ACTUAL_C_CALLERS_AND_LOOP_FRAGMENTS',
              'OSD_getter_actual_body_compiled': False,
              'boundary_stubs': ['opaque Windows types/endpoints with real mpv lock wrappers',
                  'actual OSD getter prototypes with external scalar snapshot fixture',
                  'actual OSD hold/setter signatures with observable external endpoints; '
                  'the Atomic bodies remain in the separate default GCC gate',
                  'talloc free, logging and pacing recording endpoints'],
              'not_covered': ['complete VO thread, real AO/OS scheduler/GPU/display',
                  'actual OSD state _Atomic/getter body, Windows ABI',
                  'cache image ownership/GPU/Present work after the extracted '
                  'pre-render guard and physical/pose-selection fragments',
                  'actual baseline wakeup/prepare coverage and video pacing after '
                  'a post-queue pressure rise remain UNKNOWN; the CPU boundary only '
                  'checks the original resampled formula and finite min timer'],
              'baseline_source': str(BASELINE), 'baseline_vo_sha256': sha(baseline),
              'tool_sha256': sha(Path(__file__).read_bytes()),
              'declaration_gate_tool_sha256': sha(GATE.read_bytes())}
    try:
        generated, evidence = build(load_gate(), read, baseline.decode('utf-8'))
        report.update(evidence)
        report['translation_sha256'] = sha(generated.encode())
        cpath = args.out / 'actual-source-fragments.c'
        cpath.write_text(generated, encoding='utf-8', newline='\n')
        report['actual_C'] = {}
        for name, flags in (('normal', []), ('NDEBUG', ['-DNDEBUG'])):
            item = execute_c(cpath, flags)
            try:
                item['result'] = json.loads(item['stdout'])
            except ValueError:
                pass
            report['actual_C'][name] = item
        if args.mutants:
            report['mutants'] = execute_mutants(load_gate(), generated, args.out)
            report['v24_mutants'] = execute_v24_mutants(load_gate(), generated, args.out)
        unchanged = [path for path, data in captured.items()
                     if (ROOT / path).read_bytes() != data]
        report['inputs_changed_during_run'] = unchanged
        passed = not unchanged and all(item['exit_code'] == 0 and
                    item.get('result', {}).get('failures') == 0 and
                    item.get('result', {}).get('checks') == 102298 and
                    item.get('result', {}).get('v24_checks') == 1047 and
                    item.get('result', {}).get('actual_feedback_frames') == 312 and
                    item.get('result', {}).get('early_prepare_positive') == 12
                    for item in report['actual_C'].values())
        if args.mutants:
            passed &= all(item['compiled_and_rejected']
                          for item in report['mutants'].values())
            passed &= len(report['v24_mutants']) == 5 and all(
                item['compiled_and_rejected'] for item in report['v24_mutants'].values())
        report['status'] = 'ACTUAL_VO_CPU_BOUNDARY_PASS_NOT_RUNTIME' if passed else 'ACTUAL_VO_CPU_BOUNDARY_FAIL'
    except (ValueError, KeyError, OSError, subprocess.TimeoutExpired) as error:
        report['status'] = 'ACTUAL_VO_CPU_CLOSURE_FAIL'
        report['error'] = str(error)
        passed = False
    report['source_sha256'] = {path: sha(data) for path, data in captured.items()}
    target = args.out / 'actual-C-evidence.json'
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'status': report['status'], 'report': str(target),
                     'sha256': sha(target.read_bytes()),
                     'actual_C': {name: {'exit_code': item['exit_code'],
                         'checks': item.get('result', {}).get('checks'),
                         'failures': item.get('result', {}).get('failures'),
                         'diagnostics': item['stderr'] if item['exit_code'] else ''}
                         for name, item in report.get('actual_C', {}).items()},
                     'mutants': {name: item['compiled_and_rejected']
                         for name, item in report.get('mutants', {}).items()},
                     'v24_mutants': {name: item['compiled_and_rejected']
                         for name, item in report.get('v24_mutants', {}).items()},
                     'error': report.get('error')}, ensure_ascii=False))
    return 0 if passed else 1


def execute_mutants(gate, generated, out):
    functions = gate.functions(generated)

    def replace_function(name, before, after):
        original = functions[name]['text']
        if original.count(before) != 1:
            raise ValueError('mutation boundary absent/nonunique: ' + name + ':' + before)
        changed = original.replace(before, after, 1)
        if generated.count(original) != 1:
            raise ValueError('actual mutation function absent/nonunique: ' + name)
        return generated.replace(original, changed, 1)

    affordable = functions['secondary_stage_cache_current']['text']
    start = affordable.index('secondary_ass_budget_affordable(')
    opening = start + len('secondary_ass_budget_affordable')
    end = gate.balanced(gate.mask_c(affordable), opening, '(', ')')
    affordable_call = affordable[start:end]
    timer = functions['outer_timer_boundary']['text']
    capture = re.search(r'\bwait_until\s*=\s*held_stage\.valid[^;]+;',
                        gate.mask_c(timer))
    if not capture:
        raise ValueError('actual staged timer min mutation boundary missing')
    timer_assignment = timer[capture.start():capture.end()]
    specs = {
        'stage_off_accidentally_enabled': ('vo_is_ready_for_frame',
            'in->secondary_queue_stage && isfinite(secondary_rate)',
            'isfinite(secondary_rate)'),
        'actual_bind_admission_ignored': ('vo_queue_frame',
            'mp_time_ns() >= stage.admission', 'true'),
        'queue_hold_not_published': ('vo_queue_frame',
            'in->secondary_queue_resume = stage.resume;',
            'in->secondary_queue_resume = 0;'),
        'incoming_pressure_ignored': ('secondary_stage_cache_current',
            affordable_call, 'true'),
        'expired_hold_never_released': ('promotion_boundary',
            'now < resume', '((void)resume, true)'),
        'timer_min_erased': ('outer_timer_boundary', timer_assignment,
            '(void)real_wait_until;\n    wait_until = queue_resume;'),
        'timing_cap_change_keeps_authority': ('read_opts',
            'secondary_ass_queue_stage_clear(&in->secondary_stage_pending);',
            '(void)in->secondary_stage_pending;'),
        'pressure_resume_stuck_at_capture': ('secondary_stage_budget_resume',
            'return MPMIN(stage->resume, stage->due - lead);', 'return stage->resume;'),
        'cache_ignores_current_budget_boundary': ('secondary_stage_cache_current',
            'secondary_stage_budget_resume(vo, stage, rate, now)', 'stage->resume'),
        'backend_fallback_end_not_checked': ('actual_feedback_resolve_boundary',
            'stage_flip_end >= trace_deadline', '((void)stage_flip_end, false)'),
        'future_cache_wake_lost': ('outer_timer_boundary',
            'staged_cache_wake = next;', 'staged_cache_wake = 0;'),
        'outer_current_budget_timer_omitted': ('outer_timer_boundary',
            'secondary_stage_budget_resume(vo, &held_stage, staged_rate, now)',
            '((void)staged_rate, queue_resume)'),
    }
    guard = functions['promotion_boundary']['text']
    start = guard.index('secondary_ass_stage_prefix_can_promote(')
    opening = start + len('secondary_ass_stage_prefix_can_promote')
    end = gate.balanced(gate.mask_c(guard), opening, '(', ')')
    specs['continuous_prefix_proof_ignored'] = ('promotion_boundary', guard[start:end], 'true')
    start = guard.index('secondary_ass_stage_prefix_stage_equal(')
    opening = start + len('secondary_ass_stage_prefix_stage_equal')
    end = gate.balanced(gate.mask_c(guard), opening, '(', ')')
    comparison = guard[start:end]
    specs['same_stage_failed_prefix_restarted'] = ('promotion_boundary', '!'+comparison,
        '(!in->secondary_stage_prefix.valid || !'+comparison+')')
    # Remove only the actual owner's exact-current call, retaining the rest
    # of its lifecycle contract. Real structs and functions remain compiled.
    owner = functions['secondary_stage_owner']['text']
    start = owner.index('secondary_ass_queue_stage_current(')
    opening = start + len('secondary_ass_queue_stage_current')
    end = gate.balanced(gate.mask_c(owner), opening, '(', ')')
    specs['real_frame_offset_identity_ignored'] = (
        'secondary_stage_owner', owner[start:end], 'true')
    results = {}
    for name, (function, before, after) in specs.items():
        mutated = replace_function(function, before, after)
        path = out / (name + '.c')
        path.write_text(mutated, encoding='utf-8', newline='\n')
        execution = execute_c(path, ['-DNDEBUG'])
        try:
            actual = json.loads(execution['stdout'])
        except ValueError:
            actual = {}
        rejected = execution['exit_code'] == 7 and actual.get('failures', 0) > 0
        results[name] = {**execution, 'returncode': execution['exit_code'],
            'compiled_and_rejected': rejected, 'result': actual,
            'translation_sha256': sha(mutated.encode()),
            'mutation_scope': 'generated actual C closure only; source/raw unchanged'}
    return results


def execute_v24_mutants(gate, generated, out):
    functions = gate.functions(generated)
    specs = {
        'fixed_recovery_probe_loses_grid': ('outer_timer_boundary',
            '.recovery_probe = in->secondary_fixed_forecast && probe,',
            '.recovery_probe = false,'),
        'physical_probe_permission_ignored': ('actual_redraw_pose_boundary',
            'in->secondary_fixed_forecast && grid_task && grid_task->recovery_probe',
            'false'),
        'unbound_manual_pose_recomputed': ('actual_redraw_pose_boundary',
            'bool fixed_pose_reuse = in->secondary_fixed_forecast && !grid_task &&\n        !frame->display_synced;',
            'bool fixed_pose_reuse = false;'),
        'unbound_manual_pose_not_held': ('actual_redraw_pose_boundary',
            'osd_hold_secondary_sample(vo->osd);', '(void)vo->osd;'),
        'unknown_generation_forgets_fixed_offset': ('secondary_fixed_forecast_offset',
            'struct vo_internal *in = vo->in;',
            'struct vo_internal *in = vo->in;\n'
            '    if (!in->secondary_physical.success_generation)\n'
            '        in->secondary_fixed_offset.valid = false;'),
    }
    results = {}
    for name, (function, before, after) in specs.items():
        actual = functions[function]['text']
        if actual.count(before) != 1 or generated.count(actual) != 1:
            raise ValueError('V24 actual fault boundary absent/nonunique: ' + name)
        text = generated.replace(actual, actual.replace(before, after, 1), 1)
        path = out / (name + '.c')
        path.write_text(text, encoding='utf-8', newline='\n')
        execution = execute_c(path, ['-DNDEBUG'])
        try:
            measured = json.loads(execution['stdout'])
        except ValueError:
            measured = {}
        results[name] = {**execution,
            'compiled_and_rejected': execution['exit_code'] == 7 and measured.get('failures', 0) > 0,
            'result': measured, 'translation_sha256': sha(text.encode()),
            'mutation_scope': 'generated actual V24 C fragment only; source unchanged'}
    return results


if __name__ == '__main__':
    raise SystemExit(main())
