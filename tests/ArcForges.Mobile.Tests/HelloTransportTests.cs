// SPDX-License-Identifier: Apache-2.0
using System.Diagnostics;
using ArcForges.Contracts.Hello.V1;
using ArcForges.Mobile.Network;
using ArcForges.Mobile.Tests.Fixtures;
using Grpc.Core;
using Grpc.Net.Client.Web;

namespace ArcForges.Mobile.Tests;

/// <summary>
/// The Hello unary transport matrix (AND.40): binary gRPC-Web through GrpcWebMode, no cookies, no redirects, no
/// retry, a deadline of at most 5 s, the 10 s call timeout, the grpc-timeout format, the 1 to 256 name rule and the
/// Kotlin status-to-message table. Every case runs against a loopback fixture; no service is reached.
/// </summary>
public sealed class HelloTransportTests
{
    private const string GenericMessage = "Could not reach Cloud. Check your connection and try again.";
    private static readonly TimeSpan Bound = TimeSpan.FromSeconds(20);
    private static readonly (string Name, string Value) ProtoContentType = ("Content-Type", "application/grpc-web+proto");

    private static byte[] Greeting(string name) => GrpcWebFrames.Concat(
        GrpcWebFrames.Message(new SayHelloResponse { Message = $"Hello, {name}!" }),
        GrpcWebFrames.Trailers("grpc-status: 0"));

    private static string NameOf(RecordedRequest request) =>
        SayHelloRequest.Parser.ParseFrom(GrpcWebFrames.SingleMessagePayload(request.Body)).Name;

    [Fact]
    public async Task UnarySendsOneBinaryGrpcWebRequestToTheConfiguredPath()
    {
        await using var server = new LoopbackHttpServer(async exchange =>
            await exchange.ReplyAsync(200, Greeting(NameOf(exchange.Request)), ProtoContentType));
        await using var client = new CloudHelloClient(server.Endpoint);

        var greeting = await client.SayHelloAsync(" 世界 👋 ").WaitAsync(Bound);

        Assert.Equal("Hello,  世界 👋 !", greeting);
        var request = Assert.Single(server.Requests);
        Assert.Equal("POST", request.Method);
        Assert.Equal("/api/arcforges.hello.v1.HelloService/SayHello", request.Target);
        Assert.Equal(CloudHelloTransport.RequestMediaType, request.Header("Content-Type"));
        Assert.DoesNotContain("text", request.Header("Content-Type") ?? string.Empty, StringComparison.Ordinal);
        Assert.Equal(0, server.HandlerFaults);
    }

    [Fact]
    public void TheConfiguredWebModeIsBinaryGrpcWeb()
    {
        Assert.Equal(GrpcWebMode.GrpcWeb, CloudHelloTransport.WebMode);
        Assert.NotEqual(GrpcWebMode.GrpcWebText, CloudHelloTransport.WebMode);
        Assert.Equal("application/grpc-web", CloudHelloTransport.RequestMediaType);
    }

    [Theory]
    [InlineData("application/grpc-web")]
    [InlineData("application/grpc-web+proto")]
    public async Task BinaryResponseMediaTypesWithOrWithoutProtoSuffixAreAccepted(string responseType)
    {
        await using var server = new LoopbackHttpServer(async exchange =>
            await exchange.ReplyAsync(200, Greeting(NameOf(exchange.Request)), ("Content-Type", responseType)));
        await using var client = new CloudHelloClient(server.Endpoint);

        Assert.Equal("Hello, media!", await client.SayHelloAsync("media").WaitAsync(Bound));
    }

    [Fact]
    public async Task EachUnaryRequestCarriesTheDeadlineHeaderWithinFiveSeconds()
    {
        await using var server = new LoopbackHttpServer(async exchange =>
            await exchange.ReplyAsync(200, Greeting(NameOf(exchange.Request)), ProtoContentType));
        await using var client = new CloudHelloClient(server.Endpoint);

        await client.SayHelloAsync("deadline").WaitAsync(Bound);

        var timeout = Assert.Single(server.Requests).Header("grpc-timeout");
        Assert.NotNull(timeout);
        Assert.Matches("^[0-9]{1,8}[HMSmun]$", timeout);
        var milliseconds = GrpcWebFrames.TimeoutMilliseconds(timeout);
        Assert.InRange(milliseconds, 1, CloudHelloTransport.MaximumDeadline.TotalMilliseconds);
    }

