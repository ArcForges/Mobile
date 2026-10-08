// SPDX-License-Identifier: Apache-2.0
namespace ArcForges.Mobile;

public sealed class App : Application
{
    protected override Window CreateWindow(IActivationState? activationState) => new(new MainPage());
}
