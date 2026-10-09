// SPDX-License-Identifier: Apache-2.0
using ArcForges.Mobile.Network;

namespace ArcForges.Mobile;

/// <summary>
/// Holds the Hello client for the view-model (AND.40 unit 4). The window releases the client when it is destroyed, as
/// the Kotlin activity closed its client in onDestroy. The next call in the same process creates a new client, so the
/// view-model keeps working after the window is recreated.
/// </summary>
public sealed class HelloConnection : IDisposable
{
    private readonly Uri _endpoint;
    private readonly object _gate = new();
    private CloudHelloClient? _client;

    /// <summary>Creates the holder for the Cloud Hello endpoint. It opens nothing until the first call.</summary>
    public HelloConnection(Uri endpoint)
    {
        _endpoint = endpoint ?? throw new ArgumentNullException(nameof(endpoint));
    }

    /// <summary>Sends one Hello call through the current client, creating the client when none is held.</summary>
    public Task<string> SayHelloAsync(string name, CancellationToken cancellationToken)
    {
        CloudHelloClient client;
        lock (_gate)
        {
            _client ??= new CloudHelloClient(_endpoint);
            client = _client;
        }

        return client.SayHelloAsync(name, cancellationToken);
    }

    /// <summary>Cancels in-flight calls and releases the client. Safe to call more than once.</summary>
    public void Release()
    {
        CloudHelloClient? released;
        lock (_gate)
        {
            released = _client;
            _client = null;
        }

        released?.Dispose();
    }

    /// <inheritdoc />
    public void Dispose() => Release();
}
