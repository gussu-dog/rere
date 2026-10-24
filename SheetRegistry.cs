using System.Net;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Globalization;
using System.Collections.Concurrent;

public sealed class SheetRegistry
{
    private static readonly HttpClient Http = new();
    private const string SortedTableSpreadsheetId = "1ARPBJ2CWxQH9A3nnBo1Q2Cq8dtu8aiQyC-YrDJLs298";
    private const string TrackingSpreadsheetId = "16UzU1AzInFLPL6d7fUERU5NpYpRvvw8wQpJyLhcDJXg";
    private static readonly (string Id, string Title)[] PreconfiguredSpreadsheets =
    {
        ("14sgMwoNaZGduy44M8EAJf8VpH7NQ_sIVXoJ10Ss4VPg", "위험한 초대"),
        (SortedTableSpreadsheetId, "[펄프] 진짜 위험한 초대"),
        ("16UzU1AzInFLPL6d7fUERU5NpYpRvvw8wQpJyLhcDJXg", "추적! 오후3시!"),
        ("1M1mnu9C4Yb7HH5VSBwJjvuxP2v_87_89TNcbqQgnHvQ", "엠피리언 동창회 ~빛나던 청춘의 조각을 모아~")
    };
    private static readonly HashSet<string> ExcludedTabs = new(StringComparer.OrdinalIgnoreCase)
    {
        "가나다순 정렬 백지시트",
        "공지"
    };
    private static readonly JsonSerializerOptions JsonOptions = new() { WriteIndented = true };
    private readonly string _apiKey;
    private readonly string _characterSelectionsPath;
    private readonly SemaphoreSlim _gate = new(1, 1);
    private readonly SemaphoreSlim _catalogGate = new(1, 1);
    private readonly ConcurrentDictionary<string, CachedSkillData> _skillCache = new(StringComparer.Ordinal);
    private readonly ConcurrentDictionary<string, SemaphoreSlim> _skillLoadGates = new(StringComparer.Ordinal);
    private IReadOnlyList<RegisteredSpreadsheet>? _configuredSheets;

