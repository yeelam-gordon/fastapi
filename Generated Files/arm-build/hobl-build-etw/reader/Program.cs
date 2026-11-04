using System.Text.Json;
using Microsoft.Diagnostics.Tracing;
using Microsoft.Diagnostics.Tracing.Parsers;
using Microsoft.Diagnostics.Tracing.Session;

if (args.Length == 2 && args[0] == "--sessions")
{
    try
    {
        var names = TraceEventSession.GetActiveSessionNames();
        File.WriteAllText(args[1], JsonSerializer.Serialize(names));
    }
    catch (System.Runtime.InteropServices.COMException error)
    {
        Environment.ExitCode = error.HResult;
    }
    catch (UnauthorizedAccessException error)
    {
        Environment.ExitCode = error.HResult;
    }
    return;
}

if (args.Length > 0 && args[0] == "--modules")
{
    try { ModuleMap.Run(args[1..]); }
    catch (InvalidDataException error) when (ModuleMap.FailureCodes.ContainsKey(error.Message))
    {
        Environment.ExitCode = ModuleMap.FailureCodes[error.Message];
    }
    return;
}
if (args.Length != 3)
    throw new ArgumentException("Expected ETL, private JSONL, private summary paths.");
using var source = new ETWTraceEventSource(args[0]);
using var rows = new StreamWriter(args[1]);
var counts = new SortedDictionary<string, long>();
var shapes = new SortedDictionary<string, long>();
var births = new Dictionary<int, long>();
long all = 0, populatedThreads = 0, sampleTid = 0, sampleIp = 0;
long? frequency = null;
int? rawClock = null, buffersLost = null;
long? headerQpc = null;
int? headerVersion = null, headerOpcode = null;
Guid? headerProvider = null;
int? headerEventId = null;
object? headerCallbackIdentity = null;
long lastQpc = long.MinValue;
void Emit(string kind, TraceEvent e, object? payload = null)
{
    counts[kind] = counts.GetValueOrDefault(kind) + 1;
    string shape = $"{kind}|{e.GetType().Name}|v{e.Version}|op{(int)e.Opcode}";
    shapes[shape] = shapes.GetValueOrDefault(shape) + 1;
    rows.WriteLine(JsonSerializer.Serialize(new {
        schema = 2, kind, sourceType = e.GetType().Name,
        provider = e.ProviderGuid, eventId = (int)e.ID,
        version = e.Version, opcode = (int)e.Opcode,
        qpc = e.TimeStampQPC, pid = e.ProcessID, tid = e.ThreadID,
        processBirthQpc = births.TryGetValue(e.ProcessID, out var birth) ? (long?)birth : null,
        payload
    }));
}
var kernel = source.Kernel;
kernel.EventTraceHeader += e => {
    frequency = e.PerfFreq;
    rawClock = e.ReservedFlags;
    buffersLost = e.BuffersLost;
    headerQpc = e.TimeStampQPC;
    headerVersion = ((TraceEvent)e).Version;
    headerOpcode = (int)e.Opcode;
    headerProvider = e.ProviderGuid;
    headerEventId = (int)e.ID;
    headerCallbackIdentity = new {
        provider = e.ProviderGuid, eventId = (int)e.ID,
        version = ((TraceEvent)e).Version, opcode = (int)e.Opcode
    };
};
kernel.ProcessStart += e => {
    births[e.ProcessID] = e.TimeStampQPC;
    Emit("processStart", e, new { parentPid = e.ParentID });
};
kernel.ProcessStop += e => {
    Emit("processStop", e, new { parentPid = e.ParentID });
    births.Remove(e.ProcessID);
};
kernel.ProcessDCStart += e => Emit("processDCStart", e, new { parentPid = e.ParentID });
kernel.ProcessDCStop += e => Emit("processDCStop", e, new { parentPid = e.ParentID });
kernel.ThreadStart += e => {
    if (e.ProcessID >= 0 && e.ThreadID >= 0) populatedThreads++;
    Emit("threadStart", e);
};
kernel.ThreadStop += e => Emit("threadStop", e);
kernel.ThreadDCStart += e => Emit("threadDCStart", e);
kernel.ThreadDCStop += e => Emit("threadDCStop", e);
kernel.ImageLoad += e => Emit("imageLoad", e, new { imageBase = e.ImageBase, imageSize = e.ImageSize, fileName = e.FileName });
kernel.ImageDCStart += e => Emit("imageDCStart", e, new { imageBase = e.ImageBase, imageSize = e.ImageSize, fileName = e.FileName });
kernel.ImageDCStop += e => Emit("imageDCStop", e, new { imageBase = e.ImageBase, imageSize = e.ImageSize, fileName = e.FileName });
kernel.ImageUnload += e => Emit("imageUnload", e, new { imageBase = e.ImageBase, imageSize = e.ImageSize, fileName = e.FileName });
kernel.PerfInfoSample += e => {
    if (e.ThreadID >= 0) sampleTid++;
    if (e.InstructionPointer != 0) sampleIp++;
    Emit("sample", e, new { instructionPointer = e.InstructionPointer });
};
kernel.FileIOCreate += e => Emit("fileCreate", e, new { irp = e.IrpPtr, fileObject = e.FileObject, fileName = e.FileName });
kernel.FileIORead += e => Emit("fileRead", e, new { irp = e.IrpPtr, fileObject = e.FileObject, fileKey = e.FileKey, sizeBytes = e.IoSize });
kernel.FileIOWrite += e => Emit("fileWrite", e, new { irp = e.IrpPtr, fileObject = e.FileObject, fileKey = e.FileKey, sizeBytes = e.IoSize });
kernel.FileIOOperationEnd += e => Emit("fileOpEnd", e, new {
    irp = e.IrpPtr, extraInfo = e.ExtraInfo, ntStatus = unchecked((uint)e.NtStatus)
});
kernel.ThreadCSwitch += e => Emit("cswitch", e, new {
    oldTid = e.OldThreadID, newTid = e.NewThreadID, oldThreadState = (int)e.OldThreadState,
    oldThreadWaitReason = (int)e.OldThreadWaitReason, oldThreadWaitMode = (int)e.OldThreadWaitMode,
    processorNumber = e.ProcessorNumber
});
kernel.DispatcherReadyThread += e => Emit("readyThread", e, new {
    awakenedTid = e.AwakenedThreadID, adjustReason = (int)e.AdjustReason,
    adjustIncrement = e.AdjustIncrement, flags = e.Flags, processorNumber = e.ProcessorNumber
});
source.AllEvents += e => { all++; lastQpc = Math.Max(lastQpc, e.TimeStampQPC); };
bool complete = source.Process();
if (!complete || frequency is null || rawClock is null || buffersLost is null || headerQpc is null
    || headerProvider is null || headerEventId is null || headerVersion is null
    || headerOpcode is null || headerCallbackIdentity is null)
    throw new InvalidDataException("Incomplete typed header.");
