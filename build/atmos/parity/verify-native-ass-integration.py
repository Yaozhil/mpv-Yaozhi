#!/usr/bin/env python3
"""Cheap, CPU-only Native ASS declaration/consumer integration gate.

This is deliberately NOT a complete mpv build or runtime test.  It compiles
complete, verbatim mpv declarations and selected verbatim VO functions, plus
member expressions taken from actual GPU consumers.  No mpv struct is inferred
from member uses.  Only opaque Windows platform types and logging are boundary
stubs; they make no layout, ABI, thread-safety, GPU or Display claim.
"""

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path


STRUCTS = ("vo_extra", "vo_frame", "vo_vsync_info", "vo_driver", "vo")
FUNCTIONS = (
    "secondary_record_tag", "vo_pacing_span_at", "vo_pacing_span_now",
    "secondary_record_begin", "secondary_record_end",
    "secondary_reset_physical", "reset_secondary_ass_budget",
    "secondary_plan_enabled", "secondary_cache_block_cost",
    "secondary_observe_flip_budget", "secondary_planning_state",
    "secondary_trace_plan", "secondary_trace_plan_missed",
    "secondary_plan_stale_reason",
    "wakeup_locked", "vo_is_ready_for_frame", "vo_queue_frame",
    "secondary_publish_queue_hint",
)
CONSUMERS = (
    "video/out/vo.c", "video/out/d3d11/context.c",
    "video/out/vo_gpu_next.c",
)
HEADERS = (
    "common/ass_pacing_record.h", "video/out/secondary_ass_budget.h",
    "video/out/secondary_ass_flip_budget.h",
    "video/out/secondary_ass_presentation.h",
    "video/out/secondary_ass_physical.h",
    "video/out/secondary_ass_present_plan.h",
    "sub/secondary_ass_clock.h", "video/out/secondary_ass_queue_lead.h",
    "video/out/secondary_ass_queue_stage.h",
    "video/out/secondary_ass_stage_prefix.h",
)


def mask_c(text):
    """Mask comments/literals without moving offsets or line numbers."""
    pattern = r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\''
    return re.sub(pattern, lambda m: re.sub(r"[^\n]", " ", m[0]), text,
                  flags=re.S)


def balanced(masked, start, opening="{", closing="}"):
    if masked[start] != opening:
        raise ValueError("expected balanced opening token")
    depth = 0
    for end in range(start, len(masked)):
        if masked[end] == opening:
            depth += 1
        elif masked[end] == closing:
            depth -= 1
            if not depth:
                return end + 1
    raise ValueError("unbalanced source declaration")


def declaration(text, name):
    masked = mask_c(text)
    matches = list(re.finditer(r"\bstruct\s+" + re.escape(name) + r"\s*\{", masked))
    if len(matches) != 1:
        raise ValueError(f"expected one real complete struct {name}, got {len(matches)}")
    match = matches[0]
    end = balanced(masked, masked.index("{", match.start()))
    if masked[end:].lstrip()[:1] != ";":
        raise ValueError(f"struct {name} has an unsupported declaration suffix")
    return text[match.start():end] + ";", text.count("\n", 0, match.start()) + 1


def functions(text):
    masked = mask_c(text)
    found = {}
    pattern = r"^[A-Za-z_][^\n;{}=]*?\b([A-Za-z_]\w*)\s*\("
    for match in re.finditer(pattern, masked, re.M):
        start_paren = masked.index("(", match.start(), match.end())
        end_paren = balanced(masked, start_paren, "(", ")")
        opening = end_paren
        while opening < len(masked) and masked[opening].isspace():
            opening += 1
        if opening >= len(masked) or masked[opening] != "{":
            continue
        end = balanced(masked, opening)
        name = match[1]
        if name in found:
            raise ValueError(f"duplicate function definition: {name}")
        found[name] = {
            "text": text[match.start():end],
            "masked": masked[match.start():end],
            "signature": text[match.start():opening].strip(),
            "line": text.count("\n", 0, match.start()) + 1,
        }
    return found


def meson_uncomment(text):
    # Preserve quoted strings; a '#' in a quoted argument is not a comment.
    return re.sub(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|#[^\n]*",
                  lambda m: "" if m[0].startswith("#") else m[0], text)


def meson_check(source, variant, read):
    build = meson_uncomment(read("meson.build"))
    options = meson_uncomment(read("meson.options"))
    defined = set(re.findall(r"\boption\s*\(\s*['\"]([^'\"]+)['\"]", options))
    referenced = set(re.findall(r"\bget_option\s*\(\s*['\"]([^'\"]+)['\"]", build))
    # These are Meson's built-in options, rather than project option() entries.
    builtins = {"buildtype", "debug", "optimization", "b_ndebug", "b_lto",
                "default_library", "prefix", "bindir", "libdir", "datadir",
                "includedir", "mandir", "sysconfdir", "localedir", "c_args",
                "c_link_args", "cpp_args", "cpp_link_args", "warning_level",
                "werror", "wrap_mode", "backend", "install_umask"}
    errors = []
    missing_options = sorted(referenced - defined - builtins)
    if missing_options:
        errors.append("get_option references undefined project options: " + ", ".join(missing_options))
    # Header strings also occur in cc.has_header() SDK probes and are not
    # project files. This tier checks literal implementation source paths.
    listed = re.findall(r"['\"]((?:[A-Za-z0-9_.+-]+/)+[A-Za-z0-9_.+-]+\.(?:c|cpp))['\"]", build)
    missing_sources = sorted({path for path in listed if not (source / path).is_file()})
    if missing_sources:
        errors.append("Meson literal implementation source paths are missing: " + ", ".join(missing_sources))
    if listed.count("common/ass_pacing_record.c") != 1:
        errors.append("common/ass_pacing_record.c must occur once in Meson source closure")
    atmos_sources = ("audio/decode/ad_orender.c", "common/orender_dl.c",
                     "player/orender_overlay.c", "audio/out/ao_asio.c")
    if variant == "main":
        for option in ("orender", "asio", "asio-sdk"):
            if option in referenced:
                errors.append(f"main source unexpectedly references Atmos option {option}")
        for path in atmos_sources:
            if path in listed:
                errors.append(f"main source unexpectedly includes Atmos source {path}")
    else:
        for option in ("orender", "asio", "asio-sdk"):
            if option not in defined or option not in referenced:
                errors.append(f"Atmos option closure incomplete: {option}")
        for path in atmos_sources:
            if path not in listed or not (source / path).is_file():
                errors.append(f"Atmos source closure incomplete: {path}")
        for feature, paths in (("orender", atmos_sources[:3]), ("asio", atmos_sources[3:])):
            block = re.search(r"if\s+features\[['\"]" + feature +
                              r"['\"]\](.*?)\bendif\b", build, re.S)
            if not block or any(path not in block[1] for path in paths):
                errors.append(f"Atmos {feature} sources are not inside their feature block")
    return {"pass": not errors, "errors": errors,
            "missing_options": missing_options, "missing_sources": missing_sources,
            "literal_source_count": len(listed), "scope": "MESON_LITERAL_OPTION_SOURCE_CLOSURE_NOT_MESON_SETUP"}


