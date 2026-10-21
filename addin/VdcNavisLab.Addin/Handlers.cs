// Navisworks API calls, all executed on the UI thread through UiThread.Run.
// Every API detail marked VERIFY has to be checked against the installed Autodesk.Navisworks.* assemblies.
using System;
using System.Collections.Generic;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using Autodesk.Navisworks.Api;
using Autodesk.Navisworks.Api.Clash;

namespace VdcNavisLab.Addin
{
    internal sealed class Handlers
    {
        private static readonly DateTime Started = DateTime.UtcNow;
        private readonly string _instance = Guid.NewGuid().ToString("N").Substring(0, 8);
        private readonly Jobs _jobs = new Jobs();

        // ------------------------------------------------------------ document
        private static Document Doc()
        {
            var d = Autodesk.Navisworks.Api.Application.ActiveDocument;
            if (d == null || d.IsClear) throw new RpcException("no_document", "no document is open in Navisworks");
            return d;
        }

        private static string Fingerprint(Document d)
        {
            var parts = new List<string> { d.FileName ?? d.Title ?? "" };
            parts.AddRange(d.Models.Select(m => m.FileName ?? "").OrderBy(x => x, StringComparer.Ordinal));
            return Sha1(string.Join("|", parts)).Substring(0, 16);
        }

        // Revision: a hash of what a clash analysis depends on (tests, result guids, result statuses).
        private static string Revision(Document d)
        {
            var sb = new StringBuilder();
            foreach (var t in Tests(d))
            {
                sb.Append(t.Guid).Append(t.Status);
                foreach (var r in Results(t)) sb.Append(r.Guid).Append(r.Status);
            }
            return Sha1(sb.ToString()).Substring(0, 12);
        }

        private static string Sha1(string s)
        {
            using (var h = SHA1.Create())
                return string.Concat(h.ComputeHash(Encoding.UTF8.GetBytes(s)).Select(b => b.ToString("x2")));
        }

        private static Dictionary<string, object> DocState(Document d)
        {
            return new Dictionary<string, object>
            {
                { "open", true }, { "title", d.Title }, { "fingerprint", Fingerprint(d) }, { "revision", Revision(d) }
            };
        }

        private static string VersionText()
        {
            try
            {
                var v = Autodesk.Navisworks.Api.Application.Version;
                return v.RuntimeProductName + " " + v.Runtime;
            }
            catch (Exception ex) { return "unknown (" + ex.GetType().Name + ")"; }
        }

        public object Hello(string[] methods)
        {
            return UiThread.Run<object>(() =>
            {
                var d = Autodesk.Navisworks.Api.Application.ActiveDocument;
                var doc = (d == null || d.IsClear) ? new Dictionary<string, object> { { "open", false } } : DocState(d);
                return new Dictionary<string, object>
                {
                    { "product", "navisworks" }, { "version", VersionText() },
                    { "api", 1 }, { "instance_id", _instance },
                    { "started", (Started - new DateTime(1970, 1, 1)).TotalSeconds }, { "doc", doc }, { "methods", methods }
                };
            });
        }

        public object DocInfo()
        {
            return UiThread.Run<object>(() =>
            {
                var d = Doc();
                var info = DocState(d);
                info["models"] = d.Models.Select(m => m.FileName).ToArray();
                info["units"] = "m";  // exported coordinates are always converted to metres
                return info;
            });
        }

        // ------------------------------------------------------------ clash data
        private static IEnumerable<ClashTest> Tests(Document d)
        {
            return d.GetClash().TestsData.Tests.OfType<ClashTest>();  // VERIFY: DocumentClash.TestsData.Tests
        }

        private static IEnumerable<ClashResult> Results(ClashTest t)
        {
            foreach (SavedItem child in t.Children)
            {
                var r = child as ClashResult;
                if (r != null) { yield return r; continue; }
                var g = child as ClashResultGroup;
                if (g != null) foreach (SavedItem inner in g.Children) { var rr = inner as ClashResult; if (rr != null) yield return rr; }
            }
        }

