// SPDX-License-Identifier: Apache-2.0
using ArcForges.Contracts.Events.V1;
using ArcForges.Mobile.Network;
using ArcForges.Mobile.Tests.Fixtures;
using Grpc.Core;
using static ArcForges.Mobile.Tests.Fixtures.StreamFixtures;

namespace ArcForges.Mobile.Tests;

/// <summary>
/// The streaming consumer rules (AND.40) against in-memory calls: ordered frames, exactly one OK status trailer,
/// DATA_LOSS on a missing or duplicated status, error statuses kept with their frames and metadata, bounded
/// read-ahead, and a close that is not cancelled. The loopback matrix over the real transport is in
/// <see cref="StreamConsumerLoopbackTests"/>.
/// </summary>
public sealed class StreamConsumerContractTests
{
    private static readonly TimeSpan Bound = TimeSpan.FromSeconds(20);

    private static async Task<(List<ulong> Sequences, Exception? Failure)> Drain(IAsyncEnumerable<StreamFrame> stream)
    {
        var sequences = new List<ulong>();
        try
        {
            await foreach (var frame in stream)
            {
                sequences.Add(frame.Position.Sequence);
            }

            return (sequences, null);
        }
        catch (Exception failure)
        {
            return (sequences, failure);
        }
    }

    [Fact]
    public async Task FramesArriveInOrderAndExactlyOneOkTrailerCompletesTheStream()
    {
        var disposed = 0;
        var call = Call(Finite(3), () => Status.DefaultSuccess, () => Trailers(("grpc-status", "0")), () => disposed++);

        var (sequences, failure) = await Drain(ServerStreamConsumer.ReadAsync(call)).WaitAsync(Bound);

        Assert.Null(failure);
        Assert.Equal(new ulong[] { 0, 1, 2 }, sequences);
        Assert.Equal(1, disposed);
    }

    [Fact]
    public async Task MissingStatusTrailerIsDataLossAfterTheFrames()
    {
        // The transport raises this characterised failure when the body ends without a grpc-status trailer.
        var call = Call(
            ThenFails(3, new RpcException(new Status(StatusCode.Cancelled, "No grpc-status found on response."))),
            () => Status.DefaultSuccess,
            () => new Metadata(),
            () => { });

        var (sequences, failure) = await Drain(ServerStreamConsumer.ReadAsync(call)).WaitAsync(Bound);

        Assert.Equal(new ulong[] { 0, 1, 2 }, sequences);
        var rpc = Assert.IsType<RpcException>(failure);
        Assert.Equal(StatusCode.DataLoss, rpc.StatusCode);
    }

    [Fact]
    public async Task DuplicateStatusTrailersAreDataLoss()
    {
        var call = Call(
            ThenFails(1, new RpcException(new Status(StatusCode.Cancelled, "Multiple grpc-status headers."))),
            () => Status.DefaultSuccess,
            () => new Metadata(),
            () => { });

        var (sequences, failure) = await Drain(ServerStreamConsumer.ReadAsync(call)).WaitAsync(Bound);

        Assert.Equal(new ulong[] { 0 }, sequences);
        Assert.Equal(StatusCode.DataLoss, Assert.IsType<RpcException>(failure).StatusCode);
    }

    [Fact]
    public async Task ErrorTrailerAfterFramesKeepsTheFramesStatusAndMetadata()
    {
        // The transport raises a server error status after the frames, carrying the server's detail and trailers.
        var trailers = Trailers(("x-proof-scope", "stale"));
        var call = Call(
            ThenFails(2, new RpcException(new Status(StatusCode.PermissionDenied, "refused"), trailers)),
            () => new Status(StatusCode.PermissionDenied, "refused"),
            () => trailers,
            () => { });

        var (sequences, failure) = await Drain(ServerStreamConsumer.ReadAsync(call)).WaitAsync(Bound);

        Assert.Equal(new ulong[] { 0, 1 }, sequences);
        var rpc = Assert.IsType<RpcException>(failure);
        Assert.Equal(StatusCode.PermissionDenied, rpc.StatusCode);
        Assert.Equal("refused", rpc.Status.Detail);
        Assert.Equal("stale", rpc.Trailers.GetValue("x-proof-scope"));
    }

    [Fact]
    public async Task NonOkStatusAtACleanEndIsReportedWithItsFrames()
    {
        var call = Call(
            Finite(2),
            () => new Status(StatusCode.Unavailable, "retry later"),
            () => Trailers(("x-proof-scope", "kept")),
            () => { });

        var (sequences, failure) = await Drain(ServerStreamConsumer.ReadAsync(call)).WaitAsync(Bound);

        Assert.Equal(new ulong[] { 0, 1 }, sequences);
        var rpc = Assert.IsType<RpcException>(failure);
        Assert.Equal(StatusCode.Unavailable, rpc.StatusCode);
        Assert.Equal("kept", rpc.Trailers.GetValue("x-proof-scope"));
    }

    [Fact]
    public async Task ServerDeadlineStatusAfterFramesIsNotReclassifiedAsDataLoss()
    {
        var call = Call(
            ThenFails(2, new RpcException(new Status(StatusCode.DeadlineExceeded, "late"))),
            () => Status.DefaultSuccess,
            () => new Metadata(),
            () => { });

        var (sequences, failure) = await Drain(ServerStreamConsumer.ReadAsync(call)).WaitAsync(Bound);

        Assert.Equal(new ulong[] { 0, 1 }, sequences);
        Assert.Equal(StatusCode.DeadlineExceeded, Assert.IsType<RpcException>(failure).StatusCode);
    }

