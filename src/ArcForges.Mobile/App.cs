// SPDX-License-Identifier: Apache-2.0
using Microsoft.Extensions.DependencyInjection;

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

        // The view-model outlives the window. Closing the window releases the Hello client, as the Kotlin activity did in
        // onDestroy; the next window in the same process creates a new client on its first call.
        window.Destroying += (_, _) => _services.GetRequiredService<HelloConnection>().Release();
        return window;
    }
}
