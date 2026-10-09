// SPDX-License-Identifier: Apache-2.0
using ArcForges.Mobile.Network;
using Microsoft.Extensions.DependencyInjection;

namespace ArcForges.Mobile;

/// <summary>Composition root: the application, the Hello client and the Hello screen.</summary>
public static class MauiProgram
{
    /// <summary>The Cloud Hello endpoint: https, path /api exactly, as in the Kotlin client (BASE_URL).</summary>
    public static readonly Uri CloudEndpoint = new("https://arcforges.com/api");

    public static MauiApp CreateMauiApp()
    {
        var builder = MauiApp.CreateBuilder();
        builder.UseMauiApp<App>();
        builder.Services.AddSingleton(_ => new CloudHelloClient(CloudEndpoint));
        builder.Services.AddTransient<MainPage>();
        return builder.Build();
    }
}
