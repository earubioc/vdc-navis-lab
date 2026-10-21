// DRAFT, not compiled. Entry point: loads with Navisworks, starts the pipe server, stops it on exit.
using System;
using System.Threading;
using Autodesk.Navisworks.Api.Plugins;

namespace VdcNavisLab.Addin
{
    [Plugin("VdcNavisLab.Watcher", "VDCL", DisplayName = "vdc-navis-lab bridge")]
    public class Watcher : EventWatcherPlugin
    {
        private PipeServer _server;

        public override void OnLoaded()
        {
            // OnLoaded runs on the Navisworks UI thread: this context is how every request gets back to it.
            UiThread.Capture(SynchronizationContext.Current);
            _server = new PipeServer("vdc-navis-lab." + System.Diagnostics.Process.GetCurrentProcess().Id, new Dispatcher());
            _server.Start();
        }

        public override void OnUnloading()
        {
            if (_server != null) _server.Stop();
            _server = null;
        }
    }

    /// <summary>Runs a function on the Navisworks UI thread and waits for it. The API is single-threaded.</summary>
    internal static class UiThread
    {
        private static SynchronizationContext _ctx;

        public static void Capture(SynchronizationContext ctx) { _ctx = ctx; }

        public static T Run<T>(Func<T> work, int timeoutMs = 30000)
        {
            if (_ctx == null) throw new RpcException("internal", "UI thread context not captured");
            T result = default(T);
            Exception error = null;
            using (var done = new ManualResetEventSlim(false))
            {
                _ctx.Post(_ =>
                {
                    try { result = work(); }
                    catch (Exception ex) { error = ex; }
                    finally { done.Set(); }
                }, null);
                if (!done.Wait(timeoutMs))
                    throw new RpcException("busy", "Navisworks UI thread is busy (a dialog may be open)", "close open dialogs and retry");
            }
            if (error is RpcException) throw error;
            if (error != null) throw new RpcException("internal", error.GetType().Name + ": " + error.Message);
            return result;
        }
    }
}
