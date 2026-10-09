// SPDX-License-Identifier: Apache-2.0
using System.ComponentModel;
using ArcForges.Mobile.Diagnostics;
using ArcForges.Mobile.Network;
using ArcForges.Mobile.ViewModels;

namespace ArcForges.Mobile;

/// <summary>
/// The Hello screen. It renders the app-owned <see cref="HelloViewModel"/>, so the name, the greeting and an in-flight
/// request survive when this page is recreated within the process. The page shows state and forwards input only.
/// </summary>
public partial class MainPage : ContentPage
{
    private readonly HelloViewModel _viewModel;

    public MainPage(HelloViewModel viewModel)
    {
        _viewModel = viewModel;

        // InitializeComponent writes the XAML's default name into the entry, which would overwrite the kept name.
        var keptName = _viewModel.Name;
        InitializeComponent();
        NameEntry.Text = keptName;
        UpdateState();
    }

    protected override void OnAppearing()
    {
        base.OnAppearing();
        _viewModel.PropertyChanged += OnViewModelChanged;
        UpdateState();
    }

    protected override void OnDisappearing()
    {
        _viewModel.PropertyChanged -= OnViewModelChanged;
        base.OnDisappearing();
    }

    private void OnViewModelChanged(object? sender, PropertyChangedEventArgs e) => UpdateState();

    private void OnNameChanged(object? sender, TextChangedEventArgs e) => _viewModel.Name = e.NewTextValue ?? string.Empty;

    private async void OnSayHelloClicked(object? sender, EventArgs e) => await _viewModel.SayHelloAsync();

    private async void OnBuildInformationTapped(object? sender, TappedEventArgs e)
    {
        await DisplayAlertAsync("Build information", BuildInformation.Load(), "Close");
    }

    private void UpdateState()
    {
        var model = _viewModel;
        GreetingLabel.Text = model.DisplayGreeting;
        NameEntry.IsEnabled = !model.IsLoading;
        NameCounter.Text = $"{model.NameLength}/{CloudHelloClient.MaximumNameLength}";
        NameCounter.TextColor = model.IsNameValid ? Color.FromArgb("#5C6B63") : Color.FromArgb("#B00020");
        ErrorLabel.Text = model.Error;
        ErrorLabel.IsVisible = model.HasError;
        SayHelloButton.Text = model.IsLoading ? HelloViewModel.ConnectingMessage : "Say hello";
        SayHelloButton.IsEnabled = model.CanSayHello;
    }
}