def consumer_expressions(path, text):
    """Compile actual member names against real types, without inferring types.

    GPU function bodies contain hundreds of external SDK declarations.  This
    smaller tier checks only direct VO/VO-frame/feedback/driver field operands.
    Original source function and line are retained for every operand.  Aliases
    are derived only from explicit struct declarations or known real ra_ctx.vo
    linkage, not from whatever members happen to be used.
    """
    expressions = []
    for name, function in functions(text).items():
        aliases = {}
        for match in re.finditer(r"\bstruct\s+(vo|vo_frame|vo_vsync_info|vo_driver)\s*\*\s*(\w+)", function["masked"]):
            aliases[match[2]] = match[1]
        masked = function["masked"]
        for match in re.finditer(r"\b(\w+)\s*->\s*(\w+)", masked):
            alias, field = match.groups()
            if alias not in aliases:
                continue
            struct_name = aliases[alias]
            canonical = {"vo": "vo", "vo_frame": "frame", "vo_vsync_info": "info", "vo_driver": "driver"}[struct_name]
            expressions.append((f"{canonical}->{field}", name,
                                function["line"] + masked.count("\n", 0, match.start())))
        for match in re.finditer(r"\b(?:ctx|ra)->vo->(\w+)|\bsw->ctx->vo->(\w+)|\bvo->driver->(\w+)", masked):
            expression = "driver->" + match[3] if match[3] else "vo->" + (match[1] or match[2])
            expressions.append((expression, name,
                                function["line"] + masked.count("\n", 0, match.start())))
    return expressions


