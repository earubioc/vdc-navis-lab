// Named pipe, current user only, one JSON-RPC request per connection.
using System;
using System.IO;
using System.IO.Pipes;
using System.Security.AccessControl;
using System.Security.Principal;
using System.Text;
using System.Threading;

namespace VdcNavisLab.Addin
{
    internal sealed class PipeServer
    {
        private const int MaxLine = 64 * 1024 * 1024;
        private readonly string _name;
        private readonly Dispatcher _dispatcher;
        private volatile bool _stop;
        private Thread _thread;

        public PipeServer(string name, Dispatcher dispatcher) { _name = name; _dispatcher = dispatcher; }

        public void Start()
        {
            _thread = new Thread(Loop) { IsBackground = true, Name = "vdc-navis-lab pipe" };
            _thread.Start();
        }

        public void Stop()
        {
            _stop = true;
            try { using (var poke = new NamedPipeClientStream(".", _name, PipeDirection.InOut)) poke.Connect(200); } catch { }
        }

        private PipeSecurity CurrentUserOnly()
        {
            var sec = new PipeSecurity();
            var me = WindowsIdentity.GetCurrent().User;
            sec.AddAccessRule(new PipeAccessRule(me, PipeAccessRights.ReadWrite, AccessControlType.Allow));
            return sec;
        }

        private void Loop()
        {
            while (!_stop)
            {
                NamedPipeServerStream pipe = null;
                try
                {
                    pipe = new NamedPipeServerStream(_name, PipeDirection.InOut, NamedPipeServerStream.MaxAllowedServerInstances,
                        PipeTransmissionMode.Byte, PipeOptions.None, 0, 0, CurrentUserOnly());
                    pipe.WaitForConnection();
                    if (_stop) break;
                    var captured = pipe;
                    pipe = null;  // ownership moves to the worker
                    new Thread(() => Serve(captured)) { IsBackground = true }.Start();
                }
                catch (IOException) { Thread.Sleep(100); }
                finally { if (pipe != null) pipe.Dispose(); }
            }
        }

        private void Serve(NamedPipeServerStream pipe)
        {
            using (pipe)
            {
                byte[] reply;
                try
                {
                    string line = ReadLine(pipe);
                    reply = Encoding.UTF8.GetBytes(_dispatcher.Handle(line) + "\n");
                }
                catch (Exception ex)
                {
                    reply = Encoding.UTF8.GetBytes(Rpc.Error(null, "internal", ex.GetType().Name) + "\n");
                }
                try
                {
                    pipe.Write(reply, 0, reply.Length);
                    pipe.Flush();
                    pipe.WaitForPipeDrain();
                    pipe.Disconnect();
                }
                catch (IOException) { }
            }
        }

        private static string ReadLine(Stream s)
        {
            var buf = new MemoryStream();
            var one = new byte[65536];
            while (true)
            {
                int n = s.Read(one, 0, one.Length);
                if (n <= 0) break;
                int nl = Array.IndexOf(one, (byte)'\n', 0, n);
                buf.Write(one, 0, nl >= 0 ? nl : n);
                if (nl >= 0 || buf.Length > MaxLine) break;
            }
            return Encoding.UTF8.GetString(buf.ToArray());
        }
    }
}
