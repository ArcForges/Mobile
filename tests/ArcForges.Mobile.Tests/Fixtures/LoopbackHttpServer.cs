// SPDX-License-Identifier: Apache-2.0
using System.Globalization;
using System.Net;
using System.Net.Sockets;
using System.Text;

namespace ArcForges.Mobile.Tests.Fixtures;

/// <summary>
/// A minimal HTTP/1.1 server on 127.0.0.1 for scripted gRPC-Web exchanges. Each request is recorded before the
/// handler runs, so tests can assert what the client sent, including requests that were never answered. Handlers
/// control the status line, chunked or length-delimited framing, truncation and abrupt aborts, which a higher-level
/// server would hide.
/// </summary>
internal sealed class LoopbackHttpServer : IAsyncDisposable
{
    private const int MaximumHeadBytes = 64 * 1024;
    private static readonly byte[] HeadEnd = "\r\n\r\n"u8.ToArray();
    private static readonly byte[] LineEnd = "\r\n"u8.ToArray();

    private readonly TcpListener _listener;
    private readonly Func<ServerExchange, Task> _handler;
    private readonly CancellationTokenSource _lifetime = new();
    private readonly object _gate = new();
    private readonly List<RecordedRequest> _requests = [];
    private readonly List<TcpClient> _clients = [];
    private readonly Task _accepting;
    private int _connections;
    private int _faults;

    /// <summary>Starts the server on an ephemeral loopback port.</summary>
    public LoopbackHttpServer(Func<ServerExchange, Task> handler)
    {
        _handler = handler ?? throw new ArgumentNullException(nameof(handler));
        _listener = new TcpListener(IPAddress.Loopback, 0);
        _listener.Start();
        _accepting = AcceptLoopAsync();
    }

    /// <summary>The Hello base address, <c>http://127.0.0.1:PORT/api</c>.</summary>
    public Uri Endpoint => new($"http://127.0.0.1:{Port.ToString(CultureInfo.InvariantCulture)}/api");

    /// <summary>The bound port.</summary>
    public int Port => ((IPEndPoint)_listener.LocalEndpoint).Port;

    /// <summary>Requests received so far, in arrival order.</summary>
    public IReadOnlyList<RecordedRequest> Requests
    {
        get
        {
            lock (_gate)
            {
                return _requests.ToArray();
            }
        }
    }

    /// <summary>TCP connections accepted so far.</summary>
    public int ConnectionCount => Volatile.Read(ref _connections);

    /// <summary>Handler exceptions other than the scripted aborts. A test asserts this is zero.</summary>
    public int HandlerFaults => Volatile.Read(ref _faults);

    /// <summary>Cancelled when the server is disposed, so a stalled handler can end.</summary>
    public CancellationToken Lifetime => _lifetime.Token;

    private async Task AcceptLoopAsync()
    {
        while (!_lifetime.IsCancellationRequested)
        {
            TcpClient client;
            try
            {
                client = await _listener.AcceptTcpClientAsync(_lifetime.Token).ConfigureAwait(false);
            }
            catch (Exception failure) when (failure is OperationCanceledException or ObjectDisposedException or SocketException)
            {
                return;
            }

            lock (_gate)
            {
                _clients.Add(client);
            }

            Interlocked.Increment(ref _connections);
            _ = ServeAsync(client);
        }
    }

    private async Task ServeAsync(TcpClient client)
    {
        try
        {
            using var stream = client.GetStream();
            var reader = new ReadBuffer(stream);
            while (!_lifetime.IsCancellationRequested)
            {
                var recorded = await ReadRequestAsync(reader, _lifetime.Token).ConfigureAwait(false);
                if (recorded is null)
                {
                    return;
                }

                lock (_gate)
                {
                    _requests.Add(recorded);
                }

                var exchange = new ServerExchange(recorded, stream, _lifetime.Token);
                try
                {
                    await _handler(exchange).ConfigureAwait(false);
                }
                catch (Exception failure) when (failure is IOException or ObjectDisposedException or OperationCanceledException)
                {
                    // The scripted peer went away: the scenario under test. Not a fault.
                    exchange.Abort();
                }
                catch (Exception)
                {
                    Interlocked.Increment(ref _faults);
                    exchange.Abort();
                }

                if (exchange.Aborted || exchange.CloseAfter)
                {
                    return;
                }

                if (!await exchange.CompleteAsync().ConfigureAwait(false))
                {
                    return;
                }
            }
        }
        catch (Exception failure) when (failure is IOException or ObjectDisposedException or OperationCanceledException or SocketException)
        {
            // Connection closed by the peer or by the fixture.
        }
        finally
        {
            client.Close();
        }
    }