    [Fact]
    public async Task CreatingTheClientOpensNoConnectionAndSendsNoRpc()
    {
        await using var server = new LoopbackHttpServer(_ => Task.CompletedTask);
        await using var client = new CloudHelloClient(server.Endpoint);

        await Task.Delay(100);

        Assert.Equal(0, server.ConnectionCount);
        Assert.Empty(server.Requests);
    }

    [Fact]
    public async Task NullNameIsRejectedBeforeAnyRequest()
    {
        await using var server = new LoopbackHttpServer(_ => Task.CompletedTask);
        await using var client = new CloudHelloClient(server.Endpoint);

        await Assert.ThrowsAsync<ArgumentNullException>(() => client.SayHelloAsync(null!));
        Assert.Empty(server.Requests);
    }

    [Theory]
    [InlineData(0)]
    [InlineData(257)]
    [InlineData(1024)]
    public async Task NameOutsideOneToTwoHundredFiftySixIsRejectedBeforeAnyRequest(int length)
    {
        await using var server = new LoopbackHttpServer(_ => Task.CompletedTask);
        await using var client = new CloudHelloClient(server.Endpoint);
        var name = new string('x', length);

        var failure = await Assert.ThrowsAsync<ArgumentOutOfRangeException>(() => client.SayHelloAsync(name));

        Assert.Equal("Use a name with 1 to 256 characters.", failure.Message.Split(" (")[0]);
        Assert.Empty(server.Requests);
    }

    [Theory]
    [InlineData(1)]
    [InlineData(256)]
    public async Task NameLengthBoundariesAreSentUnchanged(int length)
    {
        await using var server = new LoopbackHttpServer(async exchange =>
            await exchange.ReplyAsync(200, Greeting(NameOf(exchange.Request)), ProtoContentType));
        await using var client = new CloudHelloClient(server.Endpoint);
        var name = new string('n', length);

        await client.SayHelloAsync(name).WaitAsync(Bound);

        Assert.Equal(name, NameOf(Assert.Single(server.Requests)));
    }

    [Fact]
    public async Task NoCookieIsStoredOrSentOnTheNextRequest()
    {
        await using var server = new LoopbackHttpServer(async exchange =>
        {
            await exchange.StartAsync(200, null, ProtoContentType, ("Set-Cookie", "session=1; Path=/"), ("Set-Cookie", "unrequested=1; Domain=com; Path=/"));
            await exchange.WriteAsync(Greeting(NameOf(exchange.Request)));
        });
        await using var client = new CloudHelloClient(server.Endpoint);

        await client.SayHelloAsync("first").WaitAsync(Bound);
        await client.SayHelloAsync("second").WaitAsync(Bound);

        var requests = server.Requests;
        Assert.Equal(2, requests.Count);
        Assert.All(requests, request => Assert.Null(request.Header("Cookie")));
    }

    [Fact]
    public async Task RedirectIsNotFollowed()
    {
        await using var server = new LoopbackHttpServer(async exchange =>
        {
            if (exchange.Request.Target.EndsWith("/elsewhere", StringComparison.Ordinal))
            {
                await exchange.ReplyAsync(200, Greeting("elsewhere"), ProtoContentType);
                return;
            }

            await exchange.ReplyAsync(302, ReadOnlyMemory<byte>.Empty, ("Location", "/api/elsewhere"));
        });
        await using var client = new CloudHelloClient(server.Endpoint);

        var failure = await Assert.ThrowsAsync<CloudHelloException>(() => client.SayHelloAsync("redirect").WaitAsync(Bound));

        Assert.NotEqual(StatusCode.OK, failure.StatusCode);
        Assert.Equal(GenericMessage, failure.Message);
        Assert.DoesNotContain(server.Requests, request => request.Target.EndsWith("/elsewhere", StringComparison.Ordinal));
        Assert.Single(server.Requests);
    }

    [Fact]
    public async Task ConnectionDropBeforeAnyResponseIsNotRetried()
    {
        await using var server = new LoopbackHttpServer(exchange =>
        {
            exchange.Abort();
            return Task.CompletedTask;
        });
        await using var client = new CloudHelloClient(server.Endpoint);

        var failure = await Assert.ThrowsAsync<CloudHelloException>(() => client.SayHelloAsync("drop").WaitAsync(Bound));

        Assert.Equal(GenericMessage, failure.Message);
        Assert.Single(server.Requests);
    }