        private static string Kind(ClashTest t)
        {
            switch (t.TestType)  // VERIFY enum names
            {
                case ClashTestType.Clearance: return "clearance";
                case ClashTestType.Duplicate: return "duplicate";
                default: return "hard";
            }
        }

        private static string TestStatus(ClashTest t) { return t.Status == ClashTestStatus.New ? "new" : "active"; }  // VERIFY

        public object ClashTests()
        {
            return UiThread.Run<object>(() =>
            {
                var d = Doc();
                return Tests(d).Select(t => (object)new Dictionary<string, object>
                {
                    { "name", t.DisplayName }, { "kind", Kind(t) }, { "status", TestStatus(t) },
                    { "tolerance", Metres(d, t.Tolerance) }, { "count", Results(t).Count() }
                }).ToList();
            });
        }

        // ------------------------------------------------------------ units
        private static double UnitFactor(Document d)
        {
            switch (d.Units)  // VERIFY: Document.Units / Units enum
            {
                case Units.Millimeters: return 0.001;
                case Units.Centimeters: return 0.01;
                case Units.Meters: return 1.0;
                case Units.Kilometers: return 1000.0;
                case Units.Inches: return 0.0254;
                case Units.Feet: return 0.3048;
                case Units.Yards: return 0.9144;
                case Units.Miles: return 1609.344;
                default: return 1.0;
            }
        }

        private static double Metres(Document d, double v) { return Math.Round(v * UnitFactor(d), 6); }

        // ------------------------------------------------------------ element description
        private static string Prop(ModelItem item, string category, string name)
        {
            try
            {
                var p = item.PropertyCategories.FindPropertyByDisplayName(category, name);
                return p == null ? "" : p.Value.ToDisplayString();
            }
            catch { return ""; }
        }

        private static string FirstProp(ModelItem item, params string[][] where)
        {
            foreach (var w in where) { var v = Prop(item, w[0], w[1]); if (v.Length > 0) return v; }
            return "";
        }

        private static readonly string[] FileExtensions = { ".rvt", ".ifc", ".dwg", ".nwc", ".nwd", ".dgn", ".skp", ".rfa", ".3dm", ".dwfx", ".fbx" };

        /// <summary>Display names from the root of the selection tree down to the item (empty names skipped).</summary>
        private static List<string> PathOf(ModelItem item)
        {
            var names = new List<string>();
            for (var c = item; c != null; c = c.Parent)
            {
                var n = c.DisplayName;
                if (!string.IsNullOrEmpty(n)) names.Add(n);
            }
            names.Reverse();
            return names;
        }

        /// <summary>Source file of an item. A federated NWD reports one file for everything, so the tree is searched first.</summary>
        private static string ModelName(Document d, ModelItem item, List<string> path)
        {
            var self = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
                { d.Title ?? "", System.IO.Path.GetFileName(d.FileName ?? "") };
            foreach (var seg in path)
            {
                var l = seg.ToLowerInvariant();
                if (self.Contains(seg)) continue;
                if (FileExtensions.Any(e => l.EndsWith(e))) return seg;
            }
            var m = item.Model;
            if (m != null)
            {
                var f = System.IO.Path.GetFileName(m.FileName ?? "");
                if (f.Length > 0 && !self.Contains(f)) return f;
                if (m.RootItem != null && !string.IsNullOrEmpty(m.RootItem.DisplayName) && !self.Contains(m.RootItem.DisplayName))
                    return m.RootItem.DisplayName;
            }
            return path.Count > 1 ? path[1] : (path.Count > 0 ? path[0] : "");
        }

        private static string Short(string text)
        {
            using (var sha = SHA1.Create())
            {
                var h = sha.ComputeHash(Encoding.UTF8.GetBytes(text));
                return BitConverter.ToString(h, 0, 6).Replace("-", "").ToLowerInvariant();
            }
        }