    private static async Task<RecordedRequest?> ReadRequestAsync(ReadBuffer reader, CancellationToken token)
    {
        var head = await reader.ReadUntilAsync(HeadEnd, MaximumHeadBytes, token).ConfigureAwait(false);
        if (head is null)
        {
            return null;
        }

        var lines = Encoding.ASCII.GetString(head).Split("\r\n", StringSplitOptions.RemoveEmptyEntries);
        if (lines.Length == 0)
        {
            return null;
        }

        var requestLine = lines[0].Split(' ');
        var headers = new List<KeyValuePair<string, string>>();
        foreach (var line in lines.Skip(1))
        {
            var separator = line.IndexOf(':', StringComparison.Ordinal);
            if (separator <= 0)
            {
                continue;
            }

            headers.Add(new KeyValuePair<string, string>(line[..separator].Trim(), line[(separator + 1)..].Trim()));
        }

        var body = await ReadBodyAsync(reader, headers, token).ConfigureAwait(false);
        return new RecordedRequest(requestLine[0], requestLine.Length > 1 ? requestLine[1] : string.Empty, headers, body);
    }

    private static async Task<byte[]> ReadBodyAsync(ReadBuffer reader, IReadOnlyList<KeyValuePair<string, string>> headers, CancellationToken token)
    {
        var transfer = FirstHeader(headers, "Transfer-Encoding");
        if (transfer is not null && transfer.Contains("chunked", StringComparison.OrdinalIgnoreCase))
        {
            var body = new MemoryStream();
            while (true)
            {
                var sizeLine = await reader.ReadUntilAsync(LineEnd, 1024, token).ConfigureAwait(false)
                    ?? throw new IOException("The request ended inside a chunk size line.");
                var text = Encoding.ASCII.GetString(sizeLine);
                var size = int.Parse(text.Split(';')[0].Trim(), NumberStyles.HexNumber, CultureInfo.InvariantCulture);
                if (size == 0)
                {
                    // Discard trailer lines up to the blank line that ends the body.
                    while (await reader.ReadUntilAsync(LineEnd, 1024, token).ConfigureAwait(false) is { Length: > 0 })
                    {
                    }

                    return body.ToArray();
                }

                var chunk = await reader.ReadExactAsync(size, token).ConfigureAwait(false)
                    ?? throw new IOException("The request ended inside a chunk.");
                body.Write(chunk);
                _ = await reader.ReadExactAsync(2, token).ConfigureAwait(false);
            }
        }

        var length = FirstHeader(headers, "Content-Length");
        if (length is null)
        {
            return [];
        }

        var count = int.Parse(length, NumberStyles.None, CultureInfo.InvariantCulture);
        return await reader.ReadExactAsync(count, token).ConfigureAwait(false)
            ?? throw new IOException("The request body was truncated.");
    }

    private static string? FirstHeader(IEnumerable<KeyValuePair<string, string>> headers, string name)
    {
        foreach (var header in headers)
        {
            if (string.Equals(header.Key, name, StringComparison.OrdinalIgnoreCase))
            {
                return header.Value;
            }
        }

        return null;
    }

    /// <summary>Stops the listener, closes every connection and waits for the accept loop.</summary>
    public async ValueTask DisposeAsync()
    {
        _lifetime.Cancel();
        _listener.Stop();
        lock (_gate)
        {
            foreach (var client in _clients)
            {
                client.Close();
            }
        }

        try
        {
            await _accepting.ConfigureAwait(false);
        }
        catch (Exception failure) when (failure is OperationCanceledException or ObjectDisposedException or SocketException)
        {
            // Expected while shutting down.
        }

        _lifetime.Dispose();
    }

    /// <summary>A byte reader over the socket that supports delimiter and exact-count reads.</summary>
    private sealed class ReadBuffer(Stream stream)
    {
        private readonly byte[] _buffer = new byte[8192];
        private int _position;
        private int _length;