rows.WriteLine(JsonSerializer.Serialize(new {
    schema = 2, kind = "header", sourceType = "EventTraceHeaderTraceData",
    provider = headerProvider, eventId = headerEventId,
    version = headerVersion, opcode = headerOpcode, qpc = headerQpc,
    pid = (int?)null, tid = (int?)null, processBirthQpc = (long?)null,
    payload = new { perfFreq = frequency, reservedFlags = rawClock, eventsLost = source.EventsLost,
        buffersLost, sessionStartFileTime = source.SessionStartTime.ToFileTimeUtc(),
        sessionEndFileTime = source.SessionEndTime.ToFileTimeUtc(), lastQpc }
}));
rows.Flush();
File.WriteAllText(args[2], JsonSerializer.Serialize(new {
    schema = 2, complete, package = "Microsoft.Diagnostics.Tracing.TraceEvent",
    packageVersion = "4.0.0", assemblyVersion = typeof(TraceEvent).Assembly.GetName().Version?.ToString(),
    allCallbacks = all, counts, shapes, populatedThreadStarts = populatedThreads,
    samplesWithSourceTid = sampleTid, samplesWithNonzeroIp = sampleIp,
    qpcFrequencyHz = frequency, headerReservedFlags = rawClock, eventsLost = source.EventsLost,
    timerResolution100ns = source.TimerResolution,
    buffersLost,
    headerCallbackIdentity,
    clockRepresentation = "TraceEvent.TimeStampQPC ticks; original header ReservedFlags preserved separately",
    birthPolicy = "Observed ProcessStart QPC only; censored/unknown birth is null; no root filtering"
}, new JsonSerializerOptions { WriteIndented = true }));
