// SPDX-License-Identifier: Apache-2.0
namespace ArcForges.Mobile;

public sealed class MainPage : ContentPage
{
    public MainPage()
    {
        Title = "ArcForges";
        Content = new Label
        {
            Text = "ArcForges",
            HorizontalOptions = LayoutOptions.Center,
            VerticalOptions = LayoutOptions.Center,
        };
    }
}
