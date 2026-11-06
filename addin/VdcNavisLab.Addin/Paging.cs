// Paged extraction of clash results: the server asks for one bounded slice at a time (clash.page) and keeps what it
// needs; nothing accumulates in the Navisworks process and no single call holds the UI thread for long.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using Autodesk.Navisworks.Api;
using Autodesk.Navisworks.Api.Clash;

namespace VdcNavisLab.Addin
{
    internal sealed partial class Handlers
    {
        // What one test looks like while it is being paged: its results with the open ones first, so that a partial
        // extraction (cap, memory) always keeps the results that matter. Only the test in progress is held.
        private sealed class PageList { public string Test; public List<ClashResult> Items; public int Open; public int Closed; }
        private static PageList _page;
        private static long _pageBaseline;
        private const long PageMemoryBudget = 1024L * 1024 * 1024;

        private static string S(Dictionary<string, object> p, string key) { object v; return p.TryGetValue(key, out v) && v != null ? Convert.ToString(v) : ""; }
        private static int I(Dictionary<string, object> p, string key, int fallback) { object v; return p.TryGetValue(key, out v) && v != null ? Convert.ToInt32(v) : fallback; }
        private static bool B(Dictionary<string, object> p, string key) { object v; return p.TryGetValue(key, out v) && true.Equals(v); }
        private static bool IsClosed(string status) { return status == "approved" || status == "resolved"; }

        /// <summary>params: test, cursor, limit, closed_describe (-1 = all, N = describe at most N closed results and only
        /// count the rest), begin (first call of an extraction: resets caches and the memory baseline), if_fingerprint,
        /// budget_ms (soft time budget of this call).</summary>
        public object ClashPage(Dictionary<string, object> p)
        {
            var name = S(p, "test");
            var cursor = Math.Max(0, I(p, "cursor", 0));
            var limit = Math.Max(25, Math.Min(3000, I(p, "limit", 500)));
            var closedLeft = I(p, "closed_describe", -1);
            var budgetMs = Math.Max(200, Math.Min(10000, I(p, "budget_ms", 1500)));
            var wantFingerprint = S(p, "if_fingerprint");
            var begin = B(p, "begin");
            return UiThread.Run<object>(() =>
            {
                var d = Doc();
                if (wantFingerprint.Length > 0 && Fingerprint(d) != wantFingerprint)
                    throw new RpcException("stale_document", "the open document is not the one the extraction started on", "start the analysis again");
                if (begin)
                {
                    _page = null; OrientedCache.Clear(); OrientedStatus.Clear();
                    _pageBaseline = PrivateBytes();
                }
                var t = Tests(d).FirstOrDefault(x => x.DisplayName == name);
                if (t == null) throw new RpcException("not_found", "unknown clash test");
                if (_page == null || _page.Test != name || cursor == 0)
                {
                    var all = Results(t).ToList();
                    var open = new List<ClashResult>(all.Count);
                    var closed = new List<ClashResult>();
                    foreach (var r in all) (IsClosed(ResultStatus(r)) ? closed : open).Add(r);
                    var ordered = new List<ClashResult>(all.Count);
                    ordered.AddRange(open); ordered.AddRange(closed);
                    _page = new PageList { Test = name, Items = ordered, Open = open.Count, Closed = closed.Count };
                }
                var items = _page.Items;
                var clashes = new List<object>();
                int skipped = 0, skippedOpen = 0, closedSkipped = 0, closedDescribed = 0;
                string stop = null;
                var clock = Stopwatch.StartNew();
                int i = cursor;
                for (; i < items.Count; i++)
                {
                    if (clashes.Count >= limit) break;
                    if (clashes.Count > 0 && clock.ElapsedMilliseconds > budgetMs) break;
                    if ((i & 63) == 63 && PrivateBytes() - _pageBaseline > PageMemoryBudget)
                    {
                        Log.Write("paged export stopped by the memory guard in test at position " + i);
                        stop = "memory"; break;
                    }
                    var r = items[i];
                    var st = ResultStatus(r);
                    var closed = IsClosed(st);
                    if (closed && closedLeft == 0) { closedSkipped++; continue; }
                    if (r.Item1 == null || r.Item2 == null)
                    {
                        skipped++;
                        if (st == "new" || st == "active") skippedOpen++;
                        continue;
                    }
                    var a = Describe(d, r.Item1); var b = Describe(d, r.Item2);
                    clashes.Add(new Dictionary<string, object> {
                        { "id", r.Guid.ToString() }, { "test", t.DisplayName }, { "name", r.DisplayName },
                        { "status", st }, { "kind", Kind(t) }, { "distance", Metres(d, r.Distance) },
                        { "point", new object[] { Metres(d, r.Center.X), Metres(d, r.Center.Y), Metres(d, r.Center.Z) } },
                        { "a", a }, { "b", b }, { "level", a["level"] } });
                    if (closed) { closedDescribed++; if (closedLeft > 0) closedLeft--; }
                }
                var growthMb = (PrivateBytes() - _pageBaseline) / (1024 * 1024);
                return new Dictionary<string, object> {
                    { "test", new Dictionary<string, object> {
                        { "name", t.DisplayName }, { "kind", Kind(t) }, { "status", TestStatus(t) },
                        { "tolerance", Metres(d, t.Tolerance) }, { "count", items.Count } } },
                    { "clashes", clashes }, { "next", i < items.Count ? (object)i : null },
                    { "total", items.Count }, { "open_total", _page.Open }, { "closed_total", _page.Closed },
                    { "skipped", skipped }, { "skipped_open", skippedOpen },
                    { "closed_skipped", closedSkipped }, { "closed_described", closedDescribed },
                    { "memory_growth_mb", growthMb }, { "stop", stop } };
            }, 60000);
        }

        public object ClashRelease()
        {
            return UiThread.Run<object>(() =>
            {
                _page = null; OrientedCache.Clear(); OrientedStatus.Clear();
                return new Dictionary<string, object> { { "released", true } };
            });
        }
    }
}