FORECAST_RUNTIME_C = r'''
#ifdef MP_V23_FORECAST_CALLER_TEST
#include <stdio.h>
#include <stdlib.h>
#include <math.h>
static unsigned caller_checks;
static int64_t fixture_now;
static bool fixture_forecast_env;
static bool fixture_fixed_env;
#define CALLER_CHECK(x) do { caller_checks++; if (!(x)) { \
 fprintf(stderr,"actual caller check %u failed:%d:%s\n",caller_checks,__LINE__,#x);exit(2); } } while(0)
// Explicit OS/timer/log/record endpoints only. The mpv lock wrappers,
// complete state, setters, getter and selected sample branch are verbatim.
void AcquireSRWLockExclusive(SRWLOCK *p) { CALLER_CHECK(!*p);*p=(void*)1; }
void ReleaseSRWLockExclusive(SRWLOCK *p) { CALLER_CHECK(*p==(void*)1);*p=NULL; }
void WakeAllConditionVariable(CONDITION_VARIABLE *p) { (void)p; }
int SetEvent(HANDLE p) { (void)p;return 1; }
DWORD GetCurrentThreadId(void) { return 1; }
int64_t mp_thread_cpu_time_ns(mp_thread_id thread_id) { (void)thread_id;return 0; }
int64_t mp_time_ns(void) { return fixture_now; }
void integration_log(const char *fmt, ...) { (void)fmt; }
char *integration_getenv(const char *name) {
 if(!strcmp(name,"MPV_NATIVE_DISPLAY_FORECAST"))return fixture_forecast_env ? "1" : NULL;
 return fixture_fixed_env && !strcmp(name,"MPV_NATIVE_FIXED_FORECAST") ? "1" : NULL;
}
bool mp_ass_pacing_enabled(struct mpv_global *global) { (void)global;return false; }
void mp_ass_pacing_record(struct mpv_global *global,uint32_t kind,
                         const struct mp_ass_pacing_record *record) {
 (void)global;(void)kind;(void)record;
}
void osd_set_ass_pacing_scope(struct osd_state *osd,uint64_t vo_seq,
                            uint64_t draw_seq,uint64_t frame_id) {
 (void)osd;(void)vo_seq;(void)draw_seq;(void)frame_id;
}

static void fixture_initialize(struct vo *vo,struct vo_internal *in,
                               struct osd_state *osd,struct vo_frame *frame,
                               int64_t T,int64_t N) {
 *in=(struct vo_internal){0};*osd=(struct osd_state){0};*frame=(struct vo_frame){0};
 *vo=(struct vo){.in=in,.osd=osd};
 in->secondary_present_plan=true;in->secondary_present_grid=true;
 in->secondary_display_forecast=true;in->current_frame=frame;
 in->reported_display_fps=1e9/T;
 in->secondary_physical=(struct secondary_ass_physical){
  .phase=1000000000,.phase_slot=100,.interval=T,.epoch=7,
  .sync_qpc_ns=1000000000,.sync_count=100,.sync_slot=100,
  .sync_segment_consistent=true,.measure_qpc_ns=1000000000,.measure_count=100,
  .periods={T,T,T},.period_count=3,.period_next=3,
  .delay=1,.delay_samples={1,1,1},.delay_count=3,.success_generation=3,
 };
 osd->secondary_rate=1e9/(T*N);osd->secondary_speed=1;osd->secondary_requested_speed=1;
 osd->secondary_has_output=true;
 osd->secondary_clock=(struct secondary_ass_clock){
  .valid=true,.pts=10,.speed=1,.wall=1000000000,
 };
 fixture_now=1000000000+9*T;
}

static void actual_registration(struct vo *vo,
    const struct secondary_ass_present_plan *plan,uint64_t id,int64_t actual_slot) {
 struct secondary_ass_physical *p=&vo->in->secondary_physical;
 struct secondary_ass_physical_point actual=secondary_ass_physical_point_at(p,actual_slot);
 struct vo_vsync_info info={
  .secondary_submit_valid=true,.secondary_submit_id=id,
  .secondary_submit_generation=3,.secondary_submit_sync_interval=1,
  .secondary_sync_qpc_ns=actual.wall,.secondary_sync_time=actual.wall,
  .secondary_sync_refresh_count=(uint32_t)actual.slot,
  .secondary_present_refresh_count=(uint32_t)actual.slot,.secondary_present_id=id,
 };
 secondary_physical_feedback(vo,&info,plan->target,plan);
 unsigned saved=(p->next+31)%32;
 CALLER_CHECK(p->submitted[saved].id==id);
 CALLER_CHECK(p->submitted[saved].base_slot==plan->base.slot);
 CALLER_CHECK(p->submitted[saved].target_slot==plan->target.slot);
 CALLER_CHECK(p->phase_slot==actual_slot && p->historical_id==id);
 CALLER_CHECK(p->last_base_slot==plan->base.slot);
}

static void caller_rate(int hz,int64_t N) {
 int64_t T=INT64_C(1000000000)/hz;
 struct vo vo;struct vo_internal in;struct osd_state osd;struct vo_frame frame;
 fixture_initialize(&vo,&in,&osd,&frame,T,N);
 struct secondary_ass_physical *p=&in.secondary_physical;
 struct secondary_ass_present_plan plan=secondary_ass_present_plan_make_forecast(p,
  secondary_ass_physical_point_at(p,110));
 CALLER_CHECK(plan.valid);
 CALLER_CHECK(integration_actual_fresh_raw_guard(&vo,plan,plan.base.wall));
 CALLER_CHECK(!integration_actual_fresh_raw_guard(&vo,plan,plan.base.wall+1));
 CALLER_CHECK(plan.valid && plan.base.slot==110 && plan.target.slot==111);
 CALLER_CHECK(secondary_set_presentation(&vo,plan.target,0,T,plan.submit,false,true,&plan));
 double pts=0;
 CALLER_CHECK(integration_actual_sample_selection(&osd,&pts));
 struct secondary_ass_sample_snapshot s=osd_get_secondary_sample_snapshot(&osd);
 CALLER_CHECK(s.valid && s.display_forecast && s.origin_slot==110 && s.sample_slot==110);
 CALLER_CHECK(s.next_slot==110+N && s.next_wall==secondary_ass_physical_point_at(p,110+N).wall);
 CALLER_CHECK(osd.secondary_sampler.sample_wall==plan.target.wall);
 CALLER_CHECK(!integration_actual_sample_selection(&osd,&pts));
 CALLER_CHECK(osd.secondary_sampler.tick==0 && osd.secondary_sampler.display_slot==111);
 actual_registration(&vo,&plan,1,plan.target.slot);
 CALLER_CHECK(p->delay==1); // The real wrapper stores G, not D-currentH.

 osd.secondary_sampler.force=true;
 CALLER_CHECK(integration_actual_sample_selection(&osd,&pts));
 s=osd_get_secondary_sample_snapshot(&osd);
 CALLER_CHECK(!s.force && s.sample_forced);
 CALLER_CHECK(osd.secondary_sampler.tick==0 && osd.secondary_sampler.display_slot==111);
 plan=secondary_ass_present_plan_make_forecast(p,
  secondary_ass_physical_point_at(p,s.next_slot));
 CALLER_CHECK(secondary_set_presentation(&vo,plan.target,0,T,plan.submit,false,true,&plan));
 CALLER_CHECK(integration_actual_sample_selection(&osd,&pts));
 s=osd_get_secondary_sample_snapshot(&osd);
 CALLER_CHECK(s.valid && !s.sample_forced && s.sample_slot==110+N);

 // Simulate a static/empty bitmap boundary. The real getter keeps clock
 // rate/grid authority; libass and actual output discovery remain untested.
 osd.secondary_has_output=false;
 int64_t origin_slot=osd.secondary_sampler.origin_slot;
 int64_t origin_wall=osd.secondary_sampler.origin_wall;
 int64_t saved_base=p->last_base_slot;
 for(int k=0;k<16;k++) {
  int64_t next=secondary_ass_sampler_next_slot(&osd.secondary_sampler);
  struct secondary_ass_physical_point first=secondary_ass_physical_point_at(p,next);
  fixture_now=first.wall+T/2;
  // For N2 this naked prediction is odd while the original G grid is even.
  if(N==2)CALLER_CHECK((secondary_ass_physical_predict_point(
   &(struct secondary_ass_physical){.phase=p->phase,.phase_slot=p->phase_slot,
      .interval=p->interval,.epoch=p->epoch},fixture_now).slot-origin_slot)%N!=0);
  CALLER_CHECK(secondary_set_presentation(&vo,(struct secondary_ass_physical_point){0},
   0,T,fixture_now,true,true,NULL));
  CALLER_CHECK(integration_actual_sample_selection(&osd,&pts));
  CALLER_CHECK(osd.secondary_sampler.origin_slot==origin_slot);
  CALLER_CHECK(osd.secondary_sampler.origin_wall==origin_wall);
  CALLER_CHECK((secondary_ass_sampler_next_slot(&osd.secondary_sampler)-origin_slot)%N==0);
  CALLER_CHECK(p->last_base_slot==saved_base); // Quiet pose is not a Present.
 }
 osd.secondary_has_output=true;
 s=osd_get_secondary_sample_snapshot(&osd);
 CALLER_CHECK(s.valid && !s.held && s.display_forecast);
 plan=secondary_ass_present_plan_make_forecast(p,secondary_ass_physical_point_at(p,s.next_slot));
 CALLER_CHECK(secondary_set_presentation(&vo,plan.target,0,T,plan.submit,false,true,&plan));
 CALLER_CHECK(integration_actual_sample_selection(&osd,&pts));
 CALLER_CHECK(osd.secondary_sampler.origin_slot==origin_slot);

 // A colliding new D is an explicit held ASS MISS; a real successful primary
 // Present may register G. Its next task skips attempted G without renaming D.
 fixture_initialize(&vo,&in,&osd,&frame,T,1);
 plan=secondary_ass_present_plan_make_forecast(p,secondary_ass_physical_point_at(p,110));
 CALLER_CHECK(secondary_set_presentation(&vo,plan.target,0,T,plan.submit,false,true,&plan));
 CALLER_CHECK(integration_actual_sample_selection(&osd,&pts));
 actual_registration(&vo,&plan,1,111);
 p->delay=0; // Synthetic decreasing capture; the unchanged learner is below.
 struct secondary_ass_present_plan missed=secondary_ass_present_plan_make_forecast(p,
  secondary_ass_physical_point_at(p,111));
 CALLER_CHECK(missed.valid && missed.target.slot==osd.secondary_sampler.display_slot);
 CALLER_CHECK(!secondary_set_presentation(&vo,missed.target,0,T,missed.submit,false,true,&missed));
 CALLER_CHECK(!integration_actual_sample_selection(&osd,&pts));
 CALLER_CHECK(osd.secondary_sample_held && osd.secondary_sampler.tick==0);
 actual_registration(&vo,&missed,2,112);
 CALLER_CHECK(missed.target.slot==111 && p->delay==1);
 struct secondary_ass_physical_point first=secondary_next_sample(&vo,1);
 CALLER_CHECK(first.slot==111);
 struct secondary_ass_physical_point next=secondary_cache_next_sample(&vo,first,1,
  secondary_ass_physical_point_at(p,112).wall-T,osd.secondary_rate);
 CALLER_CHECK(next.slot==112);
 plan=secondary_ass_present_plan_make_forecast(p,next);
 CALLER_CHECK(secondary_set_presentation(&vo,plan.target,0,T,plan.submit,false,true,&plan));
 CALLER_CHECK(integration_actual_sample_selection(&osd,&pts));
 CALLER_CHECK(osd.secondary_sampler.origin_slot==110 && osd.secondary_sampler.tick==2);

 struct vo_vsync_info failed={.secondary_submit_id=3,.secondary_submit_generation=3};
 saved_base=p->last_base_slot;
 secondary_physical_feedback(&vo,&failed,plan.target,&plan);
 CALLER_CHECK(p->last_base_slot==saved_base); // Failed ID cannot consume G.
}

static void fixed_caller_rate(int hz,int64_t N) {
 int64_t T=INT64_C(1000000000)/hz;
 struct vo vo;struct vo_internal in;struct osd_state osd;struct vo_frame frame;
 fixture_initialize(&vo,&in,&osd,&frame,T,N);
 in.secondary_fixed_forecast=true;
 struct secondary_ass_physical *p=&in.secondary_physical;
 p->success_contiguous=true;
 const int historical[]={1,0,2,0,3,1,0,4};
 for(unsigned k=0;k<sizeof(historical)/sizeof(historical[0]);k++) {
  p->delay=historical[k]; // Distinct synthetic H input, not altered production learner.
  int64_t G=110+(int64_t)k*N;
  struct secondary_ass_physical_point point=secondary_ass_physical_point_at(p,G);
  struct secondary_ass_present_plan plan=secondary_forecast_plan(&vo,point,N,osd.secondary_rate);
  CALLER_CHECK(plan.valid && plan.base.slot==G && plan.target.slot==G+1);
  CALLER_CHECK(plan.historical_delay==historical[k] && plan.captured_forecast==1);
  CALLER_CHECK(in.secondary_fixed_offset.valid && in.secondary_fixed_offset.offset==1);
  CALLER_CHECK(p->delay==historical[k] && plan.submit==plan.fallback_submit);
  struct secondary_ass_physical submit_view=secondary_ass_present_plan_view(p);
  CALLER_CHECK(plan.submit==secondary_ass_physical_submit_time(&submit_view,plan.target.wall));
  struct secondary_ass_present_plan fresh=secondary_forecast_fresh_plan(&vo,point.wall,point,N,osd.secondary_rate);
  CALLER_CHECK(fresh.valid && fresh.base.slot==G && fresh.target.slot==G+1);
  CALLER_CHECK(secondary_set_presentation(&vo,plan.target,0,T,plan.submit,false,true,&plan));
  double pts=0;CALLER_CHECK(integration_actual_sample_selection(&osd,&pts));
  struct secondary_ass_sample_snapshot snapshot=osd_get_secondary_sample_snapshot(&osd);
  CALLER_CHECK(snapshot.valid && snapshot.display_forecast && snapshot.sample_slot==G);
  CALLER_CHECK(snapshot.origin_slot==110 && snapshot.next_slot==G+N);
  CALLER_CHECK(osd.secondary_sampler.display_slot==G+1 && osd.secondary_sampler.tick==(int64_t)k);
  actual_registration(&vo,&plan,k+1,G+1);
  CALLER_CHECK(p->last_base_slot==G && p->submitted[(p->next+31)%32].target_slot==G+1);
 }
 // Exact current caller selection uses only a disposable H copy. The
 // next task remains on the old sampler lattice when retrospective H moves.
 struct secondary_ass_sample_snapshot snapshot=osd_get_secondary_sample_snapshot(&osd);
 p->delay=0;struct secondary_ass_physical before=*p;
 fixture_now=secondary_ass_physical_point_at(p,snapshot.next_slot).wall-T/2;
 struct secondary_ass_physical_point next=secondary_forecast_next(&vo,snapshot.next_slot,N,fixture_now,osd.secondary_rate);
 struct secondary_ass_physical view=*p;view.delay=1;
 struct secondary_ass_physical_point expected=secondary_ass_present_plan_cache_next_forecast(&view,snapshot.next_slot,N,fixture_now);
 CALLER_CHECK(next.slot==expected.slot && next.wall==expected.wall && !memcmp(&before,p,sizeof(before)));
 p->delay=3;
 struct secondary_ass_physical_point changed=secondary_forecast_next(&vo,snapshot.next_slot,N,fixture_now,osd.secondary_rate);
 CALLER_CHECK(changed.slot==next.slot && changed.wall==next.wall && p->delay==3);
 // At the immutable delta's exact expiry, a larger retrospective H must
 // not keep the old G alive. Exercise the real caller, not just the helper.
 fixture_now=secondary_ass_physical_point_at(p,snapshot.next_slot+1).wall;
 changed=secondary_forecast_next(&vo,snapshot.next_slot,N,fixture_now,osd.secondary_rate);
 CALLER_CHECK(changed.slot==snapshot.next_slot+N &&
  changed.wall==secondary_ass_physical_point_at(p,snapshot.next_slot+N).wall);
 CALLER_CHECK(p->delay==3 && in.secondary_fixed_offset.valid && in.secondary_fixed_offset.offset==1);
 // Same-epoch UNKNOWN temporarily refuses plans without resetting offset.
 p->outlier_pending=true;
 CALLER_CHECK(!secondary_forecast_plan(&vo,next,N,osd.secondary_rate).valid);
 CALLER_CHECK(in.secondary_fixed_offset.valid && in.secondary_fixed_offset.offset==1);
 p->outlier_pending=false;
 CALLER_CHECK(secondary_forecast_plan(&vo,next,N,osd.secondary_rate).valid);
 // Existing reset wrapper owns the new state lifecycle and actual OSD getter
 // continues to report the sampler's logical G, rather than the display D.
 secondary_reset_physical(&vo,"fixed-caller-test");
 CALLER_CHECK(!in.secondary_fixed_offset.valid);
}

int main(void) {
 struct vo_internal flags={0};
 for(unsigned bits=0;bits<16;bits++) {
  bool diagnostic=bits&1;flags.secondary_present_plan=bits&2;
  flags.secondary_present_grid=bits&4;fixture_forecast_env=bits&8;
  integration_actual_forecast_flag(&flags,diagnostic);
  CALLER_CHECK(flags.secondary_display_forecast==(bits==15));
 }
 const int rates[]={30,60,120,144,165,240,360};
 for(unsigned k=0;k<sizeof(rates)/sizeof(rates[0]);k++)
  for(int64_t N=1;N<=4;N++)caller_rate(rates[k],N);
 unsigned legacy_checks=caller_checks;
 // Original 7520 checks remain; the added real quiet clock-rate getter
 // executes 448 lock/unlock pairs, adding exactly 896 checks.
 CALLER_CHECK(legacy_checks==8416);
 for(unsigned bits=0;bits<128;bits++) {
  flags=(struct vo_internal){0};bool diagnostic=bits&1;
  flags.secondary_present_plan=bits&2;flags.secondary_present_grid=bits&4;
  fixture_forecast_env=bits&8;fixture_fixed_env=bits&16;
  flags.secondary_queue_stage=bits&32;flags.secondary_queue_lead=bits&64;
  integration_actual_fixed_flag(&flags,diagnostic);
  CALLER_CHECK(flags.secondary_display_forecast==((bits&15)==15));
  CALLER_CHECK(flags.secondary_fixed_forecast==((bits&31)==31 && !(bits&96)));
  struct vo config_vo={.in=&flags};
  flags.secondary_trace=true;flags.secondary_schedule_trace=true;
  flags.secondary_fifo_present=true;flags.secondary_split_budget=true;config_vo.pacing_spans=true;
  struct mp_ass_pacing_record config=integration_actual_config(&config_vo,diagnostic);
  const int64_t expected[]={1,diagnostic,1,1,flags.secondary_present_grid,flags.secondary_present_plan,1,1,
   flags.secondary_queue_lead,flags.secondary_queue_stage,flags.secondary_display_forecast,flags.secondary_fixed_forecast,0,0,0,0};
  for(unsigned n=0;n<16;n++)CALLER_CHECK(config.v[n]==expected[n]);
 }
 fixture_fixed_env=false;
 for(unsigned k=0;k<sizeof(rates)/sizeof(rates[0]);k++)
  for(int64_t N=1;N<=4;N++)fixed_caller_rate(rates[k],N);
 if(caller_checks!=15705)return 2;
 printf("{\"original_legacy_checks\":7520,\"new_clock_getter_checks\":896,\"actual_caller_checks\":%u,\"legacy_caller_checks\":%u,\"fixed_caller_checks\":%u,\"passed\":true,\"GPU\":false}\n",
  caller_checks,legacy_checks,caller_checks-legacy_checks);
 return 0;
}
#endif
'''


