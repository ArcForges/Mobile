// SPDX-License-Identifier: Apache-2.0
using ArcForges.Contracts.Hello.V1;
using Grpc.Core;
using Grpc.Net.Client;

namespace ArcForges.Mobile.Network;

/// <summary>
/// Activity-owned Hello client (AND.40). Creating the client opens no connection and sends no RPC. Each
/// <see cref="SayHelloAsync"/> call is bounded by a deadline of at most 5 s and a call timeout of 10 s, and is
/// sent once.
/// </summary>
public sealed class CloudHelloClient : IAsyncDisposable, IDisposable
{
    /// <summary>The name length limit, counted in UTF-16 code units exactly as the Kotlin client counts it.</summary>
    public const int MaximumNameLength = 256;

    private readonly GrpcChannel _channel;
    private readonly HelloService.HelloServiceClient _service;
    private readonly TimeSpan _deadline;
    private readonly CancellationTokenSource _lifetime = new();
    private int _disposed;

    /// <summary>Creates the client for the endpoint, with the per-call deadline (at most 5 s).</summary>
    public CloudHelloClient(Uri endpoint, TimeSpan? deadline = null)
    {
        _deadline = deadline ?? CloudHelloTransport.MaximumDeadline;
        if (_deadline <= TimeSpan.Zero || _deadline > CloudHelloTransport.MaximumDeadline)
        {
            throw new ArgumentOutOfRangeException(nameof(deadline), "The call deadline must be positive and at most 5 seconds.");
        }

        _channel = CloudHelloTransport.CreateChannel(endpoint);
        _service = new HelloService.HelloServiceClient(_channel);
    }

    /// <summary>The unary call, returning the greeting text. Failures are <see cref="CloudHelloException"/>.</summary>
    /// <exception cref="ArgumentOutOfRangeException">The name is not 1 to 256 characters. Nothing is sent.</exception>
    /// <exception cref="CloudHelloException">The call failed. The message is the user-facing text.</exception>
    /// <exception cref="OperationCanceledException">The caller cancelled the call.</exception>
    public async Task<string> SayHelloAsync(string name, CancellationToken cancellationToken = default)
    {
        ValidateName(name);
        ObjectDisposedException.ThrowIf(Volatile.Read(ref _disposed) != 0, this);

        using var callTimeout = new CancellationTokenSource(CloudHelloTransport.CallTimeout);
        using var linked = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken, callTimeout.Token, _lifetime.Token);
        var options = CloudHelloTransport.CreateCallOptions(_deadline, linked.Token);
        using var call = _service.SayHelloAsync(new SayHelloRequest { Name = name }, options);
        try
        {
            var response = await call.ResponseAsync.ConfigureAwait(false);
            return response.Message;
        }
        catch (RpcException failure)
        {
            throw Translate(failure, cancellationToken, callTimeout, _lifetime);
        }
    }

    /// <summary>Validates the name rule of the Kotlin client: 1 to 256 characters, no trimming.</summary>
    public static void ValidateName(string name)
    {
        ArgumentNullException.ThrowIfNull(name);
        if (name.Length is < 1 or > MaximumNameLength)
        {
            throw new ArgumentOutOfRangeException(nameof(name), "Use a name with 1 to 256 characters.");
        }
    }

    /// <summary>
    /// Maps a gRPC status to the user-facing text. Matches the Kotlin client's table; any other status is the
    /// generic connection message.
    /// </summary>
    public static string UserMessageFor(StatusCode code) => code switch
    {
        StatusCode.InvalidArgument => "Cloud rejected this name. Check it and try again.",
        StatusCode.ResourceExhausted => "Cloud's request limit was reached. Try again later.",
        StatusCode.DeadlineExceeded => "Cloud did not respond in time. Try again.",
        StatusCode.Cancelled => "The request was canceled. Try again.",
        _ => "Could not reach Cloud. Check your connection and try again.",
    };

    private static Exception Translate(
        RpcException failure,
        CancellationToken caller,
        CancellationTokenSource callTimeout,
        CancellationTokenSource lifetime)
    {
        if (caller.IsCancellationRequested)
        {
            // The caller chose to stop. Surface it as cancellation, as a coroutine cancellation is surfaced in Kotlin.
            return new OperationCanceledException("The Hello call was canceled by the caller.", failure, caller);
        }

        if (callTimeout.IsCancellationRequested && !lifetime.IsCancellationRequested)
        {
            // The 10 s call timeout ended the call before the server answered.
            return new CloudHelloException(StatusCode.DeadlineExceeded, UserMessageFor(StatusCode.DeadlineExceeded), failure);
        }

        var status = GrpcFailureClassifier.Classify(failure).StatusCode;
        return new CloudHelloException(status, UserMessageFor(status), failure);
    }

    /// <summary>Cancels in-flight calls and releases the connection pool. Safe to call more than once.</summary>
    public void Dispose()
    {
        if (Interlocked.Exchange(ref _disposed, 1) != 0)
        {
            return;
        }

        _lifetime.Cancel();
        _channel.Dispose();
        _lifetime.Dispose();
    }

    /// <summary>
    /// Cancels in-flight calls, then shuts the channel down without blocking the caller. Use this from UI code;
    /// socket close and TLS close_notify may do I/O.
    /// </summary>
    public async ValueTask DisposeAsync()
    {
        if (Interlocked.Exchange(ref _disposed, 1) != 0)
        {
            return;
        }

        _lifetime.Cancel();
        await _channel.ShutdownAsync().ConfigureAwait(false);
        _channel.Dispose();
        _lifetime.Dispose();
    }
}