        /// <summary>Index of the source-file level of the tree (the .nwc/.rvt node), or -1.</summary>
        private static int SourceIndex(Document d, List<string> path)
        {
            var self = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
                { d.Title ?? "", System.IO.Path.GetFileName(d.FileName ?? "") };
            for (int i = 0; i < path.Count; i++)
            {
                var l = path[i].ToLowerInvariant();
                if (self.Contains(path[i])) continue;
                if (FileExtensions.Any(e => l.EndsWith(e))) return i;
            }
            return -1;
        }

        private static string At(List<string> path, int index, int leaf)
        {
            return index >= 0 && index < leaf ? path[index] : "";
        }

        private static Dictionary<string, object> Describe(Document d, ModelItem item)
        {
            var bb = item.BoundingBox();
            double f = UnitFactor(d);
            var elementId = FirstProp(item, new[] { "Element ID", "Value" }, new[] { "Element", "Id" });
            var path = PathOf(item);
            int fi = SourceIndex(d, path);
            int leaf = path.Count - 1;  // the last node is the solid (named after its material in Revit exports)
            var modelFile = FirstProp(item, new[] { "Elemento", "Archivo de origen" }, new[] { "Element", "Source File" });
            if (modelFile.Length == 0) modelFile = ModelName(d, item, path);
            var bbox = new object[] {
                new object[] { Math.Round(bb.Min.X * f, 4), Math.Round(bb.Min.Y * f, 4), Math.Round(bb.Min.Z * f, 4) },
                new object[] { Math.Round(bb.Max.X * f, 4), Math.Round(bb.Max.Y * f, 4), Math.Round(bb.Max.Z * f, 4) } };
            var boxText = string.Join(",", ((object[])bbox[0]).Concat((object[])bbox[1]));
            // Identity must be unique per element: InstanceGuid is all zeros for most geometry items, so it is only
            // used when set; otherwise the tree path plus the box identify the item.
            string ident;
            if (elementId.Length > 0) ident = elementId;
            else if (item.InstanceGuid != Guid.Empty) ident = item.InstanceGuid.ToString();
            else ident = "p" + Short(string.Join("/", path) + "|" + boxText);

            // Revit exports: file / layer(level) / category / family / type / instance / solid.
            var category = At(path, fi + 2, leaf);
            if (category.Length == 0) category = FirstProp(item, new[] { "Item", "Type" }, new[] { "Element", "Category" });
            if (category.Length == 0) category = item.ClassDisplayName ?? "";
            var family = At(path, fi + 3, leaf);
            if (family.Length == 0) family = FirstProp(item, new[] { "Element", "Family" });
            var type = At(path, fi + 4, leaf);
            var name = family.Length > 0 ? (type.Length > 0 ? family + " : " + type : family) : (item.DisplayName ?? "");
            var level = FirstProp(item, new[] { "Elemento", "Capa" }, new[] { "Element", "Layer" }, new[] { "Element", "Level" });
            if (level.Length == 0) level = At(path, fi + 1, leaf);

            // Assembly identity: the instance node (parent of the solid) and its own box, so two walls of the same
            // type are different assemblies but the layers of one wall are the same.
            string host = "";
            var parent = item.Parent;
            if (parent != null && !item.Children.Any())
            {
                var pb = parent.BoundingBox();
                host = modelFile + ":h" + Short(string.Join("/", path.Take(leaf)) + "|" +
                    string.Join(",", new[] { pb.Min.X, pb.Min.Y, pb.Min.Z, pb.Max.X, pb.Max.Y, pb.Max.Z }.Select(v => Math.Round(v * f, 3).ToString(System.Globalization.CultureInfo.InvariantCulture))));
            }

            var o = new Dictionary<string, object>
            {
                { "id", modelFile + ":" + ident },
                { "name", name },
                { "category", category },
                { "family", family },
                { "model", modelFile },
                { "path", path },
                { "level", level },
                { "props", elementId.Length > 0 ? new Dictionary<string, object> { { "Id", elementId } } : new Dictionary<string, object>() },
                { "bbox", bbox }
            };
            if (host.Length > 0) o["host_id"] = host;
            if (type.Length > 0) ((Dictionary<string, object>)o["props"])["Type"] = type;
            var system = FirstProp(item, new[] { "Element", "System Name" }, new[] { "Element", "System Type" });
            if (system.Length > 0) o["system"] = system;
            return o;
        }

