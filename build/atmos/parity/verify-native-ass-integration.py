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
    "secondary_record_tag", "secondary_record_begin", "secondary_record_end",
    "secondary_reset_physical", "reset_secondary_ass_budget",
    "secondary_plan_enabled", "secondary_cache_block_cost",
    "secondary_observe_flip_budget", "secondary_planning_state",
    "secondary_trace_plan", "secondary_trace_plan_missed",
    "secondary_plan_stale_reason",
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


def compile_gate(source, cc, read):
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
    for header in HEADERS:
        read(header)
        chunks.append(f'#include "{header}"\n')
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
    timer = read("osdep/timer.h")
    timer_decl = re.search(r"\bint64_t\s+mp_time_ns\s*\(\s*void\s*\)\s*;", timer)
    osd = read("sub/osd.h")
    scope_decl = re.search(r"\bvoid\s+osd_set_ass_pacing_scope\s*\([^;]+;", osd)
    if not timer_decl or not scope_decl:
        raise ValueError("real timer/OSD prototype closure changed")
    chunks.append(timer_decl[0] + "\n" + scope_decl[0] + "\n")
    chunks.append("void integration_log(const char *, ...);\n#define MP_INFO(obj, ...) integration_log(__VA_ARGS__)\n")
    full = []
    for name in FUNCTIONS:
        if name not in actual_functions:
            raise ValueError(f"required actual VO function absent: {name}")
        function = actual_functions[name]
        chunks.append(f'#line {function["line"]} "video/out/vo.c"\n{function["text"]}\n')
        full.append({"file": "video/out/vo.c", "function": name, "line": function["line"],
                     "sha256": hashlib.sha256(function["text"].encode()).hexdigest()})
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
    with tempfile.TemporaryDirectory(prefix="mpv-native-ass-integration-") as directory:
        work = Path(directory)
        translation = work / "real-declarations-consumers.c"
        translation.write_text(generated, encoding="utf-8")
        command = [str(cc), "-std=c99", "-Werror", "-I", str(source), "-c", str(translation), "-o", str(work / "gate.o")]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=60)
        result = {"pass": completed.returncode == 0 and not closure_errors,
                  "returncode": completed.returncode, "closure_errors": closure_errors,
                  "compiler": str(cc), "diagnostics": (completed.stdout + completed.stderr)[-18000:],
                  "real_complete_structs": declarations,
                  "verbatim_full_functions": full, "actual_member_operand_count": len(operands),
                  "actual_member_operands": operands,
                  "translation_sha256": hashlib.sha256(generated.encode()).hexdigest(),
                  "scope": "REAL_COMPLETE_DECLARATIONS_SELECTED_VERBATIM_FUNCTIONS_AND_GPU_MEMBER_OPERANDS_NOT_FULL_TRANSLATION_UNITS",
                  "boundary_stubs": ["opaque Windows OS HANDLE/DWORD/condition/once/lock types; no platform ABI assertion",
                                     "logging function/macro boundary; all format argument expressions remain compiled",
                                     "can_present_early compiled with HAVE_D3D11=0; real D3D11 branch is not compiled"],
                  "not_covered": ["full vo.c/d3d11/context.c/vo_gpu_next.c translation units and their external SDK APIs",
                                  "Meson dependency discovery, linker, optimization, ABI, threading, runtime, GPU, Display/frame pacing"]}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--variant", required=True, choices=("main", "atmos"))
    parser.add_argument("--cc", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    hashes = {}

    def read(path):
        data = (source / path).read_bytes()
        hashes[path] = hashlib.sha256(data).hexdigest()
        return data.decode("utf-8")

    result = {"source": str(source), "variant": args.variant,
              "runtime_verified": False, "gpu_started": False, "full_build_verified": False}
    try:
        result["meson"] = meson_check(source, args.variant, read)
        # Collect C evidence even if Meson fails; do not hide a second blocker.
        result["compile"] = compile_gate(source, args.cc.resolve(), read)
        success = result["meson"]["pass"] and result["compile"]["pass"]
        result["status"] = "LIMITED_REAL_DECLARATION_CONSUMER_COMPILE_PASS_NOT_FULL_BUILD_OR_RUNTIME" if success else "INTEGRATION_GATE_FAIL"
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        success = False
        result["status"] = "INTEGRATION_GATE_FAIL"
        result["error"] = str(error)
    result["source_sha256"] = hashes
    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + "\n", encoding="utf-8")
    print(output)
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