    [Fact]
    public async Task ConnectionDropOnAReusedConnectionIsNotRetried()
    {
        var answered = 0;
        await using var server = new LoopbackHttpServer(async exchange =>
        {
            if (Interlocked.Increment(ref answered) == 1)
            {
                await exchange.ReplyAsync(200, Greeting(NameOf(exchange.Request)), ProtoContentType);
                return;
            }

            exchange.Abort();
        });
        await using var client = new CloudHelloClient(server.Endpoint);

        Assert.Equal("Hello, first!", await client.SayHelloAsync("first").WaitAsync(Bound));
        var failure = await Assert.ThrowsAsync<CloudHelloException>(() => client.SayHelloAsync("second").WaitAsync(Bound));

        Assert.Equal(GenericMessage, failure.Message);
        Assert.Equal(2, server.Requests.Count);
    }

    [Theory]
    [InlineData(3, "Cloud rejected this name. Check it and try again.")]
    [InlineData(8, "Cloud's request limit was reached. Try again later.")]
    [InlineData(4, "Cloud did not respond in time. Try again.")]
    [InlineData(1, "The request was canceled. Try again.")]
    [InlineData(14, GenericMessage)]
    [InlineData(12, GenericMessage)]
    [InlineData(16, GenericMessage)]
    public async Task ServerStatusMapsToTheReviewedUserMessage(int code, string expectedMessage)
    {
        await using var server = new LoopbackHttpServer(exchange =>
            exchange.ReplyAsync(200, GrpcWebFrames.Trailers($"grpc-status: {code}", "grpc-message: refused"), ProtoContentType));
        await using var client = new CloudHelloClient(server.Endpoint);

        var failure = await Assert.ThrowsAsync<CloudHelloException>(() => client.SayHelloAsync("status").WaitAsync(Bound));

        Assert.Equal((StatusCode)code, failure.StatusCode);
        Assert.Equal(expectedMessage, failure.Message);
        Assert.Single(server.Requests);
    }

    [Fact]
    public async Task MissingContentTypeIsAProtocolFailureWithTheGenericMessage()
    {
        await using var server = new LoopbackHttpServer(exchange =>
            exchange.ReplyAsync(200, GrpcWebFrames.Trailers("grpc-status: 0")));
        await using var client = new CloudHelloClient(server.Endpoint);

        var failure = await Assert.ThrowsAsync<CloudHelloException>(() => client.SayHelloAsync("type").WaitAsync(Bound));

        Assert.Equal(StatusCode.Internal, failure.StatusCode);
        Assert.Equal(GenericMessage, failure.Message);
    }

    [Fact]
    public async Task BodyCutShortAfterAUnaryReplyBeganIsDataLoss()
    {
        await using var server = new LoopbackHttpServer(async exchange =>
        {
            await exchange.StartAsync(200, 1000, ProtoContentType);
            await exchange.WriteAsync(GrpcWebFrames.Message(new SayHelloResponse { Message = "cut" }));
            exchange.Abort();
        });
        await using var client = new CloudHelloClient(server.Endpoint);

        var failure = await Assert.ThrowsAsync<CloudHelloException>(() => client.SayHelloAsync("truncated").WaitAsync(Bound));

        Assert.Equal(StatusCode.DataLoss, failure.StatusCode);
        Assert.Equal(GenericMessage, failure.Message);
    }

    [Fact]
    public async Task HttpNotFoundIsAProtocolFailureWithTheGenericMessage()
    {
        // Grpc.Net.Client reports a non-gRPC HTTP status as Internal, where the Connect client reported Unimplemented.
        // The user-facing text is the generic one for both, so the Kotlin message table is unchanged.
        await using var server = new LoopbackHttpServer(exchange => exchange.ReplyAsync(404, ReadOnlyMemory<byte>.Empty));
        await using var client = new CloudHelloClient(server.Endpoint);

        var failure = await Assert.ThrowsAsync<CloudHelloException>(() => client.SayHelloAsync("missing").WaitAsync(Bound));

        Assert.Equal(StatusCode.Internal, failure.StatusCode);
        Assert.Equal(GenericMessage, failure.Message);
        Assert.Single(server.Requests);
    }

    [Fact]
    public async Task ResponseWithoutAStatusTrailerFailsRatherThanSucceeding()
    {
        await using var server = new LoopbackHttpServer(exchange =>
            exchange.ReplyAsync(200, GrpcWebFrames.Message(new SayHelloResponse { Message = "unterminated" }), ProtoContentType));
        await using var client = new CloudHelloClient(server.Endpoint);

        var failure = await Assert.ThrowsAsync<CloudHelloException>(() => client.SayHelloAsync("trailer").WaitAsync(Bound));

        Assert.NotEqual(StatusCode.OK, failure.StatusCode);
        Assert.Equal(GenericMessage, failure.Message);
    }

