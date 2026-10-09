// SPDX-License-Identifier: Apache-2.0
using Grpc.Core;

namespace ArcForges.Mobile.Network;

/// <summary>
/// A Hello failure with its gRPC status. <see cref="Exception.Message"/> is the user-facing text from
/// <see cref="CloudHelloClient.UserMessageFor"/>; the status is kept for diagnostics and tests.
/// </summary>
public sealed class CloudHelloException : Exception
{
    /// <summary>Creates the exception for a status and its user-facing message.</summary>
    public CloudHelloException(StatusCode statusCode, string userMessage, Exception? inner = null)
        : base(userMessage, inner)
    {
        StatusCode = statusCode;
    }

    /// <summary>The gRPC status that the failure maps to.</summary>
    public StatusCode StatusCode { get; }
}
