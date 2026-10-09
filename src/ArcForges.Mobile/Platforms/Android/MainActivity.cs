// SPDX-License-Identifier: Apache-2.0
using Android.App;
using Android.Content.PM;

namespace ArcForges.Mobile;

/// <summary>
/// The launcher activity. Its Java name is pinned, so the identity gate can check the launchable component exactly
/// (eng/maui_identity.py). Configuration changes are handled in place, as in the Kotlin manifest.
/// </summary>
[Activity(
    Name = "com.arcforges.mobile.MainActivity",
    Theme = "@style/Maui.SplashTheme",
    MainLauncher = true,
    ConfigurationChanges = ConfigChanges.ScreenSize | ConfigChanges.Orientation | ConfigChanges.UiMode
        | ConfigChanges.ScreenLayout | ConfigChanges.SmallestScreenSize | ConfigChanges.Density)]
public class MainActivity : MauiAppCompatActivity
{
}
