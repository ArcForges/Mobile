// SPDX-License-Identifier: Apache-2.0
using ArcForges.Mobile.Network;
using Grpc.Core;
using Grpc.Net.Client;

namespace ArcForges.Mobile.Tests;

/// <summary>
/// Unit rules of the transport that the loopback matrix depends on: the failure characterisation of
/// Grpc.Net.Client 2.84.0 and the path prefix that restores the Cloud base path.
/// </summary>
public sealed class TransportRuleTests
{
    [Theory]
    [InlineData(StatusCode.Cancelled, "No grpc-status found on response.", StatusCode.DataLoss)]
    [InlineData(StatusCode.Cancelled, "Multiple grpc-status headers.", StatusCode.DataLoss)]
    [InlineData(StatusCode.Unavailable, "Error reading next message. HttpIOException: The response ended prematurely, with at least 9 additional bytes expected. (ResponseEnded)", StatusCode.DataLoss)]
    [InlineData(StatusCode.Unavailable, "Error starting gRPC call. HttpIOException: The response ended prematurely, with at least 990 additional bytes expected. (ResponseEnded)", StatusCode.DataLoss)]
    [InlineData(StatusCode.Cancelled, "Bad gRPC response. Response did not have a content-type header.", StatusCode.Internal)]
    [InlineData(StatusCode.PermissionDenied, "refused", StatusCode.PermissionDenied)]
    [InlineData(StatusCode.Cancelled, "refused", StatusCode.Cancelled)]
    [InlineData(StatusCode.DeadlineExceeded, "", StatusCode.DeadlineExceeded)]
    [InlineData(StatusCode.Unavailable, "Error starting gRPC call.", StatusCode.Unavailable)]
    public void TransportFailuresMapToTheirRequiredStatus(StatusCode library, string detail, StatusCode expected)
    {
        var failure = new RpcException(new Status(library, detail));

        var mapped = GrpcFailureClassifier.Classify(failure);

        Assert.Equal(expected, mapped.StatusCode);
    }

    [Fact]
    public void AClassifiedFailureKeepsItsDetailText()
    {
        var mapped = GrpcFailureClassifier.Classify(
            new RpcException(new Status(StatusCode.Cancelled, "No grpc-status found on response.")));

        Assert.Equal("No grpc-status found on response.", mapped.Detail);
    }

    [Theory]
    [InlineData("api")]
    [InlineData("/api/")]
    [InlineData("")]
    public void PathPrefixMustStartWithASlashAndNotEndWithOne(string prefix)
    {
        using var inner = new CaptureHandler();

        Assert.Throws<ArgumentException>(() => new PathPrefixHandler(prefix, inner));
    }

    [Theory]
    [InlineData("/arcforges.hello.v1.HelloService/SayHello", "http://127.0.0.1:4321/api/arcforges.hello.v1.HelloService/SayHello")]
    [InlineData("/api/arcforges.hello.v1.HelloService/SayHello", "http://127.0.0.1:4321/api/arcforges.hello.v1.HelloService/SayHello")]
    public async Task PathPrefixIsAppliedOnceAndNothingElseChanges(string path, string expected)
    {
        using var inner = new CaptureHandler();
        using var invoker = new HttpMessageInvoker(new PathPrefixHandler("/api", inner));
        using var request = new HttpRequestMessage(HttpMethod.Post, new Uri("http://127.0.0.1:4321" + path));

        using var response = await invoker.SendAsync(request, CancellationToken.None);

        Assert.Equal(200, (int)response.StatusCode);
        Assert.Equal(new Uri(expected), inner.Seen);
        Assert.Equal(HttpMethod.Post, inner.Method);
    }

    private sealed class CaptureHandler : HttpMessageHandler
    {
        public Uri? Seen { get; private set; }

        public HttpMethod? Method { get; private set; }

        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            Seen = request.RequestUri;
            Method = request.Method;
            return Task.FromResult(new HttpResponseMessage(System.Net.HttpStatusCode.OK));
        }
    }
}
