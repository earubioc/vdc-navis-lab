// DRAFT, not compiled. In-memory job table for operations that outlive one request.
using System;
using System.Collections.Generic;
using System.Linq;

namespace VdcNavisLab.Addin
{
    internal sealed class Jobs
    {
        public sealed class Job
        {
            private readonly object _gate = new object();
            public string Id { get; private set; }
            public string Kind { get; private set; }
            public string State { get; private set; }
            public object Result { get; private set; }
            public string Error { get; private set; }
            public bool Cancelled { get { lock (_gate) return State == "cancelled"; } }

            public Job(string kind) { Id = "job-" + Guid.NewGuid().ToString("N").Substring(0, 8); Kind = kind; State = "running"; Error = ""; }

            public void Finish(string state, object result, string error)
            {
                lock (_gate) { if (State == "cancelled") return; State = state; Result = result; Error = error ?? ""; }
            }

            public void Cancel() { lock (_gate) { if (State == "running") State = "cancelled"; } }

            public Dictionary<string, object> Status()
            {
                lock (_gate)
                    return new Dictionary<string, object> {
                        { "job_id", Id }, { "kind", Kind }, { "state", State }, { "error", Error },
                        { "progress", new Dictionary<string, object> { { "kind", "indeterminate" } } } };
            }
        }

        private readonly Dictionary<string, Job> _jobs = new Dictionary<string, Job>();

        public Job Create(string kind)
        {
            lock (_jobs)
            {
                if (_jobs.Count > 20)  // keep the table small: drop the oldest finished jobs
                    foreach (var k in _jobs.Where(kv => kv.Value.State != "running").Select(kv => kv.Key).Take(_jobs.Count - 20).ToList()) _jobs.Remove(k);
                var j = new Job(kind);
                _jobs[j.Id] = j;
                return j;
            }
        }

        public Job Get(Dictionary<string, object> p)
        {
            object id;
            Job j;
            lock (_jobs)
                if (p == null || !p.TryGetValue("job_id", out id) || !_jobs.TryGetValue(Convert.ToString(id), out j))
                    throw new RpcException("not_found", "unknown job");
                else return j;
        }

        public List<object> All() { lock (_jobs) return _jobs.Values.Select(j => (object)j.Status()).ToList(); }
    }
}