        /// <summary>
        /// Reads up to and excluding <paramref name="delimiter"/>. Returns null at a clean end of stream before any
        /// byte. Throws when the stream ends mid-line or the bytes exceed <paramref name="limit"/>.
        /// </summary>
        public async Task<byte[]?> ReadUntilAsync(byte[] delimiter, int limit, CancellationToken token)
        {
            var collected = new List<byte>();
            while (true)
            {
                var next = await ReadByteAsync(token).ConfigureAwait(false);
                if (next < 0)
                {
                    return collected.Count == 0 ? null : throw new IOException("The connection closed mid-line.");
                }

                collected.Add((byte)next);
                if (collected.Count > limit)
                {
                    throw new IOException("The request head is too large.");
                }

                if (collected.Count >= delimiter.Length && EndsWith(collected, delimiter))
                {
                    return collected.GetRange(0, collected.Count - delimiter.Length).ToArray();
                }
            }
        }

        private static bool EndsWith(List<byte> collected, byte[] delimiter)
        {
            var offset = collected.Count - delimiter.Length;
            for (var index = 0; index < delimiter.Length; index++)
            {
                if (collected[offset + index] != delimiter[index])
                {
                    return false;
                }
            }

            return true;
        }

        public async Task<byte[]?> ReadExactAsync(int count, CancellationToken token)
        {
            var result = new byte[count];
            var filled = 0;
            while (filled < count)
            {
                if (_position == _length)
                {
                    _length = await stream.ReadAsync(_buffer.AsMemory(), token).ConfigureAwait(false);
                    _position = 0;
                    if (_length == 0)
                    {
                        return null;
                    }
                }

                var take = Math.Min(count - filled, _length - _position);
                Array.Copy(_buffer, _position, result, filled, take);
                _position += take;
                filled += take;
            }

            return result;
        }

        private async Task<int> ReadByteAsync(CancellationToken token)
        {
            if (_position == _length)
            {
                _length = await stream.ReadAsync(_buffer.AsMemory(), token).ConfigureAwait(false);
                _position = 0;
                if (_length == 0)
                {
                    return -1;
                }
            }

            return _buffer[_position++];
        }
    }
}

/// <summary>One request as the server received it.</summary>
internal sealed record RecordedRequest(string Method, string Target, IReadOnlyList<KeyValuePair<string, string>> Headers, byte[] Body)
{
    /// <summary>The first value of a header, compared case-insensitively, or null.</summary>
    public string? Header(string name)
    {
        foreach (var header in Headers)
        {
            if (string.Equals(header.Key, name, StringComparison.OrdinalIgnoreCase))
            {
                return header.Value;
            }
        }

        return null;
    }

    /// <summary>Every value of a header, in order.</summary>
    public IReadOnlyList<string> HeaderValues(string name) =>
        Headers.Where(header => string.Equals(header.Key, name, StringComparison.OrdinalIgnoreCase)).Select(header => header.Value).ToArray();
}

/// <summary>The handler's view of one exchange: write the response head, then the body, then let the server close it.</summary>
internal sealed class ServerExchange(RecordedRequest request, Stream stream, CancellationToken lifetime)
{
    private bool _chunked;
    private long _declared = -1;
    private long _written;
    private bool _headWritten;

    /// <summary>The request that this exchange answers.</summary>
    public RecordedRequest Request { get; } = request;

    /// <summary>True after <see cref="Abort"/>. The connection is closed without a complete response.</summary>
    public bool Aborted { get; private set; }

    /// <summary>True when the response asks the client to close the connection after it.</summary>
    public bool CloseAfter { get; set; }

    /// <summary>The server lifetime token, so a stalled handler ends when the test ends.</summary>
    public CancellationToken Lifetime => lifetime;

