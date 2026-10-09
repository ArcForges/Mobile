// SPDX-License-Identifier: Apache-2.0
using Android.App;
using Android.Runtime;

namespace ArcForges.Mobile;

/// <summary>The Android application entry point; the composition root is <see cref="MauiProgram"/>.</summary>
[Application]
public sealed class MainApplication : MauiApplication
{
    public MainApplication(IntPtr handle, JniHandleOwnership ownership)
        : base(handle, ownership)
    {
    }

    protected override MauiApp CreateMauiApp() => MauiProgram.CreateMauiApp();
}
