// SPDX-License-Identifier: Apache-2.0
using Microsoft.Extensions.DependencyInjection;
using ArcForges.Mobile.Network;

namespace ArcForges.Mobile;

/// <summary>The application: one window that hosts the Hello screen (AND.40 unit 3).</summary>
public sealed class App : Application
{
    private readonly IServiceProvider _services;

    public App(IServiceProvider services)
    {
        _services = services;
    }

    protected override Window CreateWindow(IActivationState? activationState)
    {
        var window = new Window(_services.GetRequiredService<MainPage>());

        // The Hello client holds a channel and in-flight calls; closing the window releases them, as the Kotlin
        // activity closed its client in onDestroy.
        window.Destroying += (_, _) => _services.GetRequiredService<CloudHelloClient>().Dispose();
        return window;
    }
}
