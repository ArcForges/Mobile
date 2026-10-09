// SPDX-License-Identifier: Apache-2.0
using ArcForges.Mobile.ViewModels;
using Microsoft.Extensions.DependencyInjection;

namespace ArcForges.Mobile;

/// <summary>Composition root: the application, the Hello connection, the Hello view-model and the Hello screen.</summary>
public static class MauiProgram
{
    /// <summary>The Cloud Hello endpoint: https, path /api exactly, as in the Kotlin client (BASE_URL).</summary>
    public static readonly Uri CloudEndpoint = new("https://arcforges.com/api");

    public static MauiApp CreateMauiApp()
    {
        var builder = MauiApp.CreateBuilder();
        builder.UseMauiApp<App>();

        // One connection holder and one view-model per process (AND.40 decision 15): the screen state outlives the page.
        builder.Services.AddSingleton(_ => new HelloConnection(CloudEndpoint));
        builder.Services.AddSingleton<HelloViewModel>(services =>
            new HelloViewModel(services.GetRequiredService<HelloConnection>().SayHelloAsync));
        builder.Services.AddTransient<MainPage>();
        return builder.Build();
    }
}
