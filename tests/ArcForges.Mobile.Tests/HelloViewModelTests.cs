// SPDX-License-Identifier: Apache-2.0
using ArcForges.Mobile.Network;
using ArcForges.Mobile.ViewModels;
using Grpc.Core;

namespace ArcForges.Mobile.Tests;

// AND.40 unit 4: the Hello view-model (decision 15). The app file is compiled into this project (see the csproj), so these
// tests check the code the app runs, on a host, without a device. The fake call is scripted per test.
public sealed class HelloViewModelTests
{
    private sealed class ScriptedHello
    {
        public Func<string, CancellationToken, Task<string>> Next { get; set; } =
            (name, _) => Task.FromResult("Hello, " + name + "!");

        public List<string> Names { get; } = [];

        public List<CancellationToken> Tokens { get; } = [];

        public Task<string> Invoke(string name, CancellationToken cancellationToken)
        {
            Names.Add(name);
            Tokens.Add(cancellationToken);
            return Next(name, cancellationToken);
        }
    }

    private static CloudHelloException HelloFailure(StatusCode code) =>
        new(code, CloudHelloClient.UserMessageFor(code));

    [Fact]
    public void StartsReadyWithTheDefaultName()
    {
        var model = new HelloViewModel(new ScriptedHello().Invoke);

        Assert.Equal("World", model.Name);
        Assert.Equal(HelloViewModel.ReadyMessage, model.DisplayGreeting);
        Assert.Equal(HelloViewModel.ReadyMessage, model.Greeting);
        Assert.False(model.IsLoading);
        Assert.False(model.HasError);
        Assert.True(model.CanSayHello);
    }

    [Theory]
    [InlineData(0, false)]
    [InlineData(1, true)]
    [InlineData(256, true)]
    [InlineData(257, false)]
    public void NameRuleAcceptsOneToTwoHundredFiftySixUnits(int length, bool valid)
    {
        var hello = new ScriptedHello();
        var model = new HelloViewModel(hello.Invoke);

        model.Name = new string('a', length);

        Assert.Equal(length, model.NameLength);
        Assert.Equal(valid, model.IsNameValid);
        Assert.Equal(valid, model.CanSayHello);
    }

    [Fact]
    public void NameRuleCountsUtf16UnitsSoASurrogatePairIsTwo()
    {
        var model = new HelloViewModel(new ScriptedHello().Invoke);

        model.Name = string.Concat(Enumerable.Repeat("\U0001F600", 128));
        Assert.Equal(256, model.NameLength);
        Assert.True(model.IsNameValid);

        model.Name = string.Concat(Enumerable.Repeat("\U0001F600", 129));
        Assert.Equal(258, model.NameLength);
        Assert.False(model.IsNameValid);
    }

    [Fact]
    public async Task AnInvalidNameSendsNothing()
    {
        var hello = new ScriptedHello();
        var model = new HelloViewModel(hello.Invoke);
        model.Name = string.Empty;

        await model.SayHelloAsync();

        Assert.Empty(hello.Names);
        Assert.Equal(HelloViewModel.ReadyMessage, model.DisplayGreeting);
        Assert.False(model.HasError);
    }

    [Fact]
    public async Task ASuccessfulCallSendsTheNameAsTypedAndShowsTheGreeting()
    {
        var hello = new ScriptedHello();
        var model = new HelloViewModel(hello.Invoke);
        model.Name = " Ada  ";

        await model.SayHelloAsync();

        Assert.Equal(new[] { " Ada  " }, hello.Names);
        Assert.Equal("Hello,  Ada  !", model.Greeting);
        Assert.Equal("Hello,  Ada  !", model.DisplayGreeting);
        Assert.False(model.IsLoading);
        Assert.False(model.HasError);
    }

    [Fact]
    public async Task ShowsConnectingWhileInFlightAndRefusesASecondRequest()
    {
        var gate = new TaskCompletionSource<string>(TaskCreationOptions.RunContinuationsAsynchronously);
        var hello = new ScriptedHello { Next = (_, _) => gate.Task };
        var model = new HelloViewModel(hello.Invoke);

        var first = model.SayHelloAsync();

        Assert.True(model.IsLoading);
        Assert.Equal(HelloViewModel.ConnectingMessage, model.DisplayGreeting);
        Assert.False(model.CanSayHello);

        await model.SayHelloAsync();
        Assert.Single(hello.Names);

        gate.SetResult("Hello, World!");
        await first;

        Assert.False(model.IsLoading);
        Assert.Equal("Hello, World!", model.DisplayGreeting);
    }