        // ------------------------------------------------------------ diagnostic sample
        private static Dictionary<string, object> Raw(Document d, ModelItem item)
        {
            var cats = new List<object>();
            try
            {
                int nc = 0;
                foreach (var pc in item.PropertyCategories)
                {
                    if (++nc > 40) break;
                    var props = new Dictionary<string, object>();
                    int np = 0;
                    foreach (var pr in pc.Properties)
                    {
                        if (++np > 60) break;
                        string v; try { v = pr.Value.ToDisplayString(); } catch { v = "?"; }
                        props[pr.DisplayName ?? pr.Name] = v;
                    }
                    cats.Add(new Dictionary<string, object> { { "category", pc.DisplayName }, { "props", props } });
                }
            }
            catch { }
            var path = PathOf(item);
            var m = item.Model;
            return new Dictionary<string, object>
            {
                { "path", path }, { "name", item.DisplayName ?? "" }, { "class", item.ClassDisplayName ?? "" },
                { "model_file_name", m != null ? (m.FileName ?? "") : "" },
                { "model_root", m != null && m.RootItem != null ? (m.RootItem.DisplayName ?? "") : "" },
                { "resolved_model", ModelName(d, item, path) },
                { "instance_guid", item.InstanceGuid.ToString() }, { "categories", cats }
            };
        }

        public object Sample(Dictionary<string, object> p)
        {
            int per = p.ContainsKey("per_test") ? Convert.ToInt32(p["per_test"]) : 2;
            return UiThread.Run<object>(() =>
            {
                var d = Doc();
                var list = new List<object>();
                foreach (var t in Tests(d))
                {
                    int n = 0;
                    foreach (var r in Results(t))
                    {
                        if (n++ >= per) break;
                        var row = new Dictionary<string, object> { { "test", t.DisplayName }, { "result", r.DisplayName }, { "status", r.Status.ToString() } };
                        if (r.Item1 == null || r.Item2 == null) row["missing_items"] = true;
                        else { row["a"] = Raw(d, r.Item1); row["b"] = Raw(d, r.Item2); }
                        list.Add(row);
                    }
                }
                return new Dictionary<string, object>
                {
                    { "document", d.Title }, { "file", d.FileName ?? "" },
                    { "models", d.Models.Select(m => (object)new Dictionary<string, object> { { "file", m.FileName ?? "" }, { "root", m.RootItem != null ? (m.RootItem.DisplayName ?? "") : "" } }).ToList() },
                    { "samples", list }
                };
            }, 120000);
        }

        private static string ResultStatus(ClashResult r)
        {
            switch (r.Status)  // VERIFY ClashResultStatus names
            {
                case ClashResultStatus.Active: return "active";
                case ClashResultStatus.Reviewed: return "reviewed";
                case ClashResultStatus.Approved: return "approved";
                case ClashResultStatus.Resolved: return "resolved";
                default: return "new";
            }
        }

        // ------------------------------------------------------------ export job
        public object StartExport(Dictionary<string, object> p)
        {
            var names = new HashSet<string>(((p.ContainsKey("tests") ? p["tests"] as System.Collections.ArrayList : null) ?? new System.Collections.ArrayList())
                .Cast<object>().Select(x => Convert.ToString(x)));
            int limit = p.ContainsKey("limit") ? Convert.ToInt32(p["limit"]) : 0;
            var job = _jobs.Create("clash.export");
            // 0.1 limitation: extraction runs on the UI thread in one block, so Navisworks is unresponsive meanwhile.
            // Chunked extraction (a few tests per UI slice) is the first item on the add-in roadmap.
            UiThreadPost(() => Export(job, names, limit));
            return new Dictionary<string, object> { { "job_id", job.Id } };
        }

