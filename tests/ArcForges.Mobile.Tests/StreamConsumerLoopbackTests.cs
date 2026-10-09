// SPDX-License-Identifier: Apache-2.0
using System.Diagnostics;
using ArcForges.Contracts.Events.V1;
using ArcForges.Mobile.Network;
using ArcForges.Mobile.Tests.Fixtures;
using Grpc.Core;
using Grpc.Net.Client;

namespace ArcForges.Mobile.Tests;

/// <summary>
/// The streaming matrix over the shipped transport (AND.40): EventService.Watch, the stream shape of the
/// ArcForges.Contracts.Events package, against loopback fixtures. The stream producer is not reached; CLOUD.29 confirms
/// the real stream later (migration brief, AND.40 completion edges).
/// </summary>
public sealed class StreamConsumerLoopbackTests
{
    private const string WatchPath = "/api/arcforges.events.v1.EventService/Watch";
    private static readonly TimeSpan Bound = TimeSpan.FromSeconds(20);
    private static readonly (string Name, string Value) ProtoContentType = ("Content-Type", "application/grpc-web+proto");

    private static byte[] WireFrame(int index) =>
        GrpcWebFrames.Message(new StreamFrame { Position = new StreamPosition { Sequence = (ulong)index } });

    private static AsyncServerStreamingCall<StreamFrame> Watch(GrpcChannel channel, TimeSpan deadline) =>
        new EventService.EventServiceClient(channel).Watch(
            new EventServiceWatchRequest(),
            CloudHelloTransport.CreateCallOptions(deadline, CancellationToken.None));

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
    public async Task OrderedFramesThenOneOkTrailerCompleteOverTheWire()
    {
        await using var server = new LoopbackHttpServer(async exchange =>
        {
            await exchange.StartAsync(200, null, ProtoContentType);
            await exchange.WriteAsync(WireFrame(1));
            await exchange.WriteAsync(WireFrame(2));
            await exchange.WriteAsync(WireFrame(3));
            await exchange.WriteAsync(GrpcWebFrames.Trailers("grpc-status: 0", "x-proof-cursor: 3"));
        });
        using var channel = CloudHelloTransport.CreateChannel(server.Endpoint);

        var (sequences, failure) = await Drain(ServerStreamConsumer.ReadAsync(Watch(channel, TimeSpan.FromSeconds(5))))
            .WaitAsync(Bound);

        Assert.Null(failure);
        Assert.Equal(new ulong[] { 1, 2, 3 }, sequences);
        var request = Assert.Single(server.Requests);
        Assert.Equal("POST", request.Method);
        Assert.Equal(WatchPath, request.Target);
        Assert.Equal(CloudHelloTransport.RequestMediaType, request.Header("Content-Type"));
        Assert.Matches("^[0-9]{1,8}[HMSmun]$", request.Header("grpc-timeout") ?? string.Empty);
        Assert.Equal(0, server.HandlerFaults);
    }

    [Theory]
    [InlineData(7)]
    [InlineData(16)]
    [InlineData(9)]
    [InlineData(5)]
    [InlineData(8)]
    [InlineData(4)]
    [InlineData(14)]
    public async Task ErrorTrailerAfterFramesKeepsFramesStatusAndMetadata(int code)
    {
        await using var server = new LoopbackHttpServer(async exchange =>
        {
            await exchange.StartAsync(200, null, ProtoContentType);
            await exchange.WriteAsync(WireFrame(1));
            await exchange.WriteAsync(GrpcWebFrames.Trailers(
                $"grpc-status: {code}",
                "grpc-message: refused",
                "x-proof-scope: stale"));
        });
        using var channel = CloudHelloTransport.CreateChannel(server.Endpoint);

        var (sequences, failure) = await Drain(ServerStreamConsumer.ReadAsync(Watch(channel, TimeSpan.FromSeconds(5))))
            .WaitAsync(Bound);

        Assert.Equal(new ulong[] { 1 }, sequences);
        var rpc = Assert.IsType<RpcException>(failure);
        Assert.Equal((StatusCode)code, rpc.StatusCode);
        Assert.Equal("refused", rpc.Status.Detail);
        Assert.Equal("stale", rpc.Trailers.GetValue("x-proof-scope"));
    }

    [Fact]
    public async Task StreamEndedWithoutATrailerIsDataLossAfterItsFrames()
    {
        await using var server = new LoopbackHttpServer(async exchange =>
        {
            await exchange.StartAsync(200, null, ProtoContentType);
            await exchange.WriteAsync(WireFrame(1));
            await exchange.WriteAsync(WireFrame(2));
            // The chunked body ends cleanly without the mandatory status trailer.
        });
        using var channel = CloudHelloTransport.CreateChannel(server.Endpoint);

        var (sequences, failure) = await Drain(ServerStreamConsumer.ReadAsync(Watch(channel, TimeSpan.FromSeconds(5))))
            .WaitAsync(Bound);

        Assert.Equal(new ulong[] { 1, 2 }, sequences);
        Assert.Equal(StatusCode.DataLoss, Assert.IsType<RpcException>(failure).StatusCode);
    }

