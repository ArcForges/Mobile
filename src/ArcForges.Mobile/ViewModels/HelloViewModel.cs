// SPDX-License-Identifier: Apache-2.0
using System.ComponentModel;
using ArcForges.Mobile.Network;

namespace ArcForges.Mobile.ViewModels;

/// <summary>
/// The Hello screen state, at parity with the Kotlin ArcForgesApp (AND.40 decision 15). The app owns one instance,
/// registered in DI, so the name, the greeting and an in-flight request survive page and activity recreation within
/// the process. It uses no platform types: the host tests compile this file directly (tests/ArcForges.Mobile.Tests).
/// </summary>
public sealed class HelloViewModel : INotifyPropertyChanged
{
    /// <summary>The greeting shown before the first successful call.</summary>
    public const string ReadyMessage = "Ready to connect.";

    /// <summary>The text shown in place of the greeting while a request is in flight.</summary>
    public const string ConnectingMessage = "Connecting...";

    /// <summary>The bounded failure text for an error that is not a Hello failure.</summary>
    public const string GenericFailure = "Could not complete the request. Please try again.";

    /// <summary>The name the screen starts with.</summary>
    public const string DefaultName = "World";

    private static readonly string[] AllProperties =
    [
        nameof(Name), nameof(NameLength), nameof(IsNameValid), nameof(IsLoading), nameof(CanSayHello),
        nameof(Greeting), nameof(DisplayGreeting), nameof(Error), nameof(HasError),
    ];

    private readonly Func<string, CancellationToken, Task<string>> _sayHello;
    private string _name = DefaultName;
    private string _greeting = ReadyMessage;
    private string? _error;
    private bool _loading;

    /// <summary>Creates the view-model over the Hello call, which takes the name and a cancellation token.</summary>
    public HelloViewModel(Func<string, CancellationToken, Task<string>> sayHello)
    {
        _sayHello = sayHello ?? throw new ArgumentNullException(nameof(sayHello));
    }

    /// <inheritdoc />
    public event PropertyChangedEventHandler? PropertyChanged;

    /// <summary>The name in the entry, exactly as typed. It is never trimmed.</summary>
    public string Name
    {
        get => _name;
        set
        {
            var next = value ?? string.Empty;
            if (next == _name)
            {
                return;
            }

            _name = next;
            RaiseAll();
        }
    }

    /// <summary>The name length in UTF-16 code units, the unit the Kotlin client counted.</summary>
    public int NameLength => _name.Length;

    /// <summary>True when the name has 1 to 256 UTF-16 code units.</summary>
    public bool IsNameValid => NameLength is >= 1 and <= CloudHelloClient.MaximumNameLength;

    /// <summary>True while one request is in flight.</summary>
    public bool IsLoading => _loading;

    /// <summary>True when a new request may be sent: no request is in flight and the name is valid.</summary>
    public bool CanSayHello => !_loading && IsNameValid;

    /// <summary>The last successful greeting, kept through failures and cancellations.</summary>
    public string Greeting => _greeting;

    /// <summary>The text the screen shows as the greeting: the connecting text while a request is in flight.</summary>
    public string DisplayGreeting => _loading ? ConnectingMessage : _greeting;

    /// <summary>The user-facing failure of the last request, or null.</summary>
    public string? Error => _error;

    /// <summary>True when the last request failed and the failure is shown.</summary>
    public bool HasError => _error is not null;

    /// <summary>
    /// Sends the current name. One request runs at a time and an invalid name sends nothing. A success replaces the
    /// greeting. A cancelled request keeps the previous greeting and shows no error. A failure keeps the previous
    /// greeting and shows its message; the same action retries.
    /// </summary>
    public async Task SayHelloAsync(CancellationToken cancellationToken = default)
    {
        if (!CanSayHello)
        {
            return;
        }

        var name = _name;
        _loading = true;
        _error = null;
        RaiseAll();
        try
        {
            _greeting = await _sayHello(name, cancellationToken);
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
            RaiseAll();
        }
    }

    private void RaiseAll()
    {
        foreach (var property in AllProperties)
        {
            PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(property));
        }
    }
}
