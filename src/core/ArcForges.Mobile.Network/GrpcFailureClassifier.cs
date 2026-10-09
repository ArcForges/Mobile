// SPDX-License-Identifier: Apache-2.0
using Grpc.Core;
using Grpc.Net.Client;

namespace ArcForges.Mobile.Network;

/// <summary>
/// Turns a transport failure of Grpc.Net.Client 2.84.0 into the status the AND.40 rules require.
/// <para>
/// The library does not expose a missing or duplicate <c>grpc-status</c> trailer as data. It removes the status from
/// the trailer metadata and reports these conditions as <see cref="RpcException"/> with a fixed detail text. The texts
/// below are that characterisation: the transport tests assert each one against a loopback fixture, so a library
/// upgrade that changes a text fails the suite instead of silently reclassifying a failure.
/// </para>
/// </summary>
internal static class GrpcFailureClassifier
{
    /// <summary>The response ended without a <c>grpc-status</c> trailer.</summary>
    internal const string MissingStatusDetail = "No grpc-status found on response.";

    /// <summary>The response carried more than one <c>grpc-status</c> trailer.</summary>
    internal const string DuplicateStatusDetail = "Multiple grpc-status headers.";

    /// <summary>
    /// The response body ended before its declared length. The transport names the HTTP error <c>ResponseEnded</c>; that
    /// error exists only once a response head has arrived, so the body was cut short.
    /// </summary>
    internal const string ResponseEndedMarker = "(ResponseEnded)";

    /// <summary>The response is not a gRPC response (for example, no content type, or a non-gRPC body).</summary>
    internal const string BadResponseDetailPrefix = "Bad gRPC response.";

    /// <summary>The status a failure maps to.</summary>
    public static Status Classify(RpcException failure)
    {
        ArgumentNullException.ThrowIfNull(failure);
        var detail = failure.Status.Detail ?? string.Empty;
        if (detail == MissingStatusDetail || detail == DuplicateStatusDetail)
        {
            return new Status(StatusCode.DataLoss, detail);
        }

        if (detail.Contains(ResponseEndedMarker, StringComparison.Ordinal))
        {
            return new Status(StatusCode.DataLoss, detail);
        }

        if (detail.StartsWith(BadResponseDetailPrefix, StringComparison.Ordinal))
        {
            return new Status(StatusCode.Internal, detail);
        }

        return failure.Status;
    }
}