        private static void UiThreadPost(Action a) { System.Threading.ThreadPool.QueueUserWorkItem(_ => { try { UiThread.Run<object>(() => { a(); return null; }, 600000); } catch { } }); }

        private void Export(Jobs.Job job, HashSet<string> names, int limit)
        {
            try
            {
                var d = Doc();
                var tests = new List<object>();
                var clashes = new List<object>();
                bool truncated = false;
                foreach (var t in Tests(d))
                {
                    if (job.Cancelled) { job.Finish("cancelled", null, ""); return; }
                    if (names.Count > 0 && !names.Contains(t.DisplayName)) continue;
                    var results = Results(t).ToList();
                    tests.Add(new Dictionary<string, object> {
                        { "name", t.DisplayName }, { "kind", Kind(t) }, { "status", TestStatus(t) },
                        { "tolerance", Metres(d, t.Tolerance) }, { "count", results.Count } });
                    foreach (var r in results)
                    {
                        if (limit > 0 && clashes.Count >= limit) { truncated = true; break; }
                        if (r.Item1 == null || r.Item2 == null) continue;
                        var a = Describe(d, r.Item1); var b = Describe(d, r.Item2);
                        clashes.Add(new Dictionary<string, object> {
                            { "id", r.Guid.ToString() }, { "test", t.DisplayName }, { "name", r.DisplayName },
                            { "status", ResultStatus(r) }, { "kind", Kind(t) }, { "distance", Metres(d, r.Distance) },
                            { "point", new object[] { Metres(d, r.Center.X), Metres(d, r.Center.Y), Metres(d, r.Center.Z) } },
                            { "a", a }, { "b", b }, { "level", a["level"] } });
                    }
                }
                job.Finish("completed", new Dictionary<string, object> {
                    { "schema", "vdc_navis_lab.clashset/1" }, { "source", "navisworks" }, { "document", DocState(d) },
                    { "models", d.Models.Select(m => System.IO.Path.GetFileName(m.FileName ?? "")).ToArray() },
                    { "truncated", truncated }, { "tests", tests }, { "clashes", clashes } }, "");
            }
            catch (RpcException ex) { job.Finish("failed", null, ex.Message); }
            catch (Exception ex) { job.Finish("failed", null, ex.GetType().Name); }
        }

        // ------------------------------------------------------------ writes
        // Idempotency: a dedupe_key that was already applied replays its result instead of acting twice
        // (the MCP client retries a timed-out call). Kept in memory only; cleared when Navisworks reloads the add-in.
        private readonly Dictionary<string, Dictionary<string, object>> _applied = new Dictionary<string, Dictionary<string, object>>();
        private readonly object _appliedGate = new object();

        private static List<string> Strings(object v)
        {
            var list = new List<string>();
            var al = v as System.Collections.ArrayList;
            if (al != null) foreach (var x in al) { var s = Convert.ToString(x); if (s.Length > 0) list.Add(s); }
            return list;
        }

        private static ClashResultStatus? ParseStatus(string s)
        {
            switch (s)  // VERIFY enum names; "new" is intentionally not reachable here (server never offers it, see SETTABLE_STATUS)
            {
                case "active": return ClashResultStatus.Active;
                case "reviewed": return ClashResultStatus.Reviewed;
                case "approved": return ClashResultStatus.Approved;
                case "resolved": return ClashResultStatus.Resolved;
                default: return null;
            }
        }

        /// <summary>A group with this name directly under the test, or null.</summary>
        private static ClashResultGroup FindGroup(ClashTest t, string name)
        {
            foreach (SavedItem child in t.Children)
            {
                var g = child as ClashResultGroup;
                if (g != null && g.DisplayName == name) return g;
            }
            return null;
        }

