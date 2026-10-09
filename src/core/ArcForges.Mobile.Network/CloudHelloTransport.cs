// SPDX-License-Identifier: Apache-2.0
using Grpc.Core;
using Grpc.Net.Client;
using Grpc.Net.Client.Web;

namespace ArcForges.Mobile.Network;

/// <summary>
/// The one transport configuration shared by unary and server-stream calls (AND.40 Hello transport rules,
/// carried from the retired Kotlin CloudHelloClient). It selects binary gRPC-Web, disables cookies and
/// redirects, sets no retry policy, caps per-call deadlines at 5 s, and bounds received messages.
/// </summary>
public static class CloudHelloTransport
{
    /// <summary>The production base address. The path is exactly <c>/api</c>.</summary>
    public const string ProductionEndpoint = "https://arcforges.com/api";

    /// <summary>The loopback-only cleartext host, used by local development and fixtures only.</summary>
    public const string LoopbackHost = "127.0.0.1";

    /// <summary>Upper bound of every per-call gRPC deadline, sent in the grpc-timeout header.</summary>
    public static readonly TimeSpan MaximumDeadline = TimeSpan.FromSeconds(5);

    /// <summary>
    /// Upper bound of one unary call, including reading its response body; <see cref="CloudHelloClient"/> applies it.
    /// A server-stream caller links this bound to its own token when it creates the call.
    /// </summary>
    public static readonly TimeSpan CallTimeout = TimeSpan.FromSeconds(10);

    /// <summary>Largest received message, applied to unary responses and to each stream frame.</summary>
    public const int MaximumReceiveMessageBytes = 256 * 1024;

    /// <summary>The gRPC-Web mode selected for every call. Binary, never the text (base64) variant.</summary>
    public const GrpcWebMode WebMode = GrpcWebMode.GrpcWeb;

    /// <summary>
    /// The request media type that <see cref="WebMode"/> produces. A fixture asserts it on every request, so a
    /// library change that alters the wire type fails the suite instead of reaching production.
    /// </summary>
    public const string RequestMediaType = "application/grpc-web";

    /// <summary>
    /// Validates the endpoint with the Kotlin rules: https, or http only for 127.0.0.1; the path is exactly
    /// <c>/api</c>; no user information, query or fragment.
    /// </summary>
    public static Uri ValidateEndpoint(Uri endpoint)
    {
        ArgumentNullException.ThrowIfNull(endpoint);
        if (!endpoint.IsAbsoluteUri)
        {
            throw new ArgumentException("The Cloud endpoint must be an absolute URI.", nameof(endpoint));
        }

        var scheme = endpoint.Scheme;
        var secure = scheme == Uri.UriSchemeHttps;
        var loopback = scheme == Uri.UriSchemeHttp && endpoint.Host == LoopbackHost;
        if (!secure && !loopback)
        {
            throw new ArgumentException("The Cloud endpoint must use https, or http on 127.0.0.1 only.", nameof(endpoint));
        }

        if (endpoint.AbsolutePath != "/api"
            || endpoint.UserInfo.Length != 0
            || endpoint.Query.Length != 0
            || endpoint.Fragment.Length != 0
            || endpoint.OriginalString.Contains('?', StringComparison.Ordinal)
            || endpoint.OriginalString.Contains('#', StringComparison.Ordinal))
        {
            throw new ArgumentException("The Cloud endpoint path must be exactly /api, without query, fragment or user information.", nameof(endpoint));
        }

        return endpoint;
    }

    /// <summary>
    /// Builds the channel. The HTTP handler never stores or sends cookies and never follows redirects; retry is
    /// not configured on the channel, so a failed call is reported once.
    /// </summary>
    public static GrpcChannel CreateChannel(Uri endpoint)
    {
        var validated = ValidateEndpoint(endpoint);
        var socketsHandler = new SocketsHttpHandler
        {
            UseCookies = false,
            AllowAutoRedirect = false,
            AutomaticDecompression = System.Net.DecompressionMethods.None,
        };
        // The path prefix is applied inside the gRPC-Web handler, where the final request URI is known.
        var handler = new GrpcWebHandler(WebMode, new PathPrefixHandler(validated.AbsolutePath, socketsHandler));
        // The HttpClient owns the handler chain, so disposing the channel releases the sockets. Its own Timeout is
        // infinite, so the per-call deadline (at most 5 s) and the caller's cancellation are the bounds on every call.
        var client = new HttpClient(handler, disposeHandler: true) { Timeout = Timeout.InfiniteTimeSpan };
        return GrpcChannel.ForAddress(
            validated,
            new GrpcChannelOptions
            {
                HttpClient = client,
                DisposeHttpClient = true,
                // HTTP/2 over TLS in production (ALPN). Cleartext loopback fixtures cannot negotiate HTTP/2, so the
                // policy falls back to HTTP/1.1 rather than sending the HTTP/2 connection preface to a plain socket.
                HttpVersion = new Version(2, 0),
                HttpVersionPolicy = HttpVersionPolicy.RequestVersionOrLower,
                MaxReceiveMessageSize = MaximumReceiveMessageBytes,
                MaxSendMessageSize = MaximumReceiveMessageBytes,
                ThrowOperationCanceledOnCancellation = false,
            });
    }

    /// <summary>
    /// Builds call options with a deadline no further away than <see cref="MaximumDeadline"/>. The
    /// <paramref name="deadline"/> is validated, never silently clamped.
    /// </summary>
    public static CallOptions CreateCallOptions(TimeSpan deadline, CancellationToken cancellationToken)
    {
        if (deadline <= TimeSpan.Zero || deadline > MaximumDeadline)
        {
            throw new ArgumentOutOfRangeException(nameof(deadline), "The call deadline must be positive and at most 5 seconds.");
        }

        return new CallOptions(
            deadline: DateTime.UtcNow + deadline,
            cancellationToken: cancellationToken);
    }
}