    [Fact]
    public async Task BodyCutShortAfterTheResponseBeganIsDataLoss()
    {
        // The transport reports a body that ends before its declared length this way.
        var call = Call(
            ThenFails(2, new RpcException(new Status(StatusCode.Unavailable, "Error reading next message. HttpIOException: The response ended prematurely, with at least 99991 additional bytes expected. (ResponseEnded)"))),
            () => Status.DefaultSuccess,
            () => new Metadata(),
            () => { });

        var (sequences, failure) = await Drain(ServerStreamConsumer.ReadAsync(call)).WaitAsync(Bound);

        Assert.Equal(new ulong[] { 0, 1 }, sequences);
        Assert.Equal(StatusCode.DataLoss, Assert.IsType<RpcException>(failure).StatusCode);
    }

    [Fact]
    public async Task TransportFailureBeforeTheResponseBeganKeepsItsStatus()
    {
        var neverStarted = new TaskCompletionSource<Metadata>().Task;
        var call = Call(
            ThenFails(0, new RpcException(new Status(StatusCode.Unavailable, "no route"))),
            () => Status.DefaultSuccess,
            () => new Metadata(),
            () => { },
            neverStarted);

        var (sequences, failure) = await Drain(ServerStreamConsumer.ReadAsync(call)).WaitAsync(Bound);

        Assert.Empty(sequences);
        Assert.Equal(StatusCode.Unavailable, Assert.IsType<RpcException>(failure).StatusCode);
    }

    [Fact]
    public async Task ServerStatusTrailersOnAFailureArePassedThrough()
    {
        var trailers = Trailers(("grpc-status", "7"));
        var call = Call(
            ThenFails(1, new RpcException(new Status(StatusCode.PermissionDenied, "no"), trailers)),
            () => Status.DefaultSuccess,
            () => new Metadata(),
            () => { });

        var (sequences, failure) = await Drain(ServerStreamConsumer.ReadAsync(call)).WaitAsync(Bound);

        Assert.Equal(new ulong[] { 0 }, sequences);
        Assert.Equal(StatusCode.PermissionDenied, Assert.IsType<RpcException>(failure).StatusCode);
    }

    [Theory]
    [InlineData(0)]
    [InlineData(1025)]
    public void CapacityOutsideTheBoundIsRejectedWhenTheStreamIsRequested(int capacity)
    {
        var call = Call(Finite(0), () => Status.DefaultSuccess, () => Trailers(("grpc-status", "0")), () => { });

        Assert.Throws<ArgumentOutOfRangeException>(() => ServerStreamConsumer.ReadAsync(call, CancellationToken.None, capacity));
    }

    [Fact]
    public void ANullCallIsRejectedWhenTheStreamIsRequested()
    {
        Assert.Throws<ArgumentNullException>(() => ServerStreamConsumer.ReadAsync<StreamFrame>(null!));
    }

    [Fact]
    public async Task ReadAheadNeverExceedsTheCapacityPlusOneFrame()
    {
        const int Capacity = 4;
        var reader = Endless();
        var call = Call(reader, () => Status.DefaultSuccess, () => Trailers(("grpc-status", "0")), () => { });
        await using var enumerator = ServerStreamConsumer.ReadAsync(call, CancellationToken.None, Capacity).GetAsyncEnumerator();

        Assert.True(await enumerator.MoveNextAsync().AsTask().WaitAsync(Bound));
        var consumed = 1;
        await Task.Delay(200);

        // One frame is with the consumer, Capacity frames are buffered, and at most one more is held by the producer.
        Assert.InRange(reader.Pulled, consumed + Capacity, consumed + Capacity + 1);

        for (var step = 0; step < 20; step++)
        {
            Assert.True(await enumerator.MoveNextAsync().AsTask().WaitAsync(Bound));
            consumed++;
            Assert.True(reader.Pulled <= consumed + Capacity + 1, $"Pulled {reader.Pulled} frames for {consumed} consumed.");
        }
    }

    [Fact]
    public async Task AnEarlyDisposeEndsTheStreamAndDisposesTheCall()
    {
        var disposed = 0;
        var call = Call(Endless(), () => Status.DefaultSuccess, () => Trailers(("grpc-status", "0")), () => disposed++);
        await using (var enumerator = ServerStreamConsumer.ReadAsync(call).GetAsyncEnumerator())
        {
            Assert.True(await enumerator.MoveNextAsync().AsTask().WaitAsync(Bound));
            Assert.Equal(0, disposed);
        }

        Assert.Equal(1, disposed);
    }

    [Fact]
    public async Task CancellationDisposesTheCallBeforeTheCallerSeesTheCancellation()
    {
        var disposed = 0;
        var call = Call(ThenSilent(1), () => Status.DefaultSuccess, () => Trailers(("grpc-status", "0")), () => Interlocked.Increment(ref disposed));
        using var cancellation = new CancellationTokenSource();
        var enumerator = ServerStreamConsumer.ReadAsync(call, cancellation.Token).GetAsyncEnumerator();
        try
        {
            Assert.True(await enumerator.MoveNextAsync().AsTask().WaitAsync(Bound));

            cancellation.Cancel();

            await Assert.ThrowsAnyAsync<OperationCanceledException>(() => enumerator.MoveNextAsync().AsTask()).WaitAsync(Bound);
            Assert.Equal(1, Volatile.Read(ref disposed));
        }
        finally
        {
            await enumerator.DisposeAsync();
        }
    }
}