        public object ClashApply(Dictionary<string, object> p)
        {
            return UiThread.Run<object>(() =>
            {
                var d = Doc();
                var fp = p.ContainsKey("if_fingerprint") ? Convert.ToString(p["if_fingerprint"]) : "";
                if (fp != Fingerprint(d))
                    throw new RpcException("stale_document", "the open document is not the one the plan was made for",
                        "run nw_status and re-analyze before applying");
                // Results and tests come back read-only (direct property/collection mutation throws
                // NotSupportedException: "Object is Read-Only"). DocumentClashTests is the sanctioned editor.
                var edit = d.GetClash().TestsData;

                var key = p.ContainsKey("dedupe_key") ? Convert.ToString(p["dedupe_key"]) : "";
                lock (_appliedGate)
                {
                    Dictionary<string, object> cached;
                    if (key.Length > 0 && _applied.TryGetValue(key, out cached))
                    {
                        var replay = new Dictionary<string, object>(cached) { ["replayed"] = true };
                        return (object)replay;
                    }
                }

                // Index every result by guid and by its test's guid, reusing Results() -- already proven against
                // real Navisworks by clash.export and doc.sample -- instead of re-walking Children by hand.
                // Membership and identity below compare Guid values, never object references: a COM-backed
                // wrapper object is not guaranteed to be the same instance on a second property access.
                var byGuid = new Dictionary<string, ClashResult>();
                var ownerTestGuid = new Dictionary<string, Guid>();
                var testByGuid = new Dictionary<Guid, ClashTest>();
                int testCount = 0, resultCount = 0;
                foreach (var t in Tests(d))
                {
                    testCount++;
                    testByGuid[t.Guid] = t;
                    foreach (var r in Results(t))
                    {
                        resultCount++;
                        var g = r.Guid.ToString();
                        byGuid[g] = r;
                        ownerTestGuid[g] = t.Guid;
                    }
                }
                Log.Write("clash.apply: indexed " + resultCount + " results across " + testCount + " tests (byGuid=" + byGuid.Count + ")");

                var missing = new List<string>();
                int groupsAdded = 0, groupsReused = 0, statusesSet = 0, verifiedStatuses = 0;
                var groupChecks = new List<KeyValuePair<Guid, List<string>>>();  // the group's own guid, and the guids it should hold

                var groupsArg = p.ContainsKey("groups") ? p["groups"] as System.Collections.ArrayList : null;
                if (groupsArg != null)
                    foreach (var go in groupsArg)
                    {
                        var gd = (Dictionary<string, object>)go;
                        var name = Convert.ToString(gd["name"]);
                        var guids = Strings(gd["guids"]);
                        var known = guids.Where(byGuid.ContainsKey).ToList();
                        missing.AddRange(guids.Except(known));
                        if (known.Count == 0)
                        {
                            Log.Write("clash.apply group '" + name + "': none of " + guids.Count + " guids are in the index");
                            continue;
                        }
                        var testGuid = ownerTestGuid[known[0]];
                        // A group lives under one test; members already in a different test are left alone and reported missing.
                        var sameTest = known.Where(g => ownerTestGuid[g] == testGuid).ToList();
                        missing.AddRange(known.Except(sameTest));
                        try
                        {
                            var test = testByGuid[testGuid];
                            var group = FindGroup(test, name);
                            if (group == null)
                            {
                                // TestsInsertCopy inserts a COPY of the template; the live item has to be found
                                // again under the test afterwards (VERIFY: exact insertion position and lookup).
                                edit.TestsInsertCopy(test, test.Children.Count, new ClashResultGroup { DisplayName = name });
                                group = FindGroup(test, name);
                                if (group == null) throw new InvalidOperationException("inserted group not found by name afterwards");
                                groupsAdded++;
                            }
                            else groupsReused++;
                            foreach (var g in sameTest)
                            {
                                var r = byGuid[g];
                                if (r.Parent != null && r.Parent.Guid == group.Guid) continue;  // already a member
                                var oldParent = r.Parent;
                                var oldIndex = oldParent.Children.IndexOf(r);  // VERIFY: IndexOf matches TestsMove's expectations
                                edit.TestsMove(oldParent, oldIndex, group, group.Children.Count);
                            }
                            groupChecks.Add(new KeyValuePair<Guid, List<string>>(group.Guid, sameTest));
                        }
                        catch (Exception ex)
                        {
                            Log.Write("clash.apply group '" + name + "' failed: " + ex.GetType().Name + ": " + ex.Message);
                            missing.AddRange(sameTest);
                        }
                    }

                var statusesArg = p.ContainsKey("statuses") ? p["statuses"] as System.Collections.ArrayList : null;
                if (statusesArg != null)
                    foreach (var so in statusesArg)
                    {
                        var sd = (Dictionary<string, object>)so;
                        var want = ParseStatus(Convert.ToString(sd["status"]));
                        var guids = Strings(sd["guids"]);
                        if (want == null) { Log.Write("clash.apply: unknown status word"); continue; }
                        foreach (var g in guids)
                        {
                            ClashResult r;
                            if (!byGuid.TryGetValue(g, out r)) { missing.Add(g); continue; }
                            try
                            {
                                edit.TestsEditResultStatus(r, want.Value, new Assignee());  // VERIFY: Assignee() means "no one"
                                statusesSet++;
                                if (r.Status == want.Value) verifiedStatuses++;
                            }
                            catch (Exception ex)
                            {
                                Log.Write("clash.apply status for " + g + " failed: " + ex.GetType().Name);
                                missing.Add(g);
                            }
                        }
                    }

                int verifiedGroups = groupChecks.Count(kv => kv.Value.All(g => byGuid[g].Parent != null && byGuid[g].Parent.Guid == kv.Key));
                var result = new Dictionary<string, object>
                {
                    { "applied", new Dictionary<string, object> { { "groups_added", groupsAdded }, { "groups_reused", groupsReused }, { "statuses_set", statusesSet } } },
                    { "verified", new Dictionary<string, object> { { "groups", verifiedGroups }, { "statuses", verifiedStatuses } } },
                    { "missing", missing.Distinct().OrderBy(x => x, StringComparer.Ordinal).ToList() }
                };
                if (key.Length > 0) lock (_appliedGate) { _applied[key] = result; }
                return (object)result;
            }, 120000);
        }

