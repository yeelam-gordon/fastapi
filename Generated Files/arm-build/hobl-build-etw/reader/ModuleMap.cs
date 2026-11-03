using System.Text.Json;
using Microsoft.Diagnostics.Tracing.Etlx;

internal static class ModuleMap
{
    internal static readonly Dictionary<string, int> FailureCodes = new() {
        ["module_arguments"] = 71, ["module_selection_schema"] = 72,
        ["module_counts"] = 73, ["module_key_schema"] = 74,
        ["module_key_range"] = 75, ["module_multiowner"] = 76,
        ["module_stale_etlx"] = 77, ["module_trace_loss"] = 78,
        ["module_sample_identity"] = 79
    };

    internal static void Run(string[] args)
    {
        if (args.Length != 4 && !(args.Length == 5 && args[4] == "--existing"))
            throw new InvalidDataException("module_arguments");
        using var selection = JsonDocument.Parse(File.ReadAllText(args[2]));
        var root = selection.RootElement;
        if (root.ValueKind != JsonValueKind.Object ||
            !root.EnumerateObject().Select(p => p.Name).Order().SequenceEqual(new[] { "counts", "samples", "schema" }) ||
            root.GetProperty("schema").GetInt32() != 1)
            throw new InvalidDataException("module_selection_schema");
        var counts = root.GetProperty("counts").EnumerateArray().Select(v => v.GetInt64()).ToArray();
        if (counts.Length is < 1 or > 128 || counts.Any(n => n < 0))
            throw new InvalidDataException("module_counts");
        var keys = new Dictionary<(long Qpc, int Tid, ulong Ip), (int Owner, long Count)>();
        var selectedCounts = new long[counts.Length];
        foreach (var row in root.GetProperty("samples").EnumerateArray())
        {
            if (row.ValueKind != JsonValueKind.Array || row.GetArrayLength() != 4)
                throw new InvalidDataException("module_key_schema");
            var key = (row[0].GetInt64(), row[1].GetInt32(), row[2].GetUInt64());
            int owner = row[3].GetInt32();
            if (key.Item1 < 0 || key.Item2 < 0 || owner < 0 || owner >= counts.Length)
                throw new InvalidDataException("module_key_range");
            if (keys.TryGetValue(key, out var old) && old.Owner != owner)
                throw new InvalidDataException("module_multiowner");
            keys[key] = (owner, old.Count + 1);
            selectedCounts[owner]++;
        }
        if (!counts.SequenceEqual(selectedCounts) || counts.Sum() < 1)
            throw new InvalidDataException("module_counts");
        if (args.Length == 4)
        {
            if (File.Exists(args[1]))
                throw new InvalidDataException("module_stale_etlx");
            TraceLog.CreateFromEventTraceLogFile(args[0], args[1], new TraceLogOptions {
                ShouldResolveSymbols = _ => false, LocalSymbolsOnly = true,
                AlwaysResolveSymbols = false, ContinueOnError = false,
                MaxEventCount = 500000, ConversionLog = TextWriter.Null,
                OnLostEvents = (truncated, lost, _) => {
                    if (truncated || lost != 0)
                        throw new InvalidDataException("module_trace_loss");
                }
            });
        }
        using var log = new TraceLog(args[1]);
        if (log.Truncated || log.EventsLost != 0)
            throw new InvalidDataException("module_trace_loss");
        var kernel = new HashSet<ModuleFileIndex>();
        foreach (var process in log.Processes)
            if (process.ProcessID == 0)
                foreach (var loaded in process.LoadedModules)
                    if (loaded.ModuleFile is { } module)
                        kernel.Add(module.ModuleFileIndex);
        var allow = new HashSet<string>(StringComparer.OrdinalIgnoreCase) {
            "uv", "python", "python3", "python313", "ntdll", "kernel32", "kernelbase",
            "ucrtbase", "ntoskrnl", "ntkrnlmp", "hal", "win32k", "win32kbase",
            "win32kfull", "fltmgr", "ntfs", "refs", "fastfat", "volmgr", "volsnap",
            "mountmgr", "storport", "stornvme", "disk", "classpnp", "fileinfo", "wdfilter"
        };
        var buckets = new SortedDictionary<(int Owner, string Provenance, string Module, string Context), long>();
        long unexpected = 0;
        using var source = log.Events.GetSource();
        source.Kernel.PerfInfoSample += sample => {
            var key = (sample.TimeStampQPC, sample.ThreadID, sample.InstructionPointer);
            if (!keys.TryGetValue(key, out var selected))
                return;
            if (selected.Count == 0) { unexpected++; return; }
            keys[key] = (selected.Owner, selected.Count - 1);
            var module = sample.IntructionPointerCodeAddress()?.ModuleFile;
            string provenance = "unresolved", name = "unresolved";
            if (module is not null)
            {
                bool isKernel = kernel.Contains(module.ModuleFileIndex);
                bool isUser = sample.Process()?.LoadedModules.Any(
                    loaded => loaded.ModuleFile?.ModuleFileIndex == module.ModuleFileIndex) == true;
                if (isKernel != isUser)
                {
                    provenance = isKernel ? "kernel-table" : "user-table";
                    name = allow.Contains(module.Name) ? module.Name.ToLowerInvariant() :
                        isKernel ? "other-kernel" : "other-user";
                }
            }
            string context = sample.ExecutingDPC ?
                (sample.ExecutingISR ? "DPC_ISR" : "DPC") :
                (sample.ExecutingISR ? "ISR" : "PROCESS");
            var bucket = (selected.Owner, provenance, name, context);
            buckets[bucket] = buckets.GetValueOrDefault(bucket) + 1;
        };
        bool complete = source.Process();
        if (!complete || unexpected != 0 || keys.Values.Any(v => v.Count != 0))
            throw new InvalidDataException("module_sample_identity");
        var actual = new long[counts.Length];
        foreach (var bucket in buckets) actual[bucket.Key.Owner] += bucket.Value;
        if (!actual.SequenceEqual(counts))
            throw new InvalidDataException("module_counts");
        var result = new {
            schema = 1, cpu_units = "SAMPLE_COUNTS", cpu_samples = counts.Sum(),
            missing_samples = 0, unexpected_samples = 0,
            lifetimes = counts.Select((n, i) => new { process_index = i, cpu_samples = n }),
            modules = buckets.Select(b => new { process_index = b.Key.Owner,
                provenance = b.Key.Provenance, module = b.Key.Module,
                sample_context = b.Key.Context, samples = b.Value }),
            symbol_resolution = "DISABLED", scheduling = "UNSUPPORTED", file_durations = "UNSUPPORTED",
            interpretation = "MODULE_PROVENANCE_NOT_EXECUTION_MODE_CAUSE_OR_IO_LATENCY"
        };
        File.WriteAllText(args[3], JsonSerializer.Serialize(result));
    }
}
