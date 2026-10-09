// SPDX-License-Identifier: Apache-2.0
using ArcForges.Contracts.Events.V1;
using Grpc.Core;

namespace ArcForges.Mobile.Tests.Fixtures;

/// <summary>
/// An in-memory response stream. <paramref name="produce"/> receives the index of the next frame and returns it, or
/// null at the normal end. It may throw to script a transport failure. <see cref="Pulled"/> counts the frames the
/// consumer side has pulled from the stream, which is how the bounded read-ahead is observed.
/// </summary>
internal sealed class ScriptedStreamReader<T>(Func<int, CancellationToken, Task<T?>> produce) : IAsyncStreamReader<T>
    where T : class
{
    private int _pulled;

    /// <summary>Frames pulled so far.</summary>
    public int Pulled => Volatile.Read(ref _pulled);

    /// <inheritdoc />
    public T Current { get; private set; } = null!;

    /// <inheritdoc />
    public async Task<bool> MoveNext(CancellationToken cancellationToken)
    {
        var next = await produce(Pulled, cancellationToken).ConfigureAwait(false);
        if (next is null)
        {
            return false;
        }

        Current = next;
        Interlocked.Increment(ref _pulled);
        return true;
    }
}

/// <summary>Builders for the in-memory stream fixtures.</summary>
internal static class StreamFixtures
{
    /// <summary>A frame whose position carries <paramref name="index"/>, so order is checkable.</summary>
    public static StreamFrame Frame(int index) => new()
    {
        Position = new StreamPosition { Sequence = (ulong)index },
    };

    /// <summary>A finite stream of <paramref name="count"/> frames.</summary>
    public static ScriptedStreamReader<StreamFrame> Finite(int count) =>
        new((index, _) => Task.FromResult<StreamFrame?>(index < count ? Frame(index) : null));

    /// <summary>A stream that never ends and never blocks.</summary>
    public static ScriptedStreamReader<StreamFrame> Endless() =>
        new((index, _) => Task.FromResult<StreamFrame?>(Frame(index)));

    /// <summary>A stream of <paramref name="count"/> frames that then waits until the consumer cancels or disposes.</summary>
    public static ScriptedStreamReader<StreamFrame> ThenSilent(int count) =>
        new(async (index, token) =>
        {
            if (index < count)
            {
                return Frame(index);
            }

            await Task.Delay(Timeout.Infinite, token).ConfigureAwait(false);
            return null;
        });

    /// <summary>A stream of <paramref name="count"/> frames that then fails with <paramref name="failure"/>.</summary>
    public static ScriptedStreamReader<StreamFrame> ThenFails(int count, RpcException failure) =>
        new(async (index, _) =>
        {
            if (index < count)
            {
                return Frame(index);
            }

            await Task.Yield();
            throw failure;
        });

    /// <summary>A response call over the scripted stream, with the status, trailers and dispose callbacks given.</summary>
    public static AsyncServerStreamingCall<StreamFrame> Call(
        IAsyncStreamReader<StreamFrame> reader,
        Func<Status> status,
        Func<Metadata> trailers,
        Action dispose,
        Task<Metadata>? headers = null) =>
        new(reader, headers ?? Task.FromResult(new Metadata()), status, trailers, dispose);

    /// <summary>A metadata block from the given key and value pairs.</summary>
    public static Metadata Trailers(params (string Key, string Value)[] entries)
    {
        var metadata = new Metadata();
        foreach (var (key, value) in entries)
        {
            metadata.Add(key, value);
        }

        return metadata;
    }
}