        public object DocSave(Dictionary<string, object> p)
        {
            return UiThread.Run<object>(() =>
            {
                var d = Doc();
                var fp = p.ContainsKey("if_fingerprint") ? Convert.ToString(p["if_fingerprint"]) : "";
                if (fp != Fingerprint(d))
                    throw new RpcException("stale_document", "the open document is not the one the save was requested for");
                var path = p.ContainsKey("path") ? Convert.ToString(p["path"]) : "";
                // Document.SaveFile has no parameterless overload: saving in place means passing its own file name back.
                var target = path.Length > 0 ? path : d.FileName;
                if (string.IsNullOrEmpty(target))
                    throw new RpcException("invalid_params", "the document has no file name yet; pass path to save it as a new file");
                try { d.SaveFile(target); }
                catch (Exception ex) { throw new RpcException("internal", "save failed: " + ex.GetType().Name); }
                var verified = path.Length == 0
                    || string.Equals(System.IO.Path.GetFullPath(d.FileName ?? ""), System.IO.Path.GetFullPath(path), StringComparison.OrdinalIgnoreCase);
                return new Dictionary<string, object> { { "saved", true }, { "verified", verified }, { "path", d.FileName ?? path } };
            }, 120000);
        }

        // ------------------------------------------------------------ jobs
        public object JobStatus(Dictionary<string, object> p) { return _jobs.Get(p).Status(); }
        public object JobResult(Dictionary<string, object> p)
        {
            var j = _jobs.Get(p);
            if (j.State != "completed") throw new RpcException("busy", "job is " + j.State);
            return j.Result;
        }
        public object JobCancel(Dictionary<string, object> p) { var j = _jobs.Get(p); j.Cancel(); return new Dictionary<string, object> { { "job_id", j.Id }, { "state", j.State } }; }
        public object JobList() { return _jobs.All(); }
    }
}
