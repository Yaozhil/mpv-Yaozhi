// Diagnostic-only probe: execute the official Start() property construction,
// intercept its first StartTrace call and fail it before any ETW operation.
#include <windows.h>
#include <evntrace.h>
#include <evntcons.h>
#include <cstddef>
#include <cstdio>
#include <cstring>

static EVENT_TRACE_PROPERTIES captured = {};
static unsigned intercepted = 0;
static ULONG WINAPI ProbeStartTraceW(PTRACEHANDLE handle, LPCWSTR, PEVENT_TRACE_PROPERTIES props)
{
    captured = *props;
    ++intercepted;
    *handle = 0;
    return ERROR_ACCESS_DENIED;
}

#define StartTraceW ProbeStartTraceW
#if defined(PM_PROBE_BASELINE)
#include "baseline-session.cpp"
#else
#include "PresentMonTraceSession.cpp"
#endif
#undef StartTraceW

static_assert(sizeof(void*) == 8, "Windows x64 only");
static_assert(sizeof(WNODE_HEADER) == 48, "WNODE_HEADER ABI differs");
static_assert(sizeof(EVENT_TRACE_PROPERTIES) == 120, "EVENT_TRACE_PROPERTIES ABI differs");
static_assert(offsetof(EVENT_TRACE_PROPERTIES, MinimumBuffers) == 52, "MinimumBuffers ABI");
static_assert(offsetof(EVENT_TRACE_PROPERTIES, MaximumBuffers) == 56, "MaximumBuffers ABI");
static_assert(offsetof(EVENT_TRACE_PROPERTIES, LogFileMode) == 64, "LogFileMode ABI");
static_assert(offsetof(EVENT_TRACE_PROPERTIES, EventsLost) == 88, "EventsLost ABI");
static_assert(offsetof(EVENT_TRACE_PROPERTIES, LoggerThreadId) == 104, "Thread handle ABI");
static_assert(offsetof(EVENT_TRACE_PROPERTIES, LoggerNameOffset) == 116, "Name offset ABI");

int main()
{
    PMTraceConsumer consumer;
    PMTraceSession session;
    session.mPMConsumer = &consumer;
    const ULONG status = session.Start(nullptr, L"YaozhiV30PropsProbe-NOT-A-TRACE-SESSION");
    if (status != ERROR_ACCESS_DENIED || intercepted != 1 || session.mSessionHandle != 0 ||
        session.mTraceHandle != INVALID_PROCESSTRACE_HANDLE)
        return 2;
    const auto bytes = reinterpret_cast<const unsigned char*>(&captured);
    std::printf("{\"intercepted_StartTrace_calls\":%u,\"real_ETW_calls\":0,"
                "\"status\":%lu,\"WNODE_HEADER_size\":%zu,\"properties_size\":%zu,"
                "\"WnodeBufferSize\":%lu,\"BufferSize\":%lu,\"MinimumBuffers\":%lu,"
                "\"MaximumBuffers\":%lu,\"ClientContext\":%lu,\"WnodeFlags\":%lu,"
                "\"LogFileMode\":%lu,\"LoggerNameOffset\":%lu,\"raw_properties_hex\":\"",
                intercepted, status, sizeof(WNODE_HEADER), sizeof(EVENT_TRACE_PROPERTIES),
                captured.Wnode.BufferSize, captured.BufferSize, captured.MinimumBuffers,
                captured.MaximumBuffers, captured.Wnode.ClientContext, captured.Wnode.Flags,
                captured.LogFileMode, captured.LoggerNameOffset);
    for (size_t i = 0; i != sizeof(captured); ++i) std::printf("%02x", bytes[i]);
    std::printf("\"}\n");
    return 0;
}
