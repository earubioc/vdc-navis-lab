// JSON-RPC 2.0 envelope and method dispatch. Wire format: docs/PROTOCOL.md.
using System;
using System.Collections.Generic;
using System.Web.Script.Serialization;

namespace VdcNavisLab.Addin
{
    internal sealed class RpcException : Exception
    {
        public string Code { get; private set; }
        public string Hint { get; private set; }
        public RpcException(string code, string message, string hint = "") : base(message) { Code = code; Hint = hint; }
    }

    internal static class Rpc
    {
        private static readonly JavaScriptSerializer Json = new JavaScriptSerializer { MaxJsonLength = int.MaxValue, RecursionLimit = 64 };

        public static Dictionary<string, object> Parse(string line)
        {
            return Json.Deserialize<Dictionary<string, object>>(line);
        }

        public static string Result(object id, object result)
        {
            return Json.Serialize(new Dictionary<string, object> { { "jsonrpc", "2.0" }, { "id", id }, { "result", result } });
        }

        public static string Error(object id, string code, string message, string hint = "")
        {
            var data = new Dictionary<string, object> { { "code", code } };
            if (!string.IsNullOrEmpty(hint)) data["hint"] = hint;
            return Json.Serialize(new Dictionary<string, object>
            {
                { "jsonrpc", "2.0" }, { "id", id },
                { "error", new Dictionary<string, object> { { "code", -32000 }, { "message", message }, { "data", data } } }
            });
        }
    }

    internal sealed class Dispatcher
    {
        private readonly Handlers _h = new Handlers();

        // Methods the Python server may call. Anything not listed answers "unsupported", and hello says so.
        private readonly Dictionary<string, Func<Dictionary<string, object>, object>> _methods;

        public Dispatcher()
        {
            _methods = new Dictionary<string, Func<Dictionary<string, object>, object>>
            {
                { "hello", p => _h.Hello(Names()) },
                { "doc.info", p => _h.DocInfo() },
                { "doc.sample", p => _h.Sample(p) },
                { "clash.tests", p => _h.ClashTests() },
                { "clash.export", p => _h.StartExport(p) },
                { "clash.apply", p => _h.ClashApply(p) },
                { "doc.save", p => _h.DocSave(p) },
                { "job.status", p => _h.JobStatus(p) },
                { "job.result", p => _h.JobResult(p) },
                { "job.cancel", p => _h.JobCancel(p) },
                { "job.list", p => _h.JobList() },
                // Not implemented in 0.1: model.census, elements.query, clash.run
            };
        }

        private string[] Names() { var a = new string[_methods.Count]; _methods.Keys.CopyTo(a, 0); Array.Sort(a); return a; }

        public string Handle(string line)
        {
            object id = null;
            try
            {
                var msg = Rpc.Parse(line);
                msg.TryGetValue("id", out id);
                var method = msg.ContainsKey("method") ? msg["method"] as string : null;
                var p = msg.ContainsKey("params") ? msg["params"] as Dictionary<string, object> : null;
                Func<Dictionary<string, object>, object> fn;
                if (method == null || !_methods.TryGetValue(method, out fn))
                    return Rpc.Error(id, "unsupported", "unknown method " + method, "call hello for the method list");
                return Rpc.Result(id, fn(p ?? new Dictionary<string, object>()));
            }
            catch (RpcException ex) { return Rpc.Error(id, ex.Code, ex.Message, ex.Hint); }
            catch (ArgumentException) { return Rpc.Error(id, "invalid_params", "malformed request"); }
            catch (InvalidOperationException) { return Rpc.Error(id, "invalid_params", "malformed request"); }
            catch (Exception ex) { return Rpc.Error(id, "internal", ex.GetType().Name); }  // never echo model data in errors
        }
    }
}
