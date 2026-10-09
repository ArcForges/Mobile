// SPDX-License-Identifier: Apache-2.0
using ArcForges.Mobile.Diagnostics;
using ArcForges.Mobile.Network;

namespace ArcForges.Mobile;

/// <summary>
/// The Hello screen. States follow the Kotlin ArcForgesApp: a name of 1 to 256 characters, one request at a time,
/// a bounded failure message, and a retry by the same button after a failure.
/// </summary>
public partial class MainPage : ContentPage
{
    private const string ReadyMessage = "Ready to connect.";
    private const string ConnectingMessage = "Connecting...";
    private const string GenericFailure = "Could not complete the request. Please try again.";

    private readonly CloudHelloClient _cloud;
    private string _greeting = ReadyMessage;
    private string? _error;
    private bool _loading;

    public MainPage(CloudHelloClient cloud)
    {
        _cloud = cloud;
        InitializeComponent();
        UpdateState();
    }

    private void OnNameChanged(object? sender, TextChangedEventArgs e) => UpdateState();

    private async void OnSayHelloClicked(object? sender, EventArgs e)
    {
        var name = NameEntry.Text ?? string.Empty;
        _loading = true;
        _error = null;
        UpdateState();
        try
        {
            _greeting = await _cloud.SayHelloAsync(name);
        }
        catch (OperationCanceledException)
        {
            // A cancelled request is not a failure to show; the screen keeps its previous greeting.
        }
        catch (CloudHelloException failure)
        {
            _error = failure.Message;
        }
        catch (Exception)
        {
            _error = GenericFailure;
        }
        finally
        {
            _loading = false;
            UpdateState();
        }
    }

    private async void OnBuildInformationTapped(object? sender, TappedEventArgs e)
    {
        await DisplayAlertAsync("Build information", BuildInformation.Load(), "Close");
    }

    private void UpdateState()
    {
        var length = NameEntry.Text?.Length ?? 0;
        var valid = length is >= 1 and <= CloudHelloClient.MaximumNameLength;

        GreetingLabel.Text = _loading ? ConnectingMessage : _greeting;
        NameEntry.IsEnabled = !_loading;
        NameCounter.Text = $"{length}/{CloudHelloClient.MaximumNameLength}";
        NameCounter.TextColor = valid ? Color.FromArgb("#5C6B63") : Color.FromArgb("#B00020");
        ErrorLabel.Text = _error;
        ErrorLabel.IsVisible = _error is not null;
        SayHelloButton.Text = _loading ? ConnectingMessage : "Say hello";
        SayHelloButton.IsEnabled = !_loading && valid;
    }
}
