// SPDX-License-Identifier: Apache-2.0
namespace ArcForges.Mobile.Network;

/// <summary>
/// Restores the base path of the Cloud endpoint for each call. Grpc.Net.Client 2.84.0 builds the request URI from the
/// method path, which starts with <c>/</c>, so the <c>/api</c> of the base address is dropped. This handler sits inside
/// the gRPC-Web handler, after the library has built the final URI, and prefixes the path once. It never changes the
/// host, scheme, port, query or method.
/// </summary>
internal sealed class PathPrefixHandler(string prefix, HttpMessageHandler innerHandler) : DelegatingHandler(innerHandler)
{
    private readonly string _prefix = prefix.StartsWith('/') && !prefix.EndsWith('/')
        ? prefix
        : throw new ArgumentException("The path prefix must start with '/' and must not end with '/'.", nameof(prefix));

    /// <inheritdoc />
    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(request);
        var uri = request.RequestUri ?? throw new InvalidOperationException("The gRPC request has no URI.");
        if (!uri.AbsolutePath.StartsWith(_prefix + "/", StringComparison.Ordinal))
        {
            request.RequestUri = new UriBuilder(uri) { Path = _prefix + uri.AbsolutePath }.Uri;
        }

        return base.SendAsync(request, cancellationToken);
    }
}
