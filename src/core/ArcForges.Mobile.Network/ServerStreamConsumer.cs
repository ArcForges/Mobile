// SPDX-License-Identifier: Apache-2.0
using System.Runtime.CompilerServices;
using System.Threading.Channels;
using Grpc.Core;

namespace ArcForges.Mobile.Network;

/// <summary>
/// Consumes one server-stream call under the AND.40 streaming rules:
/// <list type="bullet">
/// <item>frames are delivered in the order the server sent them;</item>
/// <item>a stream succeeds only with its OK status trailer, which the transport reports as the call's status. A
/// missing or duplicated status trailer, and a body cut short after the response began, are
/// <see cref="StatusCode.DataLoss"/> (see <see cref="GrpcFailureClassifier"/>);</item>
/// <item>an error trailer after frames keeps the frames already delivered and fails with the server's status, detail
/// and trailers;</item>
/// <item>buffering is bounded: a producer reads ahead at most <c>capacity</c> frames and then waits;</item>
/// <item>closing is never cancelled: when the caller stops or cancels, the call is disposed and the producer is
/// awaited to completion before the enumerator finishes.</item>
/// </list>
/// A caller cancellation surfaces as <see cref="OperationCanceledException"/>. Any other failure surfaces as
/// <see cref="RpcException"/> with the status it maps to.
/// </summary>
public static class ServerStreamConsumer
{
    /// <summary>Default read-ahead, in frames.</summary>
    public const int DefaultCapacity = 8;

    /// <summary>The largest read-ahead accepted. Beyond this the buffer is no longer bounded in practice.</summary>
    public const int MaximumCapacity = 1024;

    /// <summary>
    /// Reads the frames of <paramref name="call"/> under the streaming rules above. Arguments are validated when
    /// this method is called; the producer starts on the first <c>MoveNextAsync</c>. Enumerate the result to its end or
    /// dispose the enumerator: the call is released only once enumeration has started.
    /// </summary>
    /// <param name="call">The server-stream call. The consumer owns it and disposes it.</param>
    /// <param name="cancellationToken">Cancels the stream. Cancellation disposes the call before the enumerator ends.</param>
    /// <param name="capacity">The read-ahead bound, from 1 to <see cref="MaximumCapacity"/>.</param>
    public static IAsyncEnumerable<TResponse> ReadAsync<TResponse>(
        AsyncServerStreamingCall<TResponse> call,
        CancellationToken cancellationToken = default,
        int capacity = DefaultCapacity)
        where TResponse : class
    {
        ArgumentNullException.ThrowIfNull(call);
        ArgumentOutOfRangeException.ThrowIfLessThan(capacity, 1);
        ArgumentOutOfRangeException.ThrowIfGreaterThan(capacity, MaximumCapacity);
        return ReadFramesAsync(call, cancellationToken, capacity);
    }

    private static async IAsyncEnumerable<TResponse> ReadFramesAsync<TResponse>(
        AsyncServerStreamingCall<TResponse> call,
        [EnumeratorCancellation] CancellationToken cancellationToken,
        int capacity)
        where TResponse : class
    {
        var frames = Channel.CreateBounded<TResponse>(new BoundedChannelOptions(capacity)
        {
            SingleReader = true,
            SingleWriter = true,
            FullMode = BoundedChannelFullMode.Wait,
        });

        using var stop = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        var producer = ProduceAsync(call, frames.Writer, stop.Token);
        try
        {
            // WaitToReadAsync returns false at a normal end of the channel and faults with the producer's terminal
            // error. It throws OperationCanceledException when the caller cancels while the consumer waits.
            while (await frames.Reader.WaitToReadAsync(cancellationToken).ConfigureAwait(false))
            {
                while (frames.Reader.TryRead(out var frame))
                {
                    yield return frame;
                }
            }
        }
        finally
        {
            // NonCancellable close. Stop the producer, dispose the call so the transport is released, then wait for
            // the producer without a token so that this step always completes, even after the caller cancelled.
            stop.Cancel();
            call.Dispose();
            await producer.ConfigureAwait(false);
        }
    }

    private static async Task ProduceAsync<TResponse>(
        AsyncServerStreamingCall<TResponse> call,
        ChannelWriter<TResponse> writer,
        CancellationToken token)
    {
        Exception? terminal = null;
        try
        {
            var stream = call.ResponseStream;
            while (await stream.MoveNext(token).ConfigureAwait(false))
            {
                await writer.WriteAsync(stream.Current, token).ConfigureAwait(false);
            }

            terminal = CompletionFailure(call);
        }
        catch (OperationCanceledException) when (token.IsCancellationRequested)
        {
            terminal = new OperationCanceledException("The stream was canceled by the caller.", token);
        }
        catch (RpcException failure)
        {
            terminal = FailureOf(failure, token);
        }
        catch (IOException)
        {
            terminal = new RpcException(new Status(StatusCode.Unavailable, "The stream connection failed."));
        }
        finally
        {
            writer.TryComplete(terminal);
        }
    }

    /// <summary>
    /// The verdict after the frames end normally. The transport raises its own failure when the status trailer is
    /// missing, so a normal end carries the status the server sent. Null when that status is OK.
    /// </summary>
    private static Exception? CompletionFailure<TResponse>(AsyncServerStreamingCall<TResponse> call)
    {
        var status = call.GetStatus();
        return status.StatusCode == StatusCode.OK
            ? null
            : new RpcException(status, call.GetTrailers(), status.Detail);
    }

    /// <summary>
    /// Maps a transport failure. A status the server sent is kept with its trailers. A status the transport
    /// characterises as a lost trailer, or a body cut short after the response began, is DATA_LOSS.
    /// </summary>
    private static Exception FailureOf(RpcException failure, CancellationToken token)
    {
        if (token.IsCancellationRequested)
        {
            return new OperationCanceledException("The stream was canceled by the caller.", failure, token);
        }

        var status = GrpcFailureClassifier.Classify(failure);
        return new RpcException(status, failure.Trailers, status.Detail);
    }
}