    [Fact]
    public async Task AFailureKeepsThePreviousGreetingAndShowsTheUserMessage()
    {
        var hello = new ScriptedHello();
        var model = new HelloViewModel(hello.Invoke);
        await model.SayHelloAsync();

        hello.Next = (_, _) => Task.FromException<string>(HelloFailure(StatusCode.Unavailable));
        await model.SayHelloAsync();

        Assert.Equal("Hello, World!", model.Greeting);
        Assert.True(model.HasError);
        Assert.Equal("Could not reach Cloud. Check your connection and try again.", model.Error);
        Assert.True(model.CanSayHello);
    }

    [Fact]
    public async Task TheSameActionRetriesAfterAFailureAndClearsTheError()
    {
        var hello = new ScriptedHello { Next = (_, _) => Task.FromException<string>(HelloFailure(StatusCode.DeadlineExceeded)) };
        var model = new HelloViewModel(hello.Invoke);
        await model.SayHelloAsync();
        Assert.True(model.HasError);

        hello.Next = (name, _) => Task.FromResult("Hello, " + name + "!");
        model.Name = "Grace";
        await model.SayHelloAsync();

        Assert.Equal(new[] { "World", "Grace" }, hello.Names);
        Assert.False(model.HasError);
        Assert.Null(model.Error);
        Assert.Equal("Hello, Grace!", model.Greeting);
    }

    [Fact]
    public async Task AnUnexpectedErrorShowsTheGenericMessage()
    {
        var model = new HelloViewModel((_, _) => Task.FromException<string>(new IOException("socket closed")));

        await model.SayHelloAsync();

        Assert.Equal(HelloViewModel.GenericFailure, model.Error);
        Assert.Equal(HelloViewModel.ReadyMessage, model.Greeting);
        Assert.False(model.IsLoading);
    }

    [Fact]
    public async Task ACancelledRequestKeepsTheGreetingAndShowsNoError()
    {
        var hello = new ScriptedHello();
        var model = new HelloViewModel(hello.Invoke);
        await model.SayHelloAsync();

        hello.Next = (_, _) => Task.FromException<string>(new OperationCanceledException());
        await model.SayHelloAsync();

        Assert.Equal("Hello, World!", model.Greeting);
        Assert.False(model.HasError);
        Assert.False(model.IsLoading);
    }

    [Fact]
    public async Task TheCallerTokenReachesTheHelloCall()
    {
        var hello = new ScriptedHello();
        var model = new HelloViewModel(hello.Invoke);
        using var source = new CancellationTokenSource();

        await model.SayHelloAsync(source.Token);

        Assert.Equal(source.Token, Assert.Single(hello.Tokens));
    }

    [Fact]
    public async Task ChangesAreRaisedForTheInFlightStateAndTheResult()
    {
        var gate = new TaskCompletionSource<string>(TaskCreationOptions.RunContinuationsAsynchronously);
        var model = new HelloViewModel((_, _) => gate.Task);
        var changed = new List<string?>();
        model.PropertyChanged += (_, e) => changed.Add(e.PropertyName);

        var call = model.SayHelloAsync();
        Assert.Contains(nameof(HelloViewModel.DisplayGreeting), changed);
        Assert.Contains(nameof(HelloViewModel.IsLoading), changed);

        changed.Clear();
        gate.SetResult("Hello, World!");
        await call;

        Assert.Contains(nameof(HelloViewModel.DisplayGreeting), changed);
        Assert.Contains(nameof(HelloViewModel.CanSayHello), changed);
    }

    [Fact]
    public async Task TheStateSurvivesAPageThatSubscribesAgain()
    {
        var hello = new ScriptedHello();
        var model = new HelloViewModel(hello.Invoke);
        model.Name = "Ada";
        await model.SayHelloAsync();

        // A recreated page subscribes to the same instance; it sees the kept name and greeting, with no reset.
        void FirstPage(object? sender, System.ComponentModel.PropertyChangedEventArgs e) { }
        model.PropertyChanged += FirstPage;
        model.PropertyChanged -= FirstPage;
        var second = model;

        Assert.Equal("Ada", second.Name);
        Assert.Equal("Hello, Ada!", second.DisplayGreeting);
        Assert.Same(model, second);
    }

    [Fact]
    public void ConstructorRejectsAMissingCall()
    {
        Assert.Throws<ArgumentNullException>(() => new HelloViewModel(null!));
    }
}
