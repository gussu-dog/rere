using System;
using System.Reflection;
using System.Threading.Tasks;
using Discord;
using Discord.Commands;
using Discord.Interactions;
using Discord.WebSocket;
using Microsoft.Extensions.DependencyInjection;

class Program
{
    private DiscordSocketClient _client;
    private InteractionService _commands;
    private IServiceProvider _services;

    public static void Main(string[] args) => new Program().RunBotAsync().GetAwaiter().GetResult();

    public async Task RunBotAsync()
    {
        var token = Environment.GetEnvironmentVariable("DISCORD_BOT_TOKEN");
        if (string.IsNullOrWhiteSpace(token) && OperatingSystem.IsWindows())
        {
            token = Environment.GetEnvironmentVariable("DISCORD_BOT_TOKEN", EnvironmentVariableTarget.User)
                ?? Environment.GetEnvironmentVariable("DISCORD_BOT_TOKEN", EnvironmentVariableTarget.Machine);
        }
        if (string.IsNullOrWhiteSpace(token))
        {
            throw new InvalidOperationException(
                "DISCORD_BOT_TOKEN 환경 변수가 설정되지 않았습니다. 봇 토큰을 환경 변수에 설정한 뒤 다시 실행하세요.");
        }

        _client = new DiscordSocketClient(new DiscordSocketConfig
        {
            GatewayIntents = GatewayIntents.Guilds // 슬래시 명령어는 Guilds 인텐트 필요
        });

        _commands = new InteractionService(_client, new InteractionServiceConfig
        {
            EnableAutocompleteHandlers = true
        }); // 명령어 서비스 초기화

        // ServiceCollection을 생성하고 필요한 서비스 등록
        _services = new ServiceCollection()
            .AddSingleton(_client)  // 클라이언트 추가
            .AddSingleton(_commands) // 슬래시 명령어 서비스 추가
            .AddSingleton<SheetRegistry>() // TRPG 스프레드시트 허용 목록
            .BuildServiceProvider(); // 서비스 프로바이더 빌드

        _client.Log += Log;
        _client.Ready += OnReady;
        _client.InteractionCreated += HandleInteraction;

        await _client.LoginAsync(TokenType.Bot, token);
        await _commands.AddModulesAsync(Assembly.GetEntryAssembly(), _services); // 명령어 모듈 로드
        await _client.StartAsync();

        await Task.Delay(-1);
    }

    private async Task OnReady()
    {
        Console.WriteLine($"{_client.CurrentUser} is online!");

        try
        {
            var sheets = await _services.GetRequiredService<SheetRegistry>().GetAvailableSheetsAsync();
            Console.WriteLine($"Loaded {sheets.Count} TRPG spreadsheets.");
        }
        catch (Exception ex)
        {
            Console.WriteLine($"TRPG spreadsheet preload failed ({ex.GetType().Name}).");
        }

        // 슬래시 명령어를 서버에 등록
        foreach (var guild in _client.Guilds)
        {
            await _commands.RegisterCommandsToGuildAsync(guild.Id);
            Console.WriteLine($"Registered commands to {guild.Name}");
        }
    }

    private async Task HandleInteraction(SocketInteraction interaction)
    {
        var context = new SocketInteractionContext(_client, interaction);
        await _commands.ExecuteCommandAsync(context, _services);
    }

    private Task Log(LogMessage msg)
    {
        Console.WriteLine(msg);
        return Task.CompletedTask;
    }

}
