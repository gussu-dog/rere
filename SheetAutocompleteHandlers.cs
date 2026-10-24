using Discord;
using Discord.Interactions;

public sealed class SheetAutocompleteHandler : AutocompleteHandler
{
    public override Task<AutocompletionResult> GenerateSuggestionsAsync(
        IInteractionContext context,
        IAutocompleteInteraction interaction,
        IParameterInfo parameter,
        IServiceProvider services)
    {
        var registry = services.GetService(typeof(SheetRegistry)) as SheetRegistry;
        if (registry is null)
            return Task.FromResult(AutocompletionResult.FromSuccess());

        var current = interaction.Data.Current.Value?.ToString() ?? string.Empty;
        try
        {
            var sheets = registry.GetPreconfiguredSheetChoices();
            var suggestions = sheets
                .Where(sheet => string.IsNullOrWhiteSpace(current) || sheet.Title.Contains(current, StringComparison.CurrentCultureIgnoreCase))
                .Take(25)
                .Select(sheet => new AutocompleteResult(sheet.Title, sheet.Id));
            return Task.FromResult(AutocompletionResult.FromSuccess(suggestions));
        }
        catch (Exception ex)
        {
            Console.WriteLine($"Sheet autocomplete failed ({ex.GetType().Name}): {ex.Message}");
            return Task.FromResult(AutocompletionResult.FromSuccess());
        }
    }
}

public sealed class RegistrationCharacterAutocompleteHandler : AutocompleteHandler
{
    public override async Task<AutocompletionResult> GenerateSuggestionsAsync(
        IInteractionContext context,
        IAutocompleteInteraction interaction,
        IParameterInfo parameter,
        IServiceProvider services)
    {
        var registry = services.GetService(typeof(SheetRegistry)) as SheetRegistry;
        if (registry is null)
            return AutocompletionResult.FromSuccess();

        var configuredSheets = registry.GetPreconfiguredSheetChoices();
        var selectedSheetValue = interaction.Data.Options
            .Select(option => option.Value?.ToString())
            .FirstOrDefault(value => configuredSheets.Any(sheet => sheet.Id == value));
        if (string.IsNullOrWhiteSpace(selectedSheetValue))
            return AutocompletionResult.FromSuccess();

        var current = interaction.Data.Current.Value?.ToString() ?? string.Empty;
        try
        {
            var choices = await registry.GetCharacterTabChoicesAsync(selectedSheetValue);
            var suggestions = choices
                .Where(choice => string.IsNullOrWhiteSpace(current) || choice.Name.Contains(current, StringComparison.CurrentCultureIgnoreCase))
                .Take(25)
                .Select(choice => new AutocompleteResult(choice.Name, choice.Value));
            return AutocompletionResult.FromSuccess(suggestions);
        }
        catch (Exception ex)
        {
            Console.WriteLine($"Registration character autocomplete failed ({ex.GetType().Name}): {ex.Message}");
            return AutocompletionResult.FromSuccess();
        }
    }
}

public sealed class CharacterAutocompleteHandler : AutocompleteHandler
{
    public override async Task<AutocompletionResult> GenerateSuggestionsAsync(
        IInteractionContext context,
        IAutocompleteInteraction interaction,
        IParameterInfo parameter,
        IServiceProvider services)
    {
        var registry = services.GetService(typeof(SheetRegistry)) as SheetRegistry;
        if (registry is null)
            return AutocompletionResult.FromSuccess();

        var current = interaction.Data.Current.Value?.ToString() ?? string.Empty;
        var choices = await registry.GetCharacterChoicesForUserAsync(context.User.Id);
        if (current.Length >= 1)
        {
            var likelySelections = choices
                .Where(item => item.Name.StartsWith(current, StringComparison.CurrentCultureIgnoreCase))
                .Take(current.Length >= 2 ? 3 : 1);
            foreach (var choice in likelySelections)
                _ = registry.PreloadSkillsAsync(choice.Value);
        }
        var suggestions = choices
            .Where(item => string.IsNullOrWhiteSpace(current) || item.Name.Contains(current, StringComparison.CurrentCultureIgnoreCase))
            .Take(25)
            .Select(item => new AutocompleteResult(item.Name, item.Value));
        return AutocompletionResult.FromSuccess(suggestions);
    }
}

public sealed class SkillAutocompleteHandler : AutocompleteHandler
{
    public override async Task<AutocompletionResult> GenerateSuggestionsAsync(
        IInteractionContext context,
        IAutocompleteInteraction interaction,
        IParameterInfo parameter,
        IServiceProvider services)
    {
        var registry = services.GetService(typeof(SheetRegistry)) as SheetRegistry;
        if (registry is null)
            return AutocompletionResult.FromSuccess();

        var character = interaction.Data.Options
            .FirstOrDefault(option => option.Value?.ToString()?.Contains('|') == true)?.Value?.ToString();
        if (string.IsNullOrWhiteSpace(character))
            return AutocompletionResult.FromSuccess();

        var current = interaction.Data.Current.Value?.ToString() ?? string.Empty;
        try
        {
            var skills = await registry.GetSkillsAsync(character);
            var suggestions = skills
                .Where(skill => string.IsNullOrWhiteSpace(current) || skill.Contains(current, StringComparison.CurrentCultureIgnoreCase))
                .Take(25)
                .Select(skill => new AutocompleteResult(skill, skill));
            return AutocompletionResult.FromSuccess(suggestions);
        }
        catch (Exception ex)
        {
            // Log only the safe exception text, never the API URL (which contains the API key).
            Console.WriteLine($"Skill autocomplete failed ({ex.GetType().Name}): {ex.Message}");
            return AutocompletionResult.FromSuccess();
        }
    }
}

public sealed class RollModeAutocompleteHandler : AutocompleteHandler
{
    private static readonly (string Name, string Value)[] Modes =
    {
        ("패널티 +1", "패널티+1"),
        ("패널티 +2", "패널티+2"),
        ("보너스 +1", "보너스+1"),
        ("보너스 +2", "보너스+2")
    };

    public override Task<AutocompletionResult> GenerateSuggestionsAsync(
        IInteractionContext context,
        IAutocompleteInteraction interaction,
        IParameterInfo parameter,
        IServiceProvider services)
    {
        var current = interaction.Data.Current.Value?.ToString() ?? string.Empty;
        var suggestions = Modes
            .Where(mode => string.IsNullOrWhiteSpace(current) ||
                mode.Name.Contains(current, StringComparison.CurrentCultureIgnoreCase) ||
                mode.Value.Contains(current, StringComparison.CurrentCultureIgnoreCase))
            .Select(mode => new AutocompleteResult(mode.Name, mode.Value));
        return Task.FromResult(AutocompletionResult.FromSuccess(suggestions));
    }
}