    [Fact]
    public async Task ResponseLargerThanTheReceiveLimitFailsWithResourceExhausted()
    {
        var oversized = new byte[CloudHelloTransport.MaximumReceiveMessageBytes + 1024];
        await using var server = new LoopbackHttpServer(exchange =>
            exchange.ReplyAsync(200, GrpcWebFrames.Concat(GrpcWebFrames.Data(oversized), GrpcWebFrames.Trailers("grpc-status: 0")), ProtoContentType));
        await using var client = new CloudHelloClient(server.Endpoint);

        var failure = await Assert.ThrowsAsync<CloudHelloException>(() => client.SayHelloAsync("large").WaitAsync(Bound));

        Assert.Equal(StatusCode.ResourceExhausted, failure.StatusCode);
        Assert.Equal("Cloud's request limit was reached. Try again later.", failure.Message);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task DeadlineBoundsASilentOrStalledServer(bool sendFirstFrame)
    {
        var peerClosed = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        await using var server = new LoopbackHttpServer(async exchange =>
        {
            if (sendFirstFrame)
            {
                await exchange.StartAsync(200, null, ProtoContentType);
                await exchange.WriteAsync(GrpcWebFrames.Message(new SayHelloResponse { Message = "partial" }));
            }

            peerClosed.TrySetResult(await exchange.WaitForPeerCloseAsync(TimeSpan.FromSeconds(15)));
        });
        await using var client = new CloudHelloClient(server.Endpoint, TimeSpan.FromMilliseconds(500));

        var clock = Stopwatch.StartNew();
        var failure = await Assert.ThrowsAsync<CloudHelloException>(() => client.SayHelloAsync("deadline").WaitAsync(Bound));
        clock.Stop();

        Assert.Equal(StatusCode.DeadlineExceeded, failure.StatusCode);
        Assert.Equal("Cloud did not respond in time. Try again.", failure.Message);
        Assert.True(clock.Elapsed < TimeSpan.FromSeconds(5), $"The call lasted {clock.Elapsed}.");
        Assert.True(await peerClosed.Task.WaitAsync(Bound), "The client must release the connection after the deadline.");
        var timeout = Assert.Single(server.Requests).Header("grpc-timeout");
        Assert.InRange(GrpcWebFrames.TimeoutMilliseconds(timeout!), 1, 500);
        Assert.Single(server.Requests);
    }

    [Fact]
    public async Task CallerCancellationSurfacesAsCancellationAndReleasesTheConnection()
    {
        var arrived = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var peerClosed = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        await using var server = new LoopbackHttpServer(async exchange =>
        {
            arrived.TrySetResult();
            peerClosed.TrySetResult(await exchange.WaitForPeerCloseAsync(TimeSpan.FromSeconds(15)));
        });
        await using var client = new CloudHelloClient(server.Endpoint);
        using var cancellation = new CancellationTokenSource();

        var call = client.SayHelloAsync("cancel", cancellation.Token);
        await arrived.Task.WaitAsync(Bound);
        cancellation.Cancel();

        await Assert.ThrowsAsync<OperationCanceledException>(() => call).WaitAsync(Bound);
        Assert.True(await peerClosed.Task.WaitAsync(Bound), "The cancelled call must close its connection.");
    }

    [Fact]
    public async Task DisposeCancelsAnInFlightCallWithTheCanceledMessage()
    {
        var arrived = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        await using var server = new LoopbackHttpServer(async exchange =>
        {
            arrived.TrySetResult();
            await exchange.WaitForPeerCloseAsync(TimeSpan.FromSeconds(15));
        });
        var client = new CloudHelloClient(server.Endpoint);

        var call = client.SayHelloAsync("dispose");
        await arrived.Task.WaitAsync(Bound);
        client.Dispose();

        var failure = await Assert.ThrowsAsync<CloudHelloException>(() => call).WaitAsync(Bound);
        Assert.Equal(StatusCode.Cancelled, failure.StatusCode);
        Assert.Equal("The request was canceled. Try again.", failure.Message);
        await Assert.ThrowsAsync<ObjectDisposedException>(() => client.SayHelloAsync("after dispose"));
    }

    [Fact]
    public async Task DisposeAsyncShutsTheChannelDownAndIsIdempotent()
    {
        await using var server = new LoopbackHttpServer(async exchange =>
            await exchange.ReplyAsync(200, Greeting(NameOf(exchange.Request)), ProtoContentType));
        var client = new CloudHelloClient(server.Endpoint);
        await client.SayHelloAsync("before").WaitAsync(Bound);

        await client.DisposeAsync().AsTask().WaitAsync(Bound);
        await client.DisposeAsync().AsTask().WaitAsync(Bound);
        client.Dispose();

        await Assert.ThrowsAsync<ObjectDisposedException>(() => client.SayHelloAsync("after"));
    }

    [Theory]
    [InlineData(0)]
    [InlineData(-1)]
    [InlineData(5.001)]
    [InlineData(60)]
    public void DeadlineOutsideZeroToFiveSecondsIsRejected(double seconds)
    {
        var endpoint = new Uri("http://127.0.0.1:9/api");

        Assert.Throws<ArgumentOutOfRangeException>(() => new CloudHelloClient(endpoint, TimeSpan.FromSeconds(seconds)));
        Assert.Throws<ArgumentOutOfRangeException>(() => CloudHelloTransport.CreateCallOptions(TimeSpan.FromSeconds(seconds), CancellationToken.None));
    }

    [Fact]
    public void DeadlineOfExactlyFiveSecondsIsAccepted()
    {
        var options = CloudHelloTransport.CreateCallOptions(TimeSpan.FromSeconds(5), CancellationToken.None);

        Assert.NotNull(options.Deadline);
        Assert.InRange((options.Deadline!.Value - DateTime.UtcNow).TotalSeconds, 4.5, 5.1);
        using var client = new CloudHelloClient(new Uri("http://127.0.0.1:9/api"), TimeSpan.FromSeconds(5));
    }

    [Fact]
    public void TheTransportConstantsHaveTheReviewedValues()
    {
        Assert.Equal(TimeSpan.FromSeconds(5), CloudHelloTransport.MaximumDeadline);
        Assert.Equal(TimeSpan.FromSeconds(10), CloudHelloTransport.CallTimeout);
        Assert.Equal(256 * 1024, CloudHelloTransport.MaximumReceiveMessageBytes);
        Assert.Equal("https://arcforges.com/api", CloudHelloTransport.ProductionEndpoint);
        Assert.Equal(256, CloudHelloClient.MaximumNameLength);
    }

    [Theory]
    [InlineData("https://arcforges.com/api")]
    [InlineData("https://arcforges.com:443/api")]
    [InlineData("http://127.0.0.1:8080/api")]
    public void SupportedEndpointsAreAccepted(string endpoint)
    {
        Assert.Equal(new Uri(endpoint), CloudHelloTransport.ValidateEndpoint(new Uri(endpoint)));
    }

    [Theory]
    [InlineData("http://arcforges.com/api")]
    [InlineData("http://127.0.0.2:8080/api")]
    [InlineData("http://localhost:8080/api")]
    [InlineData("https://arcforges.com/api/")]
    [InlineData("https://arcforges.com/")]
    [InlineData("https://arcforges.com/apix")]
    [InlineData("https://arcforges.com/api?x=1")]
    [InlineData("https://arcforges.com/api?")]
    [InlineData("https://arcforges.com/api#fragment")]
    [InlineData("https://user@arcforges.com/api")]
    [InlineData("ftp://arcforges.com/api")]
    public void UnsupportedEndpointsAreRejected(string endpoint)
    {
        Assert.Throws<ArgumentException>(() => CloudHelloTransport.ValidateEndpoint(new Uri(endpoint)));
        Assert.Throws<ArgumentException>(() => new CloudHelloClient(new Uri(endpoint)));
    }

    [Theory]
    [InlineData(StatusCode.InvalidArgument, "Cloud rejected this name. Check it and try again.")]
    [InlineData(StatusCode.ResourceExhausted, "Cloud's request limit was reached. Try again later.")]
    [InlineData(StatusCode.DeadlineExceeded, "Cloud did not respond in time. Try again.")]
    [InlineData(StatusCode.Cancelled, "The request was canceled. Try again.")]
    [InlineData(StatusCode.Unavailable, GenericMessage)]
    [InlineData(StatusCode.Unimplemented, GenericMessage)]
    [InlineData(StatusCode.Internal, GenericMessage)]
    public void StatusTableHasTheReviewedUserMessages(StatusCode code, string expected)
    {
        Assert.Equal(expected, CloudHelloClient.UserMessageFor(code));
    }
}