    /// <summary>Writes the status line and headers. A null content length selects chunked framing.</summary>
    public async Task StartAsync(int status, long? contentLength, params (string Name, string Value)[] headers)
    {
        if (_headWritten)
        {
            throw new InvalidOperationException("The response head is already written.");
        }

        _headWritten = true;
        _chunked = contentLength is null;
        _declared = contentLength ?? -1;
        var builder = new StringBuilder();
        builder.Append("HTTP/1.1 ").Append(status.ToString(CultureInfo.InvariantCulture)).Append(' ').Append(ReasonPhrase(status)).Append("\r\n");
        foreach (var (name, value) in headers)
        {
            builder.Append(name).Append(": ").Append(value).Append("\r\n");
        }

        if (_chunked)
        {
            builder.Append("Transfer-Encoding: chunked\r\n");
        }
        else
        {
            builder.Append("Content-Length: ").Append(contentLength!.Value.ToString(CultureInfo.InvariantCulture)).Append("\r\n");
        }

        builder.Append("\r\n");
        await WriteRawAsync(Encoding.ASCII.GetBytes(builder.ToString())).ConfigureAwait(false);
    }

    /// <summary>Writes body bytes. Chunked framing is added when the head selected it.</summary>
    public async Task WriteAsync(ReadOnlyMemory<byte> data)
    {
        if (!_headWritten)
        {
            throw new InvalidOperationException("Start the response before writing its body.");
        }

        if (_chunked)
        {
            if (data.Length == 0)
            {
                return;
            }

            var prefix = Encoding.ASCII.GetBytes(data.Length.ToString("X", CultureInfo.InvariantCulture) + "\r\n");
            await WriteRawAsync(prefix).ConfigureAwait(false);
            await WriteRawAsync(data).ConfigureAwait(false);
            await WriteRawAsync("\r\n"u8.ToArray()).ConfigureAwait(false);
        }
        else
        {
            _written += data.Length;
            await WriteRawAsync(data).ConfigureAwait(false);
        }
    }

    /// <summary>Writes a complete length-delimited response.</summary>
    public async Task ReplyAsync(int status, ReadOnlyMemory<byte> body, params (string Name, string Value)[] headers)
    {
        await StartAsync(status, body.Length, headers).ConfigureAwait(false);
        await WriteAsync(body).ConfigureAwait(false);
    }

    /// <summary>
    /// Waits until the client closes its side of the connection. Returns true when the close was observed before
    /// <paramref name="timeout"/>; false otherwise. Used to prove that a cancelled call released the socket.
    /// </summary>
    public async Task<bool> WaitForPeerCloseAsync(TimeSpan timeout)
    {
        using var bound = CancellationTokenSource.CreateLinkedTokenSource(lifetime);
        bound.CancelAfter(timeout);
        var scratch = new byte[256];
        try
        {
            while (true)
            {
                var read = await stream.ReadAsync(scratch.AsMemory(), bound.Token).ConfigureAwait(false);
                if (read == 0)
                {
                    return true;
                }
            }
        }
        catch (IOException)
        {
            // The peer reset the connection: it is gone.
            return true;
        }
        catch (OperationCanceledException)
        {
            // The timeout or the server lifetime ended the wait before the peer closed.
            return false;
        }
    }

    /// <summary>Closes the connection now, with no further bytes. Used for drops and truncation.</summary>
    public void Abort()
    {
        Aborted = true;
        try
        {
            stream.Close();
        }
        catch (IOException)
        {
            // Already closed by the peer.
        }
    }

    /// <summary>
    /// Finishes the response after the handler returns. Returns false when the connection must close: a
    /// length-delimited body was shorter than declared, or the exchange was aborted.
    /// </summary>
    internal async Task<bool> CompleteAsync()
    {
        if (Aborted)
        {
            return false;
        }

        if (!_headWritten)
        {
            // A handler that wrote nothing gets an empty success, so the client cannot hang on a silent exchange.
            await StartAsync(200, 0).ConfigureAwait(false);
        }

        if (_chunked)
        {
            await WriteRawAsync("0\r\n\r\n"u8.ToArray()).ConfigureAwait(false);
            return true;
        }

        return _written == _declared;
    }

    private async Task WriteRawAsync(ReadOnlyMemory<byte> bytes)
    {
        try
        {
            await stream.WriteAsync(bytes, lifetime).ConfigureAwait(false);
            await stream.FlushAsync(lifetime).ConfigureAwait(false);
        }
        catch (IOException)
        {
            Aborted = true;
            throw;
        }
    }

    private static string ReasonPhrase(int status) => status switch
    {
        200 => "OK",
        302 => "Found",
        404 => "Not Found",
        _ => "Status",
    };
}