def forecast_runtime_gate(generated, source, cc):
    quiet = re.search(r"struct secondary_ass_physical_point logical = divisor > 0\s*"
                      r"\? secondary_forecast_next\([^;]+;", generated)
    sample_slot = re.search(r"\.sample_slot = secondary_ass_sampler_next_slot\(s\)[^;{}]*?: 0,", generated)
    if not quiet or not sample_slot:
        raise ValueError("actual quiet-grid/snapshot sample-slot closure changed")
    mutations = (
        ("collision_setter_accepts", "valid = display_slot > s->display_slot && display_wall > s->sample_wall;", "valid = true;"),
        ("force_latch_lost", "osd->secondary_forecast_forced_sample |= osd->secondary_sampler.force;", "osd->secondary_forecast_forced_sample |= false;"),
        ("rawF_guard_removed", "present_plan.base.wall < original_video_target", "false"),
        ("registration_uses_D", "submitted_id, plan->epoch, plan->base, plan->target);", "submitted_id, plan->epoch, plan->target, plan->target);"),
        ("quiet_bare_prediction_off_grid", quiet[0],
         "struct secondary_ass_physical view=secondary_ass_present_plan_view(p);\n"
         "struct secondary_ass_physical_point logical=secondary_ass_physical_predict_point(&view, MPMAX(submit,mp_time_ns()));"),
        ("snapshot_sample_slot_becomes_D", sample_slot[0], ".sample_slot = s->display_slot,"),
        ("forecast_without_diagnostic_permission", "in->secondary_display_forecast = diagnostic && in->secondary_present_plan", "in->secondary_display_forecast = in->secondary_present_plan"),
    )
    actual_functions = functions(generated)
    fixed_specs = (
        ('fixed_stage_lead_permission_ignored', 'integration_actual_fixed_flag',
         '!in->secondary_queue_stage && !in->secondary_queue_lead &&', 'true &&'),
        ('fixed_flag_ignored', 'integration_actual_fixed_flag',
         'fixed_forecast && !strcmp(fixed_forecast, "1")', '((void)fixed_forecast, true)'),
        ('CONFIG_fixed_field_lost', 'integration_actual_config',
         'in->secondary_fixed_forecast}', 'false}'),
        ('fixed_plan_follows_changing_H', 'secondary_forecast_plan',
         'secondary_fixed_forecast_offset(vo, logical, divisor, rate)',
         '((void)divisor, (void)rate, vo->in->secondary_physical.delay)'),
        ('fixed_selection_follows_changing_H', 'secondary_forecast_next',
         'return secondary_ass_present_plan_cache_next_fixed_forecast(p, first_slot,\n                                                               divisor, now, offset);',
         '(void)offset;return secondary_ass_present_plan_cache_next_forecast(p, first_slot, divisor, now);'),
        ('fixed_submission_returns_to_G', 'secondary_forecast_plan',
         'return secondary_ass_present_plan_make_fixed_forecast(\n'
         '            &vo->in->secondary_physical, logical,\n'
         '            secondary_fixed_forecast_offset(vo, logical, divisor, rate));',
         'struct secondary_ass_present_plan plan=secondary_ass_present_plan_make_fixed_forecast(\n'
         '            &vo->in->secondary_physical, logical,\n'
         '            secondary_fixed_forecast_offset(vo, logical, divisor, rate));\n'
         '        plan.submit=secondary_ass_present_plan_make_forecast(&vo->in->secondary_physical,logical).submit;\n'
         '        return plan;'),
        ('fixed_offset_survives_actual_reset', 'secondary_reset_physical',
         'in->secondary_fixed_offset = (struct secondary_ass_present_fixed_offset){0};',
         '(void)in->secondary_fixed_offset;'),
    )
    fixed_mutations = []
    for name, function, before, after in fixed_specs:
        actual = actual_functions[function]['text']
        if actual.count(before) != 1 or generated.count(actual) != 1:
            raise ValueError('V24 actual runtime fault missing/ambiguous: ' + name)
        fixed_mutations.append((name, actual, actual.replace(before, after, 1)))
    results = {}
    fixed_results = {}
    with tempfile.TemporaryDirectory(prefix="mpv-v23-forecast-callers-") as directory:
        work = Path(directory)
        cases = (("positive", "", ""), ("positive_NDEBUG", "", "")) + mutations + tuple(fixed_mutations)
        for name, needle, replacement in cases:
            text = generated
            if needle:
                if text.count(needle) != 1:
                    raise ValueError("actual C mutant operand missing/ambiguous: " + name)
                text = text.replace(needle, replacement)
            cfile = work / (name + ".c")
            cfile.write_text(text + FORECAST_RUNTIME_C, encoding="utf-8")
            exe = work / (name + ".exe")
            command = [str(cc), "-std=c99", "-Werror", "-O1", "-ffunction-sections", "-fdata-sections",
                       "-DMP_V23_FORECAST_CALLER_TEST=1", "-I", str(source), str(cfile),
                       "-Wl,--gc-sections", "-lm", "-o", str(exe)]
            if name == 'positive_NDEBUG':
                command.insert(1, '-DNDEBUG')
            compiled = subprocess.run(command, capture_output=True, text=True, timeout=60)
            item = {"compile_returncode": compiled.returncode,
                    "compile_command": command,
                    "diagnostics": (compiled.stdout + compiled.stderr)[-12000:],
                    "translation_sha256": hashlib.sha256((text + FORECAST_RUNTIME_C).encode()).hexdigest()}
            if compiled.returncode == 0:
                executed = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30)
                item.update(execute_returncode=executed.returncode, stdout=executed.stdout,
                            stderr=executed.stderr[-4000:])
                if name in ("positive", "positive_NDEBUG") and executed.returncode == 0:
                    try:
                        item["result"] = json.loads(executed.stdout)
                    except ValueError:
                        item["result"] = None
            item["pass"] = compiled.returncode == 0 and (
                item.get("execute_returncode") == 0 and isinstance(item.get("result"), dict) and
                item["result"].get("passed") is True and item["result"].get("GPU") is False and
                type(item["result"].get("actual_caller_checks")) is int and
                item["result"]["actual_caller_checks"] == 15705 and
                item["result"].get("legacy_caller_checks") == 8416 and
                item["result"].get("original_legacy_checks") == 7520 and
                item["result"].get("new_clock_getter_checks") == 896 and
                item["result"].get("fixed_caller_checks") == 7289
                if name in ("positive", "positive_NDEBUG") else
                item.get("execute_returncode") not in (None, 0))
            if name in {row[0] for row in fixed_mutations}:
                fixed_results[name] = item
            elif name == 'positive_NDEBUG':
                ndebug_result = item
            else:
                results[name] = item
    return {"pass": all(v["pass"] for v in results.values()) and
                    all(v['pass'] for v in fixed_results.values()) and ndebug_result['pass'],
            "cases": results, "v24_cases": fixed_results, "positive_NDEBUG": ndebug_result,
            "scope": "ACTUAL_COMPLETE_OSD_STATE_SETTERS_GETTER_SAMPLE_SELECTION_AND_SELECTED_VO_CALLERS_WITH_MOCK_PLATFORM_ENDPOINTS",
            "not_verified": ["real OS wait/threading, libass output discovery, actual full VO loop, GPU, Display/frame pacing"]}