    [Fact]
    public async Task DuplicatedStatusTrailerIsDataLossAfterItsFrames()
    {
        await using var server = new LoopbackHttpServer(async exchange =>
        {
            await exchange.StartAsync(200, null, ProtoContentType);
            await exchange.WriteAsync(WireFrame(1));
            await exchange.WriteAsync(GrpcWebFrames.Trailers("grpc-status: 0", "grpc-status: 0"));
        });
        using var channel = CloudHelloTransport.CreateChannel(server.Endpoint);

        var (sequences, failure) = await Drain(ServerStreamConsumer.ReadAsync(Watch(channel, TimeSpan.FromSeconds(5))))
            .WaitAsync(Bound);

        Assert.Equal(new ulong[] { 1 }, sequences);
        Assert.Equal(StatusCode.DataLoss, Assert.IsType<RpcException>(failure).StatusCode);
    }

    [Fact]
    public async Task ConnectionLostMidStreamKeepsReceivedFramesAndIsDataLoss()
    {
        await using var server = new LoopbackHttpServer(async exchange =>
        {
            // Declare far more body than is sent, then drop the connection.
            await exchange.StartAsync(200, 100_000, ProtoContentType);
            await exchange.WriteAsync(WireFrame(1));
            exchange.Abort();
        });
        using var channel = CloudHelloTransport.CreateChannel(server.Endpoint);

        var (sequences, failure) = await Drain(ServerStreamConsumer.ReadAsync(Watch(channel, TimeSpan.FromSeconds(5))))
            .WaitAsync(Bound);

        Assert.Equal(new ulong[] { 1 }, sequences);
        Assert.Equal(StatusCode.DataLoss, Assert.IsType<RpcException>(failure).StatusCode);
    }

    [Fact]
    public async Task DeadlineMidStreamKeepsFramesAndFailsWithDeadlineExceeded()
    {
        var peerClosed = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        await using var server = new LoopbackHttpServer(async exchange =>
        {
            await exchange.StartAsync(200, null, ProtoContentType);
            await exchange.WriteAsync(WireFrame(1));
            peerClosed.TrySetResult(await exchange.WaitForPeerCloseAsync(TimeSpan.FromSeconds(15)));
        });
        using var channel = CloudHelloTransport.CreateChannel(server.Endpoint);

        var clock = Stopwatch.StartNew();
        var (sequences, failure) = await Drain(ServerStreamConsumer.ReadAsync(Watch(channel, TimeSpan.FromMilliseconds(500))))
            .WaitAsync(Bound);
        clock.Stop();

        Assert.Equal(new ulong[] { 1 }, sequences);
        Assert.Equal(StatusCode.DeadlineExceeded, Assert.IsType<RpcException>(failure).StatusCode);
        Assert.True(clock.Elapsed < TimeSpan.FromSeconds(5), $"The stream lasted {clock.Elapsed}.");
        Assert.True(await peerClosed.Task.WaitAsync(Bound), "The deadline must release the stream.");
    }

    [Fact]
    public async Task CallerCancellationReleasesTheStreamAndTheServerSeesTheClose()
    {
        var peerClosed = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        await using var server = new LoopbackHttpServer(async exchange =>
        {
            await exchange.StartAsync(200, null, ProtoContentType);
            await exchange.WriteAsync(WireFrame(1));
            peerClosed.TrySetResult(await exchange.WaitForPeerCloseAsync(TimeSpan.FromSeconds(15)));
        });
        using var channel = CloudHelloTransport.CreateChannel(server.Endpoint);
        using var cancellation = new CancellationTokenSource();
        var enumerator = ServerStreamConsumer.ReadAsync(Watch(channel, TimeSpan.FromSeconds(5)), cancellation.Token)
            .GetAsyncEnumerator();
        try
        {
            Assert.True(await enumerator.MoveNextAsync().AsTask().WaitAsync(Bound));
            Assert.Equal(1UL, enumerator.Current.Position.Sequence);

            cancellation.Cancel();

            await Assert.ThrowsAnyAsync<OperationCanceledException>(() => enumerator.MoveNextAsync().AsTask()).WaitAsync(Bound);
            Assert.True(await peerClosed.Task.WaitAsync(Bound), "The cancelled stream must close its connection.");
        }
        finally
        {
            await enumerator.DisposeAsync();
        }
    }
}