    public SheetRegistry()
    {
        _apiKey = ReadConfiguredVariable("GOOGLE_SHEETS_API_KEY") ?? string.Empty;
        var dataDirectory = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "RereDiscordBot");
        Directory.CreateDirectory(dataDirectory);
        _characterSelectionsPath = Path.Combine(dataDirectory, "character-selections.json");
    }

    private static string? ReadConfiguredVariable(string name)
    {
        var value = Environment.GetEnvironmentVariable(name);
        if (!string.IsNullOrWhiteSpace(value) || !OperatingSystem.IsWindows())
            return value;

        return Environment.GetEnvironmentVariable(name, EnvironmentVariableTarget.User)
            ?? Environment.GetEnvironmentVariable(name, EnvironmentVariableTarget.Machine);
    }

    public async Task<IReadOnlyList<RegisteredSpreadsheet>> GetAvailableSheetsAsync()
    {
        if (_configuredSheets is not null)
            return _configuredSheets;
        if (string.IsNullOrWhiteSpace(_apiKey))
            throw new InvalidOperationException("GOOGLE_SHEETS_API_KEY 환경 변수가 설정되지 않았습니다.");

        await _catalogGate.WaitAsync();
        try
        {
            if (_configuredSheets is not null)
                return _configuredSheets;

            var sheets = new List<RegisteredSpreadsheet>();
            foreach (var (spreadsheetId, _) in PreconfiguredSpreadsheets)
                sheets.Add(await ReadSpreadsheetMetadataAsync(spreadsheetId));

            _configuredSheets = sheets;
            return _configuredSheets;
        }
        finally
        {
            _catalogGate.Release();
        }
    }

    public IReadOnlyList<(string Id, string Title)> GetPreconfiguredSheetChoices() => PreconfiguredSpreadsheets;

    public async Task<IReadOnlyList<(string Value, string Name)>> GetCharacterChoicesAsync()
    {
        var sheets = await GetAvailableSheetsAsync();
        return sheets.SelectMany(sheet => sheet.Tabs.Select(tab =>
            (Value: $"{sheet.SpreadsheetId}|{tab}", Name: TrimChoiceName(tab))))
            .ToList();
    }

    public async Task<IReadOnlyList<(string Value, string Name)>> GetCharacterTabChoicesAsync(string spreadsheetId)
    {
        var sheet = (await GetAvailableSheetsAsync()).FirstOrDefault(item => item.SpreadsheetId == spreadsheetId);
        return sheet is null
            ? Array.Empty<(string Value, string Name)>()
            : sheet.Tabs.Select(tab => (Value: $"{sheet.SpreadsheetId}|{tab}", Name: TrimChoiceName(tab))).ToList();
    }

    public async Task<IReadOnlyList<(string Value, string Name)>> GetCharacterChoicesForUserAsync(ulong userId)
    {
        var allChoices = await GetCharacterChoicesAsync();
        var selected = await GetUserCharacterSelectionAsync(userId);
        if (selected is null || selected.Count == 0)
            return Array.Empty<(string Value, string Name)>();

        var selectedSet = selected.ToHashSet(StringComparer.Ordinal);
        return allChoices.Where(choice => selectedSet.Contains(choice.Value)).ToList();
    }

    public async Task<IReadOnlyList<string>?> GetUserCharacterSelectionAsync(ulong userId)
    {
        await _gate.WaitAsync();
        try
        {
            var selections = await ReadCharacterSelectionsAsync();
            return selections.TryGetValue(userId, out var selected) ? selected : null;
        }
        finally
        {
            _gate.Release();
        }
    }

    public async Task<bool> ClearUserCharacterSelectionsAsync(ulong userId)
    {
        await _gate.WaitAsync();
        try
        {
            var selections = await ReadCharacterSelectionsAsync();
            var removed = selections.Remove(userId);
            if (removed)
                await WriteCharacterSelectionsAsync(selections);
            return removed;
        }
        finally
        {
            _gate.Release();
        }
    }

    public async Task AddUserCharacterSelectionsForSheetAsync(ulong userId, string spreadsheetId, IEnumerable<string> selectedValues)
    {
        var available = await GetCharacterChoicesAsync();
        var validForSheet = available
            .Where(choice => choice.Value.StartsWith(spreadsheetId + "|", StringComparison.Ordinal))
            .Select(choice => choice.Value)
            .ToHashSet(StringComparer.Ordinal);
        var selectedForSheet = selectedValues
            .Where(validForSheet.Contains)
            .Distinct(StringComparer.Ordinal)
            .ToList();

        await _gate.WaitAsync();
        try
        {
            var selections = await ReadCharacterSelectionsAsync();
            var current = selections.TryGetValue(userId, out var existing)
                ? existing
                : new List<string>();
            current = current
                .Concat(selectedForSheet)
                .Distinct(StringComparer.Ordinal)
                .ToList();
            selections[userId] = current;
            await WriteCharacterSelectionsAsync(selections);
        }
        finally
        {
            _gate.Release();
        }
    }

    private static string TrimChoiceName(string value) => value.Length <= 100 ? value : value[..97] + "…";

    public async Task<IReadOnlyList<string>> GetSkillsAsync(string characterValue)
    {
        var data = await GetSkillDataAsync(characterValue);
        if (data is null) return Array.Empty<string>();
        return data.Values.Keys.OrderBy(skill => skill, StringComparer.CurrentCulture).ToList();
    }

    public async Task<IReadOnlyDictionary<string, int>?> GetSkillValuesAsync(string characterValue)
    {
        var data = await GetSkillDataAsync(characterValue);
        return data?.Values;
    }

    public async Task<IReadOnlyDictionary<string, int>?> GetSkillInvestmentValuesAsync(string characterValue)
    {
        var data = await GetSkillDataAsync(characterValue);
        return data?.InvestedPoints;
    }

    public async Task PreloadSkillsAsync(string characterValue)
    {
        try
        {
            await GetSkillDataAsync(characterValue);
        }
        catch (Exception ex)
        {
            // Keep background preloading quiet for Discord; the next focused request can retry.
            Console.WriteLine($"Skill preload failed ({ex.GetType().Name}): {ex.Message}");
        }
    }

    public async Task<int?> GetSkillValueAsync(string characterValue, string skillName)
    {
        var data = await GetSkillDataAsync(characterValue);
        if (data is null) return null;
        return data.Values.TryGetValue(skillName, out var value) ? value : null;
    }

    public async Task<string?> GetCharacterEmoteNameAsync(string characterValue, bool succeeded)
    {
        var data = await GetSkillDataAsync(characterValue);
        if (string.IsNullOrWhiteSpace(data?.EmoteKey)) return null;
        var outcome = succeeded ? "P" : "N";
        return data.EmoteKey.Contains('_')
            ? $"{data.EmoteKey}_{outcome}"
            : $"{outcome}_{data.EmoteKey}";
    }

    private async Task<CachedSkillData?> GetSkillDataAsync(string characterValue)
    {
        var separator = characterValue.IndexOf('|');
        if (separator <= 0 || separator == characterValue.Length - 1)
            return null;
        var spreadsheetId = characterValue[..separator];
        var tab = characterValue[(separator + 1)..];
        var registrations = await GetAvailableSheetsAsync();
        if (!registrations.Any(sheet => sheet.SpreadsheetId == spreadsheetId && sheet.Tabs.Contains(tab, StringComparer.OrdinalIgnoreCase)))
            return null;
        if (string.IsNullOrWhiteSpace(_apiKey))
            throw new InvalidOperationException("GOOGLE_SHEETS_API_KEY 환경 변수를 찾지 못했어요. 사용자 환경 변수에 키를 설정했는지 확인해 주세요!");

        var key = $"{spreadsheetId}|{tab}";
        if (_skillCache.TryGetValue(key, out var cached) && cached.ExpiresAt > DateTimeOffset.UtcNow)
            return cached;

        var loadGate = _skillLoadGates.GetOrAdd(key, _ => new SemaphoreSlim(1, 1));
        await loadGate.WaitAsync();
        try
        {
            if (_skillCache.TryGetValue(key, out cached) && cached.ExpiresAt > DateTimeOffset.UtcNow)
                return cached;

            // All linked character sheets use the same three skill blocks:
            // C/F -> L, P/S -> Y, and AC/AF -> AL (skill labels -> total value).
            // Read only those ranges and omit formatting metadata for fast autocomplete.
            var escapedTab = tab.Replace("'", "''");
            var usesSortedTable = spreadsheetId == SortedTableSpreadsheetId;
            var ranges = usesSortedTable
                ? new[] { $"'{escapedTab}'!A1", $"'{escapedTab}'!B129:M200", $"'{escapedTab}'!O21:AL27", $"'{escapedTab}'!AE12" }
                : new[] { $"'{escapedTab}'!A1", $"'{escapedTab}'!S3:AH7", $"'{escapedTab}'!C19:N80", $"'{escapedTab}'!P19:AA80", $"'{escapedTab}'!AC19:AN80", $"'{escapedTab}'!AE9" };
            var requestUrl = $"https://sheets.googleapis.com/v4/spreadsheets/{Uri.EscapeDataString(spreadsheetId)}/values:batchGet?valueRenderOption=FORMATTED_VALUE" +
                string.Concat(ranges.Select(range => $"&ranges={Uri.EscapeDataString(range)}")) +
                $"&key={Uri.EscapeDataString(_apiKey)}";
            using var response = await Http.GetAsync(requestUrl);
            if (!response.IsSuccessStatusCode)
                throw new InvalidOperationException($"기능표를 읽지 못했어요 (HTTP {(int)response.StatusCode}). API 키의 Sheets API 설정과 시트 공개 설정을 확인해 주세요!");

            await using var stream = await response.Content.ReadAsStreamAsync();
            using var document = await JsonDocument.ParseAsync(stream);
            Dictionary<string, int>? investedPoints = null;
            Dictionary<string, int> values;
            if (usesSortedTable)
                values = ParseSortedTableSkillValues(document.RootElement);
            else
                values = ParseSkillValues(document.RootElement, out investedPoints);
            foreach (var characteristic in ParseCharacteristicValues(document.RootElement, usesSortedTable))
                values.TryAdd(characteristic.Key, characteristic.Value);
            var emoteKey = ParseCharacterEmoteKey(document.RootElement);
            var sanityValue = ParseSanityValue(document.RootElement);
            if (sanityValue is not null)
                values.TryAdd("이성", sanityValue.Value);
            cached = new CachedSkillData(values, investedPoints, emoteKey, DateTimeOffset.UtcNow.AddMinutes(1));
            _skillCache[key] = cached;
            return cached;
        }
        finally
        {
            loadGate.Release();
        }
    }

    private static string? ParseCharacterEmoteKey(JsonElement root)
    {
        if (!root.TryGetProperty("valueRanges", out var ranges) || ranges.GetArrayLength() == 0)
            return null;

        var firstRange = ranges[0];
        if (!firstRange.TryGetProperty("values", out var rows) || rows.GetArrayLength() == 0)
            return null;
        var firstRow = rows[0];
        if (firstRow.GetArrayLength() == 0)
            return null;

        var key = firstRow[0].GetString()?.Trim();
        if (string.IsNullOrWhiteSpace(key) || key.Length > 30 ||
            !Regex.IsMatch(key, @"^[A-Za-z0-9]+(?:_[A-Za-z0-9]+)*$", RegexOptions.CultureInvariant))
            return null;

        return key;
    }

    private static int? ParseSanityValue(JsonElement root)
    {
        if (!root.TryGetProperty("valueRanges", out var ranges) || ranges.GetArrayLength() == 0)
            return null;

        var range = ranges[ranges.GetArrayLength() - 1];
        if (!range.TryGetProperty("values", out var rows) || rows.GetArrayLength() == 0 || rows[0].GetArrayLength() == 0)
            return null;

        var value = rows[0][0].GetString()?.Trim().Replace(",", "");
        return int.TryParse(value, NumberStyles.Any, CultureInfo.InvariantCulture, out var sanity) ? sanity : null;
    }

    private static Dictionary<string, int> ParseSkillValues(JsonElement root, out Dictionary<string, int> investedPoints)
    {
        var result = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
        investedPoints = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
        if (!root.TryGetProperty("valueRanges", out var ranges)) return result;
        // Range 0 contains the emote key and range 1 contains characteristics.
        foreach (var range in ranges.EnumerateArray().Skip(2))
        {
            if (!range.TryGetProperty("values", out var rows)) continue;
            foreach (var row in rows.EnumerateArray())
            {
                var cells = row.EnumerateArray().Select(cell => cell.GetString()?.Trim() ?? string.Empty).ToList();
                if (cells.Count < 10 || !int.TryParse(cells[9], NumberStyles.Any, CultureInfo.InvariantCulture, out var total))
                    continue;

                // Each block can have a parent skill and a specialization. Keep both
                // visible in one selectable name (e.g. "언어 | 독일").
                var mainSkill = cells[0];
                var specialization = cells[3];
                var allocation = ParseNonNegativeInt(cells, 7);
                var scenarioOrTraining = ParseNonNegativeInt(cells, 11);
                var investment = allocation + scenarioOrTraining;
                if (IsPotentialSkillName(mainSkill) && IsPotentialSkillName(specialization))
                {
                    var skillName = $"{mainSkill} | {specialization}";
                    AddSkill(skillName, total, result);
                    AddSkillInvestment(skillName, investment, investedPoints);
                }
                else
                {
                    AddSkill(mainSkill, total, result);
                    AddSkill(specialization, total, result);
                    AddSkillInvestment(mainSkill, investment, investedPoints);
                    AddSkillInvestment(specialization, investment, investedPoints);
                }
            }
        }
        return result;
    }

    private static int ParseNonNegativeInt(IReadOnlyList<string> cells, int index) =>
        index < cells.Count && int.TryParse(cells[index].Replace(",", ""), NumberStyles.Any, CultureInfo.InvariantCulture, out var value)
            ? Math.Max(0, value)
            : 0;

    private static void AddSkillInvestment(string label, int investment, Dictionary<string, int> result)
    {
        if (investment <= 0 || !IsPotentialSkillName(label))
            return;
        result[label] = result.TryGetValue(label, out var existing) ? existing + investment : investment;
    }

    private static Dictionary<string, int> ParseCharacteristicValues(JsonElement root, bool usesSortedTable)
    {
        var result = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
        if (!root.TryGetProperty("valueRanges", out var ranges))
            return result;

        var rangeIndex = usesSortedTable ? 2 : 1;
        if (ranges.GetArrayLength() <= rangeIndex ||
            !ranges[rangeIndex].TryGetProperty("values", out var rows))
            return result;

        var rowValues = rows.EnumerateArray()
            .Select(row => row.EnumerateArray().Select(cell => cell.GetString()?.Trim() ?? string.Empty).ToList())
            .ToList();
        for (var rowIndex = 0; rowIndex < rowValues.Count; rowIndex++)
        {
            var cells = rowValues[rowIndex];
            for (var columnIndex = 0; columnIndex < cells.Count; columnIndex++)
            {
                var characteristicName = GetCharacteristicName(cells[columnIndex]);
                if (characteristicName is null)
                    continue;

                var value = 0;
                var valueIsPresent = columnIndex + 3 < cells.Count &&
                    int.TryParse(cells[columnIndex + 3].Replace(",", ""), NumberStyles.Any, CultureInfo.InvariantCulture, out value);
                if (!valueIsPresent && rowIndex + 1 < rowValues.Count && columnIndex < rowValues[rowIndex + 1].Count)
                    valueIsPresent = int.TryParse(rowValues[rowIndex + 1][columnIndex].Replace(",", ""), NumberStyles.Any, CultureInfo.InvariantCulture, out value);

                if (valueIsPresent)
                    result[characteristicName] = value;
            }
        }

        return result;
    }

    private static string? GetCharacteristicName(string label)
    {
        var names = new[] { "근력", "민첩", "정신", "건강", "외모", "교육", "크기", "지능", "행운" };
        return names.FirstOrDefault(name => label.StartsWith(name, StringComparison.OrdinalIgnoreCase));
    }

    private static Dictionary<string, int> ParseSortedTableSkillValues(JsonElement root)
    {
        var result = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
        if (!root.TryGetProperty("valueRanges", out var ranges) || ranges.GetArrayLength() < 2)
            return result;

        var tableRange = ranges[1];
        if (!tableRange.TryGetProperty("values", out var rows))
            return result;

        // This workbook's "roll20 자동화 시트 입력용 정렬기" table lists
        // three skill/value pairs per row in B:E, F:I, and J:M.
        foreach (var row in rows.EnumerateArray())
        {
            var cells = row.EnumerateArray().Select(cell => cell.GetString()?.Trim() ?? string.Empty).ToList();
            foreach (var labelIndex in new[] { 0, 4, 8 })
            {
                var valueIndex = labelIndex + 3;
                if (cells.Count <= valueIndex ||
                    !int.TryParse(cells[valueIndex].Replace(",", ""), NumberStyles.Any, CultureInfo.InvariantCulture, out var value))
                    continue;

                var skillName = cells[labelIndex];
                var separatorIndex = skillName.IndexOf(':');
                if (separatorIndex > 0 && separatorIndex < skillName.Length - 1)
                    skillName = $"{skillName[..separatorIndex]} | {skillName[(separatorIndex + 1)..]}";

                AddSkill(skillName, value, result);
            }
        }

        return result;
    }

    private static void AddSkill(string label, int value, Dictionary<string, int> result)
    {
        if (IsPotentialSkillName(label) && !result.ContainsKey(label))
            result[label] = value;
    }

    private static bool IsPotentialSkillName(string text) =>
        !string.IsNullOrWhiteSpace(text) && text.Length <= 30 &&
        !double.TryParse(text.Replace(",", ""), NumberStyles.Any, CultureInfo.InvariantCulture, out _) &&
        !text.Contains("기능", StringComparison.Ordinal) &&
        !text.Contains("점수", StringComparison.Ordinal) &&
        !text.Contains("보상", StringComparison.Ordinal) &&
        !text.Contains("기본", StringComparison.Ordinal) &&
        !text.Contains("하늘색", StringComparison.Ordinal) &&
        !text.Contains("인류", StringComparison.Ordinal) &&
        !text.Contains("합계", StringComparison.Ordinal) &&
        !text.Contains("총합", StringComparison.Ordinal);

    private async Task<RegisteredSpreadsheet> ReadSpreadsheetMetadataAsync(string spreadsheetId)
    {
        var fields = Uri.EscapeDataString("spreadsheetId,properties(title),sheets(properties(sheetId,title,index))");
        var requestUrl = $"https://sheets.googleapis.com/v4/spreadsheets/{Uri.EscapeDataString(spreadsheetId)}?fields={fields}&key={Uri.EscapeDataString(_apiKey)}";
        using var response = await Http.GetAsync(requestUrl);
        if (!response.IsSuccessStatusCode)
        {
            var reason = response.StatusCode == HttpStatusCode.NotFound
                ? "문서를 찾을 수 없습니다. 링크와 공개 설정을 확인해 주세요."
                : $"Google Sheets API 요청에 실패했습니다 (HTTP {(int)response.StatusCode}). API 키와 Sheets API 사용 설정을 확인해 주세요.";
            throw new InvalidOperationException(reason);
        }

        await using var stream = await response.Content.ReadAsStreamAsync();
        using var document = await JsonDocument.ParseAsync(stream);
        var root = document.RootElement;
        var title = root.GetProperty("properties").GetProperty("title").GetString() ?? "제목 없는 스프레드시트";
        var tabs = new List<string>();
        if (root.TryGetProperty("sheets", out var sheets))
        {
            foreach (var sheet in sheets.EnumerateArray())
            {
                if (sheet.TryGetProperty("properties", out var properties) &&
                    properties.TryGetProperty("title", out var tabTitle))
                {
                    var value = tabTitle.GetString();
                    if (!string.IsNullOrWhiteSpace(value) && !ExcludedTabs.Contains(value.Trim()))
                        tabs.Add(value);
                }
            }
        }

        return new RegisteredSpreadsheet(spreadsheetId, title, ExcludeNonCharacterTabs(spreadsheetId, tabs));
    }

    private static List<string> ExcludeNonCharacterTabs(string spreadsheetId, IEnumerable<string> tabs)
    {
        var excluded = new HashSet<string>(ExcludedTabs, StringComparer.OrdinalIgnoreCase);
        if (spreadsheetId == SortedTableSpreadsheetId)
            excluded.UnionWith(new[] { "공지사항", "펄프 캐릭터 시트" });
        if (spreadsheetId == TrackingSpreadsheetId)
            excluded.UnionWith(new[] { "요기부터동창회", "이후로는사교도" });
        return tabs.Where(tab => !excluded.Contains(tab.Trim())).ToList();
    }

    private async Task<Dictionary<ulong, List<string>>> ReadCharacterSelectionsAsync()
    {
        if (!File.Exists(_characterSelectionsPath))
            return new Dictionary<ulong, List<string>>();

        await using var stream = File.OpenRead(_characterSelectionsPath);
        return await JsonSerializer.DeserializeAsync<Dictionary<ulong, List<string>>>(stream)
            ?? new Dictionary<ulong, List<string>>();
    }

    private async Task WriteCharacterSelectionsAsync(Dictionary<ulong, List<string>> selections)
    {
        var temporaryPath = _characterSelectionsPath + ".tmp";
        await using (var stream = File.Create(temporaryPath))
            await JsonSerializer.SerializeAsync(stream, selections, JsonOptions);

        File.Move(temporaryPath, _characterSelectionsPath, overwrite: true);
    }
}

public sealed record RegisteredSpreadsheet(string SpreadsheetId, string Title, List<string> Tabs);
internal sealed record CachedSkillData(Dictionary<string, int> Values, Dictionary<string, int>? InvestedPoints, string? EmoteKey, DateTimeOffset ExpiresAt);