def compile_gate(source, cc, read, include_osd_getter=True, output_translation=None):
    vo_header = read("video/out/vo.h")
    vo_source = read("video/out/vo.c")
    thread_header = read("osdep/threads-win32.h")
    actual_functions = functions(vo_source)
    chunks = ["#include <stdint.h>\n#include <stdbool.h>\n#include <inttypes.h>\n#include <stddef.h>\n#include <limits.h>\n"]
    # Opaque PLATFORM types only: internal typedef declarations below are real.
    chunks.append("typedef void *HANDLE; typedef unsigned long DWORD;\n"
                  "typedef void *CONDITION_VARIABLE; typedef void *INIT_ONCE; typedef void *SRWLOCK;\n")
    thread_aliases = re.findall(r"^typedef[^;]+\bmp_(?:cond|once|mutex|static_mutex|thread|thread_id)\s*;", thread_header, re.M)
    if len(thread_aliases) != 6:
        raise ValueError("real Windows thread typedef closure changed")
    chunks.append("\n".join(thread_aliases))
    # Preserve actual inline mpv lock/broadcast declarations and bodies. Only
    # the Windows OS call endpoints remain opaque platform boundaries.
    chunks.append("void AcquireSRWLockExclusive(SRWLOCK *);\n"
                  "void ReleaseSRWLockExclusive(SRWLOCK *);\n"
                  "void WakeAllConditionVariable(CONDITION_VARIABLE *);\n"
                  "int SetEvent(HANDLE);\n")
    thread_functions = functions(thread_header)
    platform_full = []
    for name in ("mp_mutex_lock", "mp_mutex_unlock", "mp_cond_broadcast"):
        if name not in thread_functions:
            raise ValueError(f"actual Windows thread function missing: {name}")
        function = thread_functions[name]
        chunks.append(f'#line {function["line"]} "osdep/threads-win32.h"\n{function["text"]}\n')
        platform_full.append({"file": "osdep/threads-win32.h", "function": name,
                              "line": function["line"], "sha256": hashlib.sha256(function["text"].encode()).hexdigest()})
    for header in HEADERS:
        read(header)
        chunks.append(f'#include "{header}"\n')
    # The injected compilation closure cannot hide a missing real include.
    if len(re.findall(r'^\s*#include\s+"secondary_ass_queue_lead.h"\s*$', vo_source, re.M)) != 1:
        raise ValueError("actual vo.c queue-lead include missing/duplicated")
    common = read("common/common.h")
    for macro in ("MPMIN", "MPMAX", "MP_NOPTS_VALUE"):
        found = re.findall(r"^#define\s+" + macro + r"(?:\([^\n]+|\s+[^\n]+)", common, re.M)
        if len(found) != 1:
            raise ValueError(f"real macro closure changed: {macro}")
        chunks += found
    assertion = read("misc/mp_assert.h")
    chunks.append('#include "misc/mp_assert.h"\n')
    masked_vo_header = mask_c(vo_header)
    for token in ("VO_EVENT_LIVE_RESIZING", "VO_CAP_NORETAIN"):
        candidates = []
        for match in re.finditer(r"\benum\s*\{", masked_vo_header):
            end = balanced(masked_vo_header, masked_vo_header.index("{", match.start()))
            if re.search(r"\b" + token + r"\b", masked_vo_header[match.start():end]):
                candidates.append(vo_header[match.start():end] + ";")
        if len(candidates) != 1:
            raise ValueError(f"real enum closure changed: {token}")
        chunks += candidates
    constants = re.findall(r"^#define\s+VO_MAX_REQ_FRAMES\s+[^\n]+", vo_header, re.M)
    if len(constants) != 1:
        raise ValueError("real VO_MAX_REQ_FRAMES declaration missing")
    chunks += constants
    # Preserve real tag forwards before callback parameter declarations. TCC
    # tolerates missing forwards that GCC diagnoses as parameter-scope tags.
    chunks += re.findall(r"^struct\s+\w+\s*;", vo_header, re.M)
    declarations = []
    for name in STRUCTS:
        decl, line = declaration(vo_header, name)
        declarations.append({"file": "video/out/vo.h", "struct": name, "line": line,
                             "sha256": hashlib.sha256(decl.encode()).hexdigest()})
        chunks.append(f'#line {line} "video/out/vo.h"\n{decl}\n')
    decl, line = declaration(vo_source, "vo_internal")
    declarations.append({"file": "video/out/vo.c", "struct": "vo_internal", "line": line,
                         "sha256": hashlib.sha256(decl.encode()).hexdigest()})
    chunks.append(f'#line {line} "video/out/vo.c"\n#define _WIN32 1\n{decl}\n')
    decl, line = declaration(vo_source, "secondary_ass_grid_task")
    declarations.append({"file": "video/out/vo.c", "struct": "secondary_ass_grid_task", "line": line,
                         "sha256": hashlib.sha256(decl.encode()).hexdigest()})
    chunks.append(f'#line {line} "video/out/vo.c"\n{decl}\n')
    timer = read("osdep/timer.h")
    timer_decl = re.search(r"\bint64_t\s+mp_time_ns\s*\(\s*void\s*\)\s*;", timer)
    osd = read("sub/osd.h")
    scope_decl = re.search(r"\bvoid\s+osd_set_ass_pacing_scope\s*\([^;]+;", osd)
    if not timer_decl or not scope_decl:
        raise ValueError("real timer/OSD prototype closure changed")
    chunks.append(timer_decl[0] + "\n" + scope_decl[0] + "\n")
    unit_macros = re.findall(r"^#define\s+MP_TIME_S_TO_NS\([^\n]+", timer, re.M)
    if len(unit_macros) != 1:
        raise ValueError("real timer conversion macro closure changed")
    chunks += unit_macros
    milliseconds = re.findall(r"^#define\s+MP_TIME_MS_TO_NS\([^\n]+", timer, re.M)
    if len(milliseconds) != 1:
        raise ValueError("actual millisecond macro closure changed")
    chunks += milliseconds
    # Keep the real mpv declarations and alias used by the new span helpers.
    # GetCurrentThreadId is an explicit opaque platform-call boundary here;
    # its Windows SDK calling convention/ABI still requires the full build.
    prototypes = []
    for path, text, name, returns in (
        ("osdep/threads-win32.h", thread_header, "mp_thread_cpu_time_ns", "int64_t"),
        ("video/out/vo.h", vo_header, "vo_pacing_span_at", "void"),
        ("video/out/vo.h", vo_header, "vo_pacing_span_now", "void"),
        ("sub/osd.h", osd, "osd_get_secondary_refresh", "double"),
        ("sub/osd.h", osd, "osd_get_secondary_sample_snapshot", "struct secondary_ass_sample_snapshot"),
    ):
        matches = list(re.finditer(r"\b" + returns + r"\s+" + name +
                                  r"\s*\([^;{}]*\)\s*;", mask_c(text)))
        if len(matches) != 1:
            raise ValueError(f"real prototype closure changed: {path}:{name}")
        match = matches[0]
        proto = text[match.start():match.end()]
        chunks.append(proto)
        prototypes.append({"file": path, "function": name,
                           "line": text.count("\n", 0, match.start()) + 1,
                           "sha256": hashlib.sha256(proto.encode()).hexdigest()})
    aliases = list(re.finditer(r"^#define\s+mp_thread_current_id\s+GetCurrentThreadId\s*$",
                              mask_c(thread_header), re.M))
    if len(aliases) != 1:
        raise ValueError("real Windows mp_thread_current_id alias closure changed")
    alias = aliases[0]
    chunks.append("DWORD GetCurrentThreadId(void);\n" + thread_header[alias.start():alias.end()] + "\n")
    chunks.append("void integration_log(const char *, ...);\n#define MP_INFO(obj, ...) integration_log(__VA_ARGS__)\n")
    full = list(platform_full)
    selected = set(FUNCTIONS) | {
        "secondary_forecast_enabled", "secondary_cache_plan", "secondary_capture_grid_plan",
        "secondary_next_sample", "secondary_cache_next_sample",
        "secondary_fixed_forecast_offset", "secondary_forecast_plan",
        "secondary_forecast_fresh_plan", "secondary_forecast_next",
        "secondary_set_presentation", "secondary_physical_feedback",
    }
    selected.update(name for name in actual_functions if re.match(r"^secondary_.*stage", name))
    # Preserve real OSD prototypes instead of manufacturing signatures from
    # call operands. Forward selected VO functions retain their actual types.
    osd_prototypes = ("osd_get_secondary_clock_rate", "osd_get_secondary_physical_next_sample_slot",
        "osd_get_secondary_physical_next_sample_time", "osd_get_secondary_physical_sample_divisor",
        "osd_set_secondary_physical_forecast_time", "osd_set_secondary_physical_presentation_time",
        "osd_set_secondary_presentation_time", "osd_hold_secondary_sample", "osd_reset_secondary_clock")
    for name in osd_prototypes:
        matches = list(re.finditer(r"^[A-Za-z_][^;{}]*\b" + re.escape(name) +
                                  r"\s*\([^;{}]*\)\s*;", mask_c(osd), re.M))
        if len(matches) != 1:
            raise ValueError("actual OSD prototype missing/duplicated: " + name)
        m = matches[0]
        proto = osd[m.start():m.end()]
        chunks.append(proto)
        prototypes.append({"file": "sub/osd.h", "function": name,
                           "sha256": hashlib.sha256(proto.encode()).hexdigest()})
    for name in selected:
        if name not in actual_functions:
            raise ValueError("actual V23 function missing: " + name)
        chunks.append(actual_functions[name]["signature"] + ";")
    for name in sorted(selected, key=lambda n: actual_functions[n]["line"]):
        if name not in actual_functions:
            raise ValueError(f"required actual VO function absent: {name}")
        function = actual_functions[name]
        chunks.append(f'#line {function["line"]} "video/out/vo.c"\n{function["text"]}\n')
        full.append({"file": "video/out/vo.c", "function": name, "line": function["line"],
                     "sha256": hashlib.sha256(function["text"].encode()).hexdigest()})
    # Compile the actual render-frame current-token condition without pulling
    # unrelated image/GPU APIs or synthesizing an mpv struct from its fields.
    render = actual_functions.get("render_frame")
    if not render:
        raise ValueError("actual render_frame definition missing")
    condition = re.search(r"\bbool\s+current\s*=\s*[^;]*\bsecondary_ass_queue_lead_current\s*\([^;]+;", render["masked"])
    sample = re.search(r"\bstruct\s+secondary_ass_sample_snapshot\s+queue_sample\s*=[^;]+;", render["masked"])
    token = re.search(r"\bstruct\s+secondary_ass_queue_token\s*\*\s*token\s*=[^;]+;", render["masked"])
    internal = re.search(r"\bstruct\s+vo_internal\s*\*\s*in\s*=[^;]+;", render["masked"])
    if not all((condition, sample, token, internal)):
        raise ValueError("real render_frame queue-current call/context closure changed")
    fragments = []
    chunks.append("\nstatic void integration_render_queue_current_call(struct vo *vo) {\n")
    for match in (internal, sample, token, condition):
        text = render["text"][match.start():match.end()]
        line = render["line"] + render["masked"].count("\n", 0, match.start())
        chunks.append(f'#line {line} "video/out/vo.c"\n{text}\n')
        fragments.append({"file": "video/out/vo.c", "function": "render_frame", "line": line,
                          "sha256": hashlib.sha256(text.encode()).hexdigest()})
    chunks.append("(void)current;\n}\n")
    thread = actual_functions.get("vo_thread")
    if not thread or len(re.findall(r"\bsecondary_publish_queue_hint\s*\(\s*vo\s*\)", thread["masked"])) != 1:
        raise ValueError("actual vo_thread queue-hint publisher invocation missing/duplicated")
    osd_source = read("sub/osd.c")
    osd_functions = functions(osd_source)
    getter = osd_functions.get("osd_get_secondary_sample_snapshot")
    if not getter:
        raise ValueError("actual OSD snapshot getter definition missing")
    if include_osd_getter:
        if len(re.findall(r'^\s*#include\s+"osd_state.h"\s*$', osd_source, re.M)) != 1:
            raise ValueError("actual osd.c osd_state include missing/duplicated")
        maximum_parts = re.findall(r"^#define\s+MAX_OSD_PARTS\s+[^\n]+", osd, re.M)
        if len(maximum_parts) != 1:
            raise ValueError("real MAX_OSD_PARTS closure changed")
        chunks += maximum_parts
        state, line = declaration(read("sub/osd_state.h"), "osd_state")
        declarations.append({"file": "sub/osd_state.h", "struct": "osd_state", "line": line,
                             "sha256": hashlib.sha256(state.encode()).hexdigest()})
        chunks.append(f'#line {line} "sub/osd_state.h"\n{state}\n')
        chunks.append(f'#line {getter["line"]} "sub/osd.c"\n{getter["text"]}\n')
        full.append({"file": "sub/osd.c", "function": "osd_get_secondary_sample_snapshot",
                     "line": getter["line"], "sha256": hashlib.sha256(getter["text"].encode()).hexdigest()})
        for name in ("osd_get_secondary_refresh", "osd_get_secondary_clock_rate",
                     "osd_get_secondary_physical_next_sample_slot",
                     "osd_get_secondary_physical_next_sample_time",
                     "osd_get_secondary_physical_sample_divisor",
                     "osd_set_secondary_presentation_time",
                     "osd_set_secondary_physical_presentation_time",
                     "osd_set_secondary_physical_forecast_time", "osd_hold_secondary_sample",
                     "osd_anchor_secondary_clock", "osd_reset_secondary_clock"):
            function = osd_functions.get(name)
            if not function:
                raise ValueError("actual V23 OSD function missing: " + name)
            chunks.append(f'#line {function["line"]} "sub/osd.c"\n{function["text"]}\n')
            full.append({"file": "sub/osd.c", "function": name,
                         "line": function["line"], "sha256": hashlib.sha256(function["text"].encode()).hexdigest()})
        render_object = osd_functions["render_object"]
        start = render_object["text"].index("        if (osd->secondary_sample_held)")
        end = render_object["text"].index("        struct mp_ass_pacing_record scope", start)
        piece = render_object["text"][start:end]
        chunks.append("\nstatic bool integration_actual_sample_selection(struct osd_state *osd, double *pts) {\n"
                      "double video_pts=*pts; bool changed_sample=false;\n" + piece +
                      "\n*pts=video_pts;return changed_sample;\n}\n")
        fragments.append({"file": "sub/osd.c", "function": "render_object",
                          "context": "complete_secondary_sample_selection_before_bitmap_boundary",
                          "sha256": hashlib.sha256(piece.encode()).hexdigest()})
    fresh_guard = re.search(r"\bif\s*\(present_plan\.display_forecast[^{};]+\)\s*\{", render["masked"])
    if not fresh_guard:
        raise ValueError("actual fresh G>=rawF guard absent")
    guard_end = balanced(render["masked"], render["masked"].index("{", fresh_guard.start()))
    piece = render["text"][fresh_guard.start():guard_end]
    chunks.append("\nstatic bool integration_actual_fresh_raw_guard(struct vo *vo, "
                  "struct secondary_ass_present_plan present_plan, int64_t original_video_target) {\n" +
                  piece + "\nreturn present_plan.valid;\n}\n")
    fragments.append({"file": "video/out/vo.c", "function": "render_frame",
                      "context": "fresh_G_at_or_after_original_video_target",
                      "sha256": hashlib.sha256(piece.encode()).hexdigest()})
    flag_start = thread["text"].index('    const char *display_forecast = getenv(')
    flag_match = re.search(r"\bin->secondary_display_forecast\s*=[^;]+;", thread["masked"][flag_start:])
    if not flag_match:
        raise ValueError("actual forecast flag authorization absent")
    piece = thread["text"][flag_start:flag_start + flag_match.end()]
    chunks.append("\nchar *integration_getenv(const char *);\n#define getenv integration_getenv\n"
                  "static void integration_actual_forecast_flag(struct vo_internal *in, bool diagnostic) {\n" +
                  piece + "\n}\n#undef getenv\n")
    fragments.append({"file": "video/out/vo.c", "function": "vo_thread",
                      "context": "actual_default_off_forecast_env_authorization",
                      "sha256": hashlib.sha256(piece.encode()).hexdigest()})
    fixed_match = re.search(r"\bin->secondary_fixed_forecast\s*=[^;]+;", thread["masked"][flag_start:])
    if not fixed_match:
        raise ValueError("actual default-off fixed forecast authorization absent")
    fixed_start = thread["text"].index('    const char *fixed_forecast = getenv(', flag_start)
    fixed_piece = thread["text"][fixed_start:flag_start + fixed_match.end()]
    chunks.append("\n#define getenv integration_getenv\n"
                  "static void integration_actual_fixed_flag(struct vo_internal *in, bool diagnostic) {\n" +
                  "integration_actual_forecast_flag(in,diagnostic);\n" + fixed_piece + "\n}\n#undef getenv\n")
    fragments.append({"file": "video/out/vo.c", "function": "vo_thread",
                      "context": "actual_default_off_fixed_forecast_env_authorization",
                      "sha256": hashlib.sha256(fixed_piece.encode()).hexdigest()})
    config_start = thread["text"].index("struct mp_ass_pacing_record record =", flag_start)
    config_open = thread["masked"].index("{", config_start)
    config_end = balanced(thread["masked"], config_open)
    config_piece = thread["text"][config_start:config_end + 1]
    if "in->secondary_fixed_forecast" not in config_piece or "MP_ASS_PACING_CONFIG" not in thread["text"][config_end:config_end + 120]:
        raise ValueError("actual twelve-field CONFIG writer closure changed")
    chunks.append("\nstatic struct mp_ass_pacing_record integration_actual_config(struct vo *vo, bool diagnostic) {\n"
                  "struct vo_internal *in=vo->in;\n" + config_piece + "\nreturn record;\n}\n")
    fragments.append({"file": "video/out/vo.c", "function": "vo_thread",
                      "context": "actual_CONFIG_twelve_fields_plus_four_reserved_zeros",
                      "sha256": hashlib.sha256(config_piece.encode()).hexdigest()})
    gpu_functions = functions(read("video/out/vo_gpu_next.c"))
    closure_errors = []
    stage = gpu_functions.get("pacing_gpu_stage")
    if not stage:
        closure_errors.append("actual vo_gpu_next pacing_gpu_stage definition missing")
    else:
        chunks.append(f'#line {stage["line"]} "video/out/vo_gpu_next.c"\n{stage["text"]}\n')
        full.append({"file": "video/out/vo_gpu_next.c", "function": "pacing_gpu_stage",
                     "line": stage["line"], "sha256": hashlib.sha256(stage["text"].encode()).hexdigest()})
    operands = []
    chunks.append("\nvoid integration_member_consumers(struct vo *vo, struct vo_frame *frame, struct vo_vsync_info *info, struct vo_driver *driver) {\n")
    for path in CONSUMERS:
        extracted = consumer_expressions(path, read(path))
        if not extracted:
            raise ValueError(f"no actual member consumer operands found: {path}")
        for expression, name, line in extracted:
            chunks.append(f'#line {line} "{path}"\n(void)({expression});\n')
            operands.append({"file": path, "function": name, "line": line, "expression": expression})
    chunks.append("}\n")
    # Compile the verbatim callback and initializer under the explicit
    # non-D3D11 boundary. The real D3D11 branch still needs the full SDK build;
    # unlike a static prototype-only fixture this has no undefined definition.
    early = gpu_functions.get("can_present_early")
    if not early:
        closure_errors.append("actual gpu-next can_present_early definition missing")
    elif not re.search(r"\.can_present_early\s*=\s*can_present_early\b", mask_c(read("video/out/vo_gpu_next.c"))):
        closure_errors.append("actual gpu-next driver callback initializer missing")
    else:
        chunks.append(f'#line {early["line"]} "video/out/vo_gpu_next.c"\n#define HAVE_D3D11 0\n{early["text"]}\n')
        chunks.append("struct vo_driver integration_callback = {.can_present_early = can_present_early};\n")
        full.append({"file": "video/out/vo_gpu_next.c", "function": "can_present_early",
                     "line": early["line"], "sha256": hashlib.sha256(early["text"].encode()).hexdigest(),
                     "preprocessor_scope": "HAVE_D3D11=0; callback type contract, no SDK backend branch"})
    generated = "\n".join(chunks)
    if output_translation:
        output_translation.parent.mkdir(parents=True, exist_ok=True)
        output_translation.write_text(generated, encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="mpv-native-ass-integration-") as directory:
        work = Path(directory)
        translation = work / "real-declarations-consumers.c"
        translation.write_text(generated, encoding="utf-8")
        command = [str(cc), "-std=c99", "-Werror", "-I", str(source), "-c", str(translation), "-o", str(work / "gate.o")]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=60)
        result = {"pass": completed.returncode == 0 and not closure_errors,
                  "compile_command": command,
                  "returncode": completed.returncode, "closure_errors": closure_errors,
                  "compiler": str(cc), "diagnostics": (completed.stdout + completed.stderr)[-18000:],
                  "real_complete_structs": declarations,
                  "real_prototypes": prototypes,
                  "verbatim_full_functions": full, "actual_member_operand_count": len(operands),
                  "actual_member_operands": operands,
                  "translation_sha256": hashlib.sha256(generated.encode()).hexdigest(),
                  "queue_osd_getter_requested": include_osd_getter,
                  "queue_osd_getter_compiled": include_osd_getter and completed.returncode == 0,
                  "verbatim_queue_render_condition_fragments": fragments,
                  "queue_gate_scope": "REAL_OSD_STATE_GETTER_AND_COMPLETE_VO_QUEUE_FUNCTIONS" if include_osd_getter else
                                      "VO_QUEUE_ONLY_NOT_OSD_GETTER_COMPILATION; TCC DOES NOT SUPPORT REAL _Atomic",
                  "scope": "REAL_COMPLETE_DECLARATIONS_SELECTED_VERBATIM_FUNCTIONS_AND_GPU_MEMBER_OPERANDS_NOT_FULL_TRANSLATION_UNITS",
                  "boundary_stubs": ["opaque Windows OS HANDLE/DWORD/condition/once/lock types; no platform ABI assertion",
                                     "Windows Acquire/Release SRWLock, condition broadcast and SetEvent endpoints; actual mpv wrappers verbatim, no SDK ABI assertion",
                                     "GetCurrentThreadId prototype boundary; no Windows calling convention/SDK ABI assertion",
                                     "logging function/macro boundary; all format argument expressions remain compiled",
                                     "can_present_early compiled with HAVE_D3D11=0; real D3D11 branch is not compiled"],
                  "not_covered": ["full vo.c/d3d11/context.c/vo_gpu_next.c translation units and their external SDK APIs",
                                  "OSD getter actual body/complete osd_state when --queue-vo-only; this limited mode cannot substitute for default GCC gate",
                                  "Meson dependency discovery, linker, optimization, ABI, threading, runtime, GPU, Display/frame pacing"]}
    if include_osd_getter and result["pass"]:
        result["cpu_forecast_caller_execution"] = forecast_runtime_gate(generated, source, cc)
        result["pass"] &= result["cpu_forecast_caller_execution"]["pass"]
    elif not include_osd_getter:
        result["cpu_forecast_caller_execution"] = {"pass": None, "status": "UNVERIFIED_TCC_VO_ONLY_CANNOT_REPLACE_FULL_GCC_GATE"}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--variant", required=True, choices=("main", "atmos"))
    parser.add_argument("--cc", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--queue-vo-only", action="store_true",
                        help="Limited local TCC diagnostic only; leaves actual OSD getter compilation unverified")
    parser.add_argument("--translation-output", type=Path,
                        help="Save verbatim declaration/function/fragment compilation evidence")
    parser.add_argument("--quiet", action="store_true", help="Print compact status; full evidence remains in --output")
    args = parser.parse_args()
    source = args.source.resolve()
    hashes = {}
    cached = {}

    def read(path):
        if path in cached:
            return cached[path]
        data = (source / path).read_bytes()
        hashes[path] = hashlib.sha256(data).hexdigest()
        cached[path] = data.decode("utf-8")
        return cached[path]

    result = {"source": str(source), "variant": args.variant,
              "runtime_verified": False, "gpu_started": False, "full_build_verified": False}
    try:
        result["meson"] = meson_check(source, args.variant, read)
        # Collect C evidence even if Meson fails; do not hide a second blocker.
        result["compile"] = compile_gate(source, args.cc.resolve(), read, not args.queue_vo_only,
                                         args.translation_output)
        success = result["meson"]["pass"] and result["compile"]["pass"]
        changed = [path for path,digest in hashes.items()
                   if hashlib.sha256((source/path).read_bytes()).hexdigest() != digest]
        result["inputs_changed_during_gate"] = changed
        success = success and not changed
        result["status"] = ("VO_QUEUE_ONLY_COMPILE_PASS_OSD_GETTER_UNVERIFIED_NOT_FULL_BUILD_OR_RUNTIME" if args.queue_vo_only else
                            "LIMITED_REAL_DECLARATION_CONSUMER_COMPILE_PASS_NOT_FULL_BUILD_OR_RUNTIME") if success else "INTEGRATION_GATE_FAIL"
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        success = False
        result["status"] = "INTEGRATION_GATE_FAIL"
        result["error"] = str(error)
    result["source_sha256"] = hashes
    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "compile_pass": result.get("compile", {}).get("pass"),
                      "error": result.get("error")}, ensure_ascii=False) if args.quiet else output)
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
