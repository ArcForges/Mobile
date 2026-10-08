// SPDX-License-Identifier: Apache-2.0
using ArcForges.Contracts.Hello.V1;

namespace ArcForges.Mobile.Compatibility;

// AND.01 compile-time evidence that the published NuGet Contracts client restores and builds
// against the pinned MAUI tuple for net10.0-android. It carries no behaviour; AND.04 owns the client.
internal static class ContractsClientCompatibility
{
    internal static Type HelloClientType { get; } = typeof(HelloService.HelloServiceClient);
}
